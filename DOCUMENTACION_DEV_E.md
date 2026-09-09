# Dev E — Resiliencia, operación y validación

## Alcance implementado

El cierre de un carrito existente se registra primero en SQLite y después se envía
a `fn_cerrar_venta` en Supabase. La cola sobrevive al reinicio de la API. Se utiliza
SQLite por su persistencia local; Redis continúa disponible en Compose, pero no
es la fuente de verdad ni almacena tickets.

**No es un POS completamente offline.** Durante una caída se pueden consultar los
carritos que esta API guardó previamente y solicitar su cierre. Crear productos,
crear ventas y editar carritos necesitan Supabase. Un cierre pendiente no confirma
stock, no descuenta inventario local y no autoriza mostrar una venta como completada.

### Contrato de cierre

`POST /api/v1/ventas/{id}/cerrar` conserva el cuerpo `{"metodo_pago":"efectivo"}`.

| Respuesta | Significado |
|---|---|
| 200, `success: true`, `sync_status: synced` | Supabase confirmó el cierre. |
| 202, `success: false`, `sync_status: pending` | Solicitud persistida localmente; falta confirmación. |
| 409 | Conflicto de stock, carrito modificado, venta cancelada o método incompatible. Requiere revisión. |
| 503 | Fallo de conexión en una operación que no puede resolverse localmente. |

Repetir el cierre de la misma venta con el mismo método devuelve la confirmación
guardada. Un método diferente produce 409. Un cierre pendiente bloquea modificaciones
del carrito a través de esta API. El POS muestra el pendiente y espera la confirmación;
no hay una segunda llamada a un procesador de pagos: el sistema solo registra el método.

El sincronizador reintenta fallos de transporte y errores temporales conocidos con
espera creciente (hasta 300 segundos). Los rechazos de negocio no se reintentan
automáticamente. Antes de cerrar compara el total y las líneas con el ticket guardado.
Si se pierde la respuesta después del commit, consulta el estado remoto y reconoce
el cierre previo. La protección final contra doble descuento depende del bloqueo y
validación de estado de la función atómica existente `fn_cerrar_venta` de Dev A.

Operar **una instancia de API, un proceso Uvicorn y un volumen SQLite por caja**.
No compartir esta base local por NFS ni ejecutar varios backends que modifiquen el mismo
carrito. Las escrituras externas a esta API no están cubiertas por su bloqueo local.
La protección frente a esas escrituras requiere transacciones adicionales en Supabase.

### Diagnóstico

- `GET /live`: proceso vivo, sin depender de Internet; usado por Docker.
- `GET /health`: conexión a Supabase; devuelve `status: degraded` si falla.
- `GET /api/v1/resiliencia`: contadores y hasta 100 operaciones no sincronizadas,
  con ID, estado, intentos y error. No devuelve credenciales ni frames.
- Estados de cola: `pending`, `processing`, `synced`, `rejected`.
- Un proceso que muere mientras sincroniza deja una reserva recuperable después de 120 s.
- Después de un rechazo, revisar carrito/stock y repetir el cierre explícitamente.
  Si el método remoto difiere, conciliar primero; no registrar un segundo cobro.

## Arranque local

Desde la raíz del repositorio, crear `.env` a partir de `.env.example` si aún no existe.
Configurar las credenciales de Supabase por el canal privado del equipo.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

En otra terminal:

```powershell
cd frontend-dashboard
npm ci
npm run dev
```

En otra terminal para la cámara/GPU (instalar sus dependencias en el entorno del worker):

```powershell
python -m pip install -r cv-worker/requirements.txt
python cv-worker/main.py
```

El worker usa la venta seleccionada al arrancar. Después de cambiar de venta,
usar su tecla `C` para resincronizar el ID. La sincronización automática entre cajas
no forma parte de esta entrega.

Alternativamente, backend y Redis con Docker:

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Frontend y worker se ejecutan en el host. SQLite persiste en el volumen `pos-data`,
montado en `/data`. `docker compose down` conserva el volumen; **no usar `down -v`
si hay operaciones pendientes**. Fuera de Docker, la ruta por defecto es
`data/pos-outbox.sqlite3`, relativa al directorio de arranque. Usar siempre la raíz
o configurar una ruta absoluta en `OFFLINE_DB_PATH`.

Variables añadidas: `OFFLINE_DB_PATH`, `SYNC_INTERVAL_SECONDS` (5 por defecto),
`SUPABASE_TIMEOUT_SECONDS` (3 por defecto). Para respaldar SQLite, detener la API
y copiar el directorio de datos completo; conservar también sus archivos WAL/SHM
si existen. No borrar filas pendientes para resolver un error.

## Atlas

### Alternativa elegida: MongoDB local

El equipo confirmó que no existe una instancia Atlas. Compose incluye ahora
`mongodb`, con MongoDB 8.0 y volumen persistente `mongo-data`. El puerto se publica
solo en `127.0.0.1`; esta configuración de desarrollo no usa autenticación y no debe
exponerse a otros equipos. El worker continúa ejecutándose en el host.

```env
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DB_NAME=pos_telemetria
MONGODB_COLLECTION=eventos_vision
```

Con Docker instalado y abierto, desde la raíz:

```powershell
docker compose up -d mongodb
docker compose ps mongodb
.venv/Scripts/python.exe devops/check_atlas.py --initialize --write-probe
```

El resultado esperado es `logs_sistema: OK` y `eventos_vision: OK`. El nombre del
script se conserva, pero funciona tanto con MongoDB local como con Atlas.
`docker compose restart mongodb` conserva los datos. No usar `down -v` si se desea
conservar la telemetría. Cada compañero tendrá su propia base local; no se comparte
automáticamente entre computadoras.

