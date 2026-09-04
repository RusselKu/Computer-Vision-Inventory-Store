# Sprint de 1.5 semanas — POS con reconocimiento de producto

**Duración:** 8 días hábiles (lunes a miércoles de la semana 2)
**Equipo:** 5 desarrolladores
**Stack:** 100% open source / capas gestionadas gratuitas — Supabase (Postgres + Auth + Storage + Realtime), MongoDB Atlas (free tier), Docker local, cámara 1080p + GPU local para inferencia

---

## Cambios de stack respecto al plan original

| Original | Ahora | Motivo |
|---|---|---|
| PostgreSQL propio en Docker | **Supabase** | Da Postgres + Auth + Storage + Realtime sin montar infraestructura |
| MongoDB propio en Docker | **MongoDB Atlas (free tier)** | Cluster gestionado, cero mantenimiento en el sprint |
| Redis en servidor | **Redis local (Docker) o caché en memoria del proceso** | Solo se corre en la máquina de desarrollo, no en producción todavía |
| MinIO | **Supabase Storage** | Ya viene incluido con el proyecto Supabase, evita un servicio más |
| Power BI | **Metabase u open source Superset (self-hosted)** | Mantiene todo open source |
| VPS + Kubernetes | **Fuera de este sprint** | Se corre todo en la computadora local con GPU; el despliegue a servidor queda para una fase 2 |
| JWT propio | **Supabase Auth** | Ya trae JWT y manejo de sesiones |

---

## Equipo (5 desarrolladores)

| Rol | Responsable de |
|---|---|
| **Dev A — Backend core** | API FastAPI, integración con Supabase (esquemas, triggers de stock), endpoints `agregar_item`, `eliminar_item`, `cerrar_venta` |
| **Dev B — Visión por computadora** | Captura con OpenCV (cámara 1080p), inferencia YOLOv8 en GPU local, lectura de códigos de barras (pyzbar), lógica de fallback |
| **Dev C — Frontend POS** | Pantalla de punto de venta: panel de reconocimiento, carrito, ticket, cobro |
| **Dev D — Frontend Dashboard** | Dashboard de tracking + analítica, conexión en tiempo real vía Supabase Realtime |
| **Dev E — Integración / DevOps** | Setup de Atlas y Supabase, Docker Compose local, caché de resiliencia, pruebas de carga y latencia |

---

## Día 1 — Setup y modelado de datos
*Todo el equipo*

- Crear proyecto en **Supabase**: esquemas `productos`, `ventas`, `detalle_ventas`, `inventario` + trigger de descuento de stock al cerrar venta.
- Crear cluster en **MongoDB Atlas**: colecciones `logs_sistema` y `eventos_vision` (frames no reconocidos, detecciones de baja confianza).
- Repositorio Git + `docker-compose.yml` local con FastAPI, Redis y el worker de visión.
- Dev E deja el entorno corriendo para que A, B, C y D puedan trabajar en paralelo desde el día 2.

## Días 2-3 — Backend y visión en paralelo

**Dev A (backend):**
- Endpoints del carrito sobre Supabase (REST vía `supabase-py` o PostgREST directo).
- Trigger SQL en Supabase que descuenta stock al insertar en `detalle_ventas`.

**Dev B (visión):**
- Captura de video 1080p con OpenCV (`cv2.VideoCapture`), preprocesamiento ligero (contraste/iluminación).
- Inferencia con YOLOv8 preentrenado usando la GPU local (CUDA) para detectar producto + bounding box.
- Lectura de código de barras/QR con `pyzbar` dentro del bounding box.
- Fallback: si no lee en 5 frames, emite evento a `eventos_vision` (Atlas) y dispara alerta al POS para captura manual.

## Día 4 — Integración CV ↔ Backend

- Dev A + Dev B conectan el resultado de visión con el endpoint `agregar_item` (vía WebSocket o polling corto).
- Dev E implementa la caché de resiliencia: si Supabase no responde, las ventas se guardan en SQLite local y se reenvían al reconectar.

## Días 4-5 — Frontend (en paralelo con integración)

**Dev C (POS):**
- Pantalla de punto de venta con panel de reconocimiento de producto, carrito editable, resumen de pago y emisión de ticket (ya prototipada).

**Dev D (dashboard):**
- Dashboard de tracking conectado a Supabase Realtime: métricas de envíos/stock se actualizan en vivo cuando el POS vende o el trigger descuenta inventario.
- Vista de ticket individual con el movimiento de inventario asociado.

## Día 6 — Analítica ligera

- Dev A/E: script Python (pandas) que lee Supabase + Atlas y arma un data mart simple dentro del mismo proyecto Supabase (tablas agregadas, sin Airflow — se corre con `cron` local por ahora).
- Detección de anomalías simple con Z-score sobre ventas diarias.
- Conectar **Metabase** (self-hosted, open source) a Supabase para: top 10 productos, horas pico, alertas de anomalías.

## Día 7 — Pruebas

- Dev E: prueba de carga básica con **Locust** sobre los endpoints del POS.
- Medir latencia cámara → ticket (objetivo: menor a 1.5 segundos) usando la GPU local.
- Auditar que los eventos de fallo de cámara en Atlas disparen correctamente el fallback manual en el POS.

## Día 8 (medio día) — Pulido y entrega

- Ajustes finales de UI, revisión cruzada entre los 5 devs.
- Documentación corta: cómo levantar el entorno local (Docker Compose + variables de Supabase/Atlas) y cómo correr el modelo YOLOv8 con GPU.

---

## Notas

- El despliegue a un servidor (VPS, Traefik, autoscaling) queda explícitamente fuera de este sprint — todo corre en la computadora local con GPU, apuntando a Supabase y Atlas en la nube.
- Si el modelo YOLOv8 preentrenado no reconoce bien los productos del catálogo, el fallback de código de barras cubre la operación diaria mientras se recolectan frames en `eventos_vision` para un fine-tuning posterior.
- Con 5 personas trabajando en paralelo desde el día 2, la ruta crítica es la integración CV↔backend (día 4) — conviene que Dev A y Dev B se sincronicen desde el día 1 sobre el contrato de datos (formato del evento de detección).
