# 📋 Documentación de Cierre — Sesión de Estabilización CV Worker & Dashboard

**Fecha:** Septiembre 2026
**Autor de esta sesión:** Rivaldo (con asistencia de Claude Code)
**Objetivo:** Diagnosticar y estabilizar el reconocimiento visual del `cv-worker`, corregir bugs de integración con Supabase, y mejorar el diseño del dashboard unificado.

---

## 1. Qué se hizo en esta sesión

### 1.1 Bugs corregidos

| Bug | Archivo | Descripción |
|---|---|---|
| **Catálogo vectorial cargaba ruido aleatorio** | `cv-worker/vector_engine.py` | La ruta `dataset_dir = "SetImagenesBuenas"` era relativa al `cwd` del proceso. Al lanzar el worker desde `cv-worker/`, esa carpeta no existía ahí (vive un nivel arriba), así que `os.path.exists()` fallaba en silencio y el sistema usaba vectores **aleatorios sintéticos** (`np.random.randn(512)`) en vez de fotos reales. Corregido con ruta absoluta basada en `os.path.dirname(__file__)`. |
| **Código de barras de Chokis no coincidía con Supabase** | `cv-worker/vector_engine.py` | El mapeo interno tenía `7501000635003`, pero la tabla `productos` en Supabase tiene `7501011115481`. Cualquier reconocimiento visual exitoso de Chokis habría fallado al buscar el producto en el backend. Corregido. |
| **Congelamiento del video al detectar un producto** | `cv-worker/main.py` | `enviar_deteccion_api()` (POST HTTP) y `atlas.registrar_evento_fallback()` (insert a MongoDB) se ejecutaban de forma **síncrona dentro del mismo loop** que captura y muestra la cámara. Cada detección bloqueaba el video hasta que la petición de red/DB terminaba. Ahora corren en un `ThreadPoolExecutor` en segundo plano. |
| **Vector ResNet18 se recalculaba en cada frame** | `cv-worker/main.py` | YOLO ya se saltaba 1 de cada 2 frames, pero la extracción de embeddings (ResNet18) corría en el 100% de los frames con objeto detectado — doble inferencia GPU sin necesidad. Ahora ambos están sincronizados bajo `PROCESS_EVERY_N_FRAMES` (config), y el bounding box se sigue dibujando en cada frame (sin heavy-compute) para que el HUD no parpadee. |
| **Doble instancia del worker compitiendo por la cámara** | Proceso, no código | En un punto había dos procesos `cv-worker/main.py` corriendo a la vez, ambos abriendo el índice de cámara 1 — el segundo no podía leer frames y forzaba el fallback a modo simulación. Resuelto matando el proceso duplicado; **si vuelve a pasar "la cámara no prende"/cae a simulación, lo primero a revisar es si hay más de un proceso Python usando la cámara** (`tasklist` / `Get-CimInstance Win32_Process`). |
| **`PosView.jsx` llamaba a `/checkout` en vez de `/cerrar`** | `frontend-dashboard/src/PosView.jsx` | El endpoint real en el backend es `POST /ventas/{id}/cerrar`. Corregido. |
| **Falso positivo Agua ↔ Coca-Cola** | `cv-worker/vector_engine.py` | `buscar_producto_por_vector` solo exigía "similitud ≥ 65%" contra cualquier imagen suelta del catálogo. Ahora agrupa por código de producto y exige además un **margen mínimo (4%)** sobre el segundo candidato más parecido, para no confundir productos ambiguos. |
| **Catálogo de Agua con marca equivocada** | `SetImagenesBuenas/BoteAgua/` | Se habían agregado por error fotos de la marca "Ciel" cuando el producto real en Supabase es "Agua e-pura". Corregido — el folder solo contiene ahora fotos de e-pura 1L. |

### 1.2 Mejoras de infraestructura / DX