### Si después se utiliza Atlas

Configurar `MONGODB_URI` y `MONGODB_DB_NAME=pos_telemetria` en `.env`.
El script usa esas variables y no imprime la URI.

```powershell
.venv/Scripts/python.exe devops/check_atlas.py
.venv/Scripts/python.exe devops/check_atlas.py --initialize --write-probe
```

El segundo comando crea `logs_sistema` y `eventos_vision` si faltan, añade índices,
comprueba escritura/lectura y elimina únicamente los documentos de prueba propios.
El logger del worker comprueba ahora el ping real antes de anunciar conexión.
Los frames del worker siguen enviándose a `eventos_vision`; `logs_sistema` queda
disponible para logs operativos. Si Atlas está caído, el logger actual solo escribe
el fallo en consola: esta cola SQLite protege cierres, no frames de telemetría.

## Pruebas

```powershell
.venv/Scripts/python.exe -m pytest -q
```

La suite por defecto es aislada: caída de red, reinicio, respuesta perdida después
del commit, reintentos, conflictos, reserva concurrente, caché, contrato HTTP 202 y
fallback WebSocket. No usa Supabase ni descuenta inventario real.
CI ejecuta esta suite, valida Compose y construye backend y dashboard.

Para la suite original, configurar **un proyecto Supabase exclusivo de pruebas** con
el esquema, función atómica y seed de Dev A; sus pruebas escriben ventas y descuentan stock:

```powershell
.venv/Scripts/python.exe -m pytest -m integration backend/tests/test_api.py -v
```

### Carga

Con la API apuntando a ese entorno de pruebas:

```powershell
.venv/Scripts/python.exe -m locust -f devops/locustfile.py --host http://localhost:8000
```

Abrir la interfaz de Locust en el puerto 8089 y comenzar con 5 usuarios. El escenario
consulta productos y crea/agrega/cancela carritos; no cierra ventas ni descuenta stock.
Las ventas canceladas quedan como evidencia en el entorno de pruebas. Para CSV:

```powershell
New-Item -ItemType Directory -Force reports
.venv/Scripts/python.exe -m locust -f devops/locustfile.py --host http://localhost:8000 --headless -u 10 -r 2 -t 60s --csv reports/load
```

Revisar tasa de errores y percentiles, no solo promedio. Configurar `LOAD_BARCODE`
si el producto del seed cambió. Un corte abrupto del proceso puede dejar carritos abiertos.

### Latencia

La prueba sintética crea una venta por muestra y la cancela al terminar:

```powershell
.venv/Scripts/python.exe devops/measure_latency.py --samples 30
```

Genera `reports/latency.csv` y calcula p95 de detección HTTP → WebSocket → consulta
del carrito. **Excluye cámara, IA y render**; no acredita por sí sola el objetivo total.

Para medir con cámara, agregar `VITE_MEASURE_LATENCY=true` a
`frontend-dashboard/.env.local` y reiniciar Vite. Ejecutar worker, API y navegador
en el mismo equipo (mismo reloj). Usar productos físicos y mantener el POS visible.
El navegador guarda muestras en `window.POS_LATENCY_SAMPLES`. Exportar el resultado
de `JSON.stringify(window.POS_LATENCY_SAMPLES)` a `reports/camera-latency.json` y ejecutar:

```powershell
.venv/Scripts/python.exe devops/summarize_camera_latency.py reports/camera-latency.json
```

La medición empieza cuando el loop recibe el frame y termina después de actualizar
el carrito y dos callbacks de animación del navegador. Incluye inferencia y red;
excluye buffers físicos anteriores a la entrega del frame. Es una aproximación al
render, no una medición óptica del monitor. Las teclas de simulación no cuentan como
cámara real. Exige al menos 30 muestras y p95 < 1500 ms para devolver código de éxito.

## Validación de entrega pendiente en el entorno del equipo

Verificado localmente durante esta implementación: 15 pruebas aisladas aprobadas,
compilación del dashboard y prueba en navegador con API simulada (captura manual,
fallback, cierre pendiente, confirmación posterior y ticket). El archivo de Locust
carga correctamente y ambos YAML se pueden analizar. Docker no está instalado en
este entorno y no hay credenciales de los servicios remotos configuradas; no se
reportan resultados reales de carga, Atlas ni cámara.

1. Ejecutar el escenario con las credenciales de pruebas de Supabase y Atlas.
2. Cargar un carrito, cortar la red, solicitar cierre y comprobar HTTP 202 y aviso.
3. Reiniciar la API usando la misma base SQLite; restablecer red y comprobar una sola
   venta completada y un solo descuento de stock. Revisar `/api/v1/resiliencia`.
4. Provocar stock insuficiente y comprobar estado `rejected` y ausencia de reintentos.
5. Medir carga y cámara real; adjuntar CSV/JSON con equipo, usuarios, duración y p95.

La validación local con dobles de prueba no certifica la función SQL remota, permisos,
rendimiento de GPU, persistencia en Atlas ni ejecución de Docker en otra máquina.

## Actualización: validación de Docker y MongoDB local

- WSL y Docker operativos.
- Backend, Redis y MongoDB iniciados con Docker Compose y estado healthy.
- Colecciones logs_sistema y eventos_vision: escritura, lectura y eliminación de documentos de prueba correctas.
- Documento MongoDB conservado tras reiniciar su contenedor; documento de prueba eliminado después.
- Archivo de prueba del volumen /data del backend conservado tras reiniciar; eliminado después.
- API en Docker conectada a Supabase, comprobada por /health.
- No se crearon ventas ni se modificó stock durante estas pruebas.
- Los tres servicios quedan encendidos. Cámara y emisión real de frames quedan a cargo del compañero.
