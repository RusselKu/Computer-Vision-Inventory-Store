# Módulo de Visión por Computadora (Dev B)

Worker de visión asíncrono para el sistema POS con **OpenCV**, **YOLOv8** y **pyzbar** (con fallback a OpenCV BarcodeDetector).

---

## 🛠️ Funcionalidades Implementadas

1. **Captura y Preprocesamiento de Video:**
   - Lectura de webcam o stream RTSP a 1080p con OpenCV.
   - Cálculo dinámico de FPS y visualización HUD en tiempo real.

2. **Inferencia YOLOv8:**
   - Detección de la región delimitadora del producto (`bounding_box`) y nivel de confianza.

3. **Decodificación de Código de Barras (pyzbar / OpenCV):**
   - Recorte de la ROI (Region of Interest) dentro del bounding box de YOLO.
   - Ajustes de contraste (CLAHE), desenfoque Gaussiano y binarización adaptativa para decodificación rápida en condiciones de poca iluminación.

4. **Regla de los 5 Frames:**
   - Contador de frames consecutivos donde se detecta objeto por YOLO pero no se logra leer el código de barras.
   - Al llegar a 5 frames:
     1. Guarda el frame y metadatos en **MongoDB Atlas** (`pos_telemetria.eventos_vision`) para re-entrenamiento futuro.
     2. Envia payload con `"es_fallback": true` a `POST /api/v1/cv/deteccion` para alertar instantáneamente a la pantalla del cajero (Dev C) vía WebSocket.

5. **Modo de Pruebas y Simulación Integrado:**
   - Si no hay webcam conectada o estás probando sin códigos físicos, puedes interactuar mediante el teclado en vivo.

---

## 🚀 Cómo Ejecutar el Worker

### 1. Instalar dependencias

```bash
cd cv-worker
pip install -r requirements.txt
```

### 2. Configurar variables de entorno (Opcional)

Puedes copiar el archivo `.env.example` a `.env`:

```bash
cp .env.example .env
```

### 3. Iniciar el Worker

Asegúrate de que la API de FastAPI esté corriendo en `http://localhost:8000`:

```bash
python main.py
```

---

## ⌨️ Controles de Teclado en la Ventana de OpenCV

| Tecla | Acción |
|---|---|
| `S` | **Simular Detección de Producto:** Envía una Coca-Cola (`7501055312107`) escaneada al carrito activo. |
| `F` | **Simular Fallback:** Envía una alerta de producto no reconocido (5 frames) al POS del cajero. |
| `C` | **Crear Nueva Venta:** Solicita al backend un nuevo ID y Folio de venta de prueba. |
| `Q` | **Salir:** Cierra la ventana y detiene el worker. |