- **`cv-worker/capturar_referencias.py`** (nuevo): herramienta interactiva para capturar fotos de referencia directamente desde la cámara del worker (teclas 1-5 para elegir producto, ESPACIO para guardar). Pensada para reemplazar fotos de stock por fotos tomadas en las condiciones reales de la cámara de producción.
- **10 imágenes reales agregadas al catálogo** (Coca-Cola, Sabritas, Ruffles, Chokis) obtenidas de [Open Food Facts](https://openfoodfacts.org) (base de datos abierta, fotos reales de usuarios, no fotos de stock genéricas).
- **MCP de Supabase configurado** (`.mcp.json`, no incluido en este commit — ver sección de riesgos) para poder consultar la base de datos directamente desde Claude Code en sesiones futuras.
- **Dashboard rediseñado**: se quitó el panel de "Previsualización de Cámara" del POS web (era redundante — el `cv-worker` ya muestra su propio feed en una ventana de OpenCV). Se unificó la paleta de color entre el POS y el Panel de Métricas, se cargaron las fuentes (`JetBrains Mono` y `Plus Jakarta Sans`) que el CSS ya referenciaba pero nunca se importaban, se limpiaron restos de la plantilla default de Vite en `index.css`, y se agregaron sombras/hover consistentes en tarjetas, tablas y botones.

---

## 2. Problemas conocidos que NO se resolvieron (y por qué)

### 2.1 El reconocimiento 100% visual (sin código de barras) tiene un techo de precisión bajo

Se midió cuantitativamente la separación entre clases del catálogo vectorial (ResNet18 + similitud de coseno):

```
                  similitud cruzada (distinto producto)    similitud interna (mismo producto)
Coca-Cola         media ~0.65 | máx ~0.78-0.82             media ~0.84-0.87 | mín ~0.70-0.78
Sabritas          media ~0.68-0.76 | máx ~0.81-0.90        media ~0.83-0.87 | mín ~0.64-0.70
Ruffles           media ~0.68-0.76 | máx ~0.81-0.90        media ~0.85-0.87 | mín ~0.65-0.75
Agua              media ~0.61-0.73 | máx ~0.78-0.86        media ~0.81-0.82 | mín ~0.72-0.74
Chokis            media ~0.66-0.76 | máx ~0.75-0.88        media ~0.82-0.85 | mín ~0.70-0.73
```

**En casi todos los casos, la similitud entre productos DISTINTOS puede superar la similitud entre fotos del MISMO producto.** Esto no es un bug de código — es una limitación del enfoque: ResNet18 preentrenado en ImageNet extrae características globales de color/forma/composición de la imagen, no logos/texto específicos de marca. Se intentó reemplazar por CLIP (modelo entrenado por contraste imagen-texto, mejor para este caso en teoría) pero **se revirtió a petición del equipo**, ya que la documentación y el diseño del proyecto especifican ResNet18 como la arquitectura de Dev B — cambiarlo sin acuerdo del equipo se consideró fuera de alcance de esta sesión.

**Causa raíz real medida:** el salto de dominio entre las fotos de catálogo (limpias, fondo blanco, producto llenando el frame) y cómo la cámara real captura el producto (ángulo, iluminación, glare) es el factor que más pesa. Se intentó cerrar ese salto fotografiando la pantalla de un celular con la cámara del worker (mismo "dominio" que las pruebas) — **esto empeoró los resultados**, porque el fondo compartido (mano, bisel del teléfono, cuarto) domina la comparación por encima del contenido real del producto en pantalla.

### 2.2 Sin productos físicos reales, la validación del sistema es limitada

El equipo no cuenta con los productos físicos (bolsas de papas, botellas, etc.) para probar — solo fotos en pantalla o impresas. Esto es una limitación real del contexto del proyecto (no de la implementación), pero **condiciona fuertemente qué tan bien puede funcionar el reconocimiento 100% visual** en la demo final.

### 2.3 Columna `embedding` (pgvector) en Supabase nunca se conectó

La tabla `productos` tiene una columna `embedding` (tipo `vector`) pensada en el Día 1 del sprint para guardar los embeddings en Supabase con búsqueda pgvector. El código actual (`vector_engine.py`) **nunca escribe ni lee esa columna** — todo el catálogo vive en memoria RAM del proceso del worker. Esto es consistente con una decisión de diseño ya documentada (evitar la latencia de red de Supabase en el loop de cámara), pero significa que:
- El catálogo vectorial se **reconstruye desde cero cada vez que se reinicia el worker** (recalcula todos los embeddings de las imágenes en `SetImagenesBuenas/`).
- No hay forma de compartir/sincronizar el catálogo entre múltiples instancias del worker (si algún día se corre en más de una caja registradora).

### 2.4 Redis está en `docker-compose.yml` pero no se usa en ningún lado del código

Confirmado por grep: `redis` solo aparece en `backend/app/core/config.py` (variables de entorno `REDIS_HOST`/`REDIS_PORT`), pero ningún servicio del backend lo importa ni lo usa. La "caché de resiliencia" mencionada en `PlanInicial.md` (Día 4, responsabilidad de Dev E) **no está implementada**.

---

## 3. Qué se puede mejorar (recomendaciones concretas, en orden de impacto)

1. **Capturar fotos de referencia con productos físicos reales**, con la cámara y en las condiciones de iluminación reales del punto de venta (usar `cv-worker/capturar_referencias.py`). Esto es lo único que medimos que realmente puede cerrar la brecha de dominio.
2. **Si no hay acceso a productos físicos**, considerar imprimir las imágenes de producto en papel (en vez de mostrarlas en pantalla de celular) y recapturar el catálogo con esas impresiones — elimina el brillo de pantalla y el patrón moiré, y se acerca más a como el catálogo actual ya está armado.
3. **Aumentar el número de imágenes de referencia por producto** (idealmente 15-20 con variedad de ángulo/distancia) una vez resuelto el punto 1 o 2.
4. **Considerar recorte más ajustado del ROI** antes de extraer el vector — el bounding box de YOLO (modelo genérico COCO, sin clases de producto reales) a veces incluye fondo/mano de más, lo que ensucia el embedding.
5. **Evaluar un modelo YOLO entrenado específicamente** en las clases de producto del catálogo (usando las imágenes ya recolectadas en `SetImagenesBuenas/` y `productos para entrenar modelo/`) — esto resolvería tanto la detección (bounding box ajustado a producto real) como, potencialmente, la clasificación directa sin depender tanto del matching vectorial. Es la mejora de mayor impacto pero requiere más tiempo/esfuerzo (recolectar más imágenes, entrenar, validar).
6. Si el equipo decide que vale la pena revisitar CLIP u otro extractor de embeddings, hacerlo como una decisión de equipo documentada (no unilateral), idealmente en paralelo a la opción 5.

---

## 4. Lo que le corresponde a Dev E (Integración / DevOps) para cerrar el sprint

Según `PlanInicial.md`, el rol de Dev E incluye: *Setup de Atlas y Supabase, Docker Compose local, caché de resiliencia, pruebas de carga y latencia*. Estado actual de cada uno:

| Tarea | Estado | Detalle |
|---|---|---|
| **Setup Supabase** | ✅ Hecho | Proyecto conectado, tablas `productos`, `inventario`, `ventas`, `detalle_ventas` existentes y en uso. MCP de Supabase configurado en `.mcp.json` para administración futura (requiere que cada dev lo autorice localmente vía `/mcp` — no se sube el token, solo la URL del servidor). |
| **Setup MongoDB Atlas** | ✅ Hecho | `atlas_logger.py` funcional, con fallback offline a consola si no hay conexión. |
| **Docker Compose local** | ⚠️ Parcial | `docker-compose.yml` existe y define `backend` + `redis`, pero **no incluye el `cv-worker`** (no puede correr en contenedor por necesitar acceso directo a la cámara/GPU del host) ni el `frontend-dashboard`. Falta decidir si el frontend se dockeriza o se documenta como "correr con `npm run dev` fuera de Docker". |
| **Caché de resiliencia (SQLite local si Supabase no responde)** | ❌ Pendiente | Mencionado explícitamente en el Día 4 del plan original. No se encontró ninguna implementación en `backend/`. Este es probablemente el pendiente más importante de Dev E. |
| **Redis** | ⚠️ Configurado pero sin uso | Está en `docker-compose.yml` y en `config.py`, pero ningún servicio lo usa todavía. Si la caché de resiliencia se implementa con Redis en vez de SQLite, aquí es donde conectarlo. |
| **Pruebas de carga (Locust)** | ❌ Pendiente | No se encontró ningún archivo de Locust en el repo. Mencionado en el Día 7 del plan original (objetivo: latencia cámara → ticket < 1.5s). |
| **Auditoría de fallback de cámara → Atlas → POS** | ✅ Verificado en esta sesión | El flujo `atlas.registrar_evento_fallback` → alerta al POS vía WebSocket (`ALERTA_CV_FALLBACK`) funciona correctamente y ya no bloquea el video (ver sección 1.1). |

**Recomendación de orden para Dev E:** dado que el sprint ya casi termina, priorizar (a) la caché de resiliencia SQLite —es la única pieza completamente ausente que el plan original marca como crítica— sobre (b) las pruebas de carga con Locust, que son más una validación de calidad que una funcionalidad faltante.

---

## 5. Notas sobre el commit de este cambio

- **No se incluyen** en el commit: `.mcp.json` (config local de MCP, cada dev debe crear el suyo), `yolov8n.pt` sueltos en raíz/`cv-worker/` (pesos de modelo, se regeneran solos al correr `ultralytics` por primera vez), `scratch/`, `test_cam0.jpg`, `ciel.json` (archivos de prueba de esta sesión), y `SetImagenesBuenas/productos para entrenar modelo/` (duplicados de imágenes ya organizadas en sus carpetas correspondientes).
- Se agregaron patrones a `.gitignore` para evitar que estos archivos vuelvan a aparecer como "untracked" en el futuro.
