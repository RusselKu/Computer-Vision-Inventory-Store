import cv2
import time
import requests
import logging
from uuid import UUID

from config import (
    API_URL, CAMERA_INDEX, USE_SIMULATION, VENTA_ID, YOLO_MODEL_PATH, YOLO_CONF_THRESHOLD,
    FALLBACK_FRAME_THRESHOLD, COOL_DOWN_SECONDS
)
from barcode_reader import decodificar_codigo_barras
from yolo_detector import DetectorYOLO
from atlas_logger import AtlasLogger

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CVWorkerMain")


def obtener_o_crear_venta_activa():
    """Obtiene una venta activa existente o crea una nueva para pruebas de escaneo."""
    if VENTA_ID:
        return VENTA_ID

    logger.info(f"Conectando a API en {API_URL} para crear/obtener venta activa de prueba...")
    try:
        res = requests.post(f"{API_URL}/ventas", timeout=3)
        if res.status_code == 201:
            nueva_venta = res.json()
            v_id = nueva_venta["id"]
            folio = nueva_venta.get("folio", "")
            logger.info(f"✓ Venta activa de prueba creada: {v_id} (Folio: {folio})")
            return v_id
    except Exception as e:
        logger.warning(f"No se pudo conectar al Backend API ({e}). Usando UUID ficticio para pruebas de UI.")

    return "00000000-0000-0000-0000-000000000001"


def enviar_deteccion_api(payload):
    """Envía el contrato JSON a POST /api/v1/cv/deteccion en FastAPI."""
    try:
        url = f"{API_URL}/cv/deteccion"
        res = requests.post(url, json=payload, timeout=3)
        if res.status_code == 200:
            data = res.json()
            logger.info(f"✓ API Respuesta: {data.get('status')} - {data.get('mensaje')}")
            return data
        else:
            logger.error(f"✗ API Error ({res.status_code}): {res.text}")
    except Exception as e:
        logger.error(f"✗ Error al enviar datos a la API: {e}")
    return None


def main():
    logger.info("==========================================================")
    logger.info("   Worker de Visión por Computadora — POS CV System       ")
    logger.info("==========================================================")

    # 1. Inicializar Venta, Detector YOLO y Logger de Atlas
    venta_id_actual = obtener_o_crear_venta_activa()
    yolo = DetectorYOLO(model_path=YOLO_MODEL_PATH, conf_thresh=YOLO_CONF_THRESHOLD)
    atlas = AtlasLogger()

    # 2. Iniciar Captura de Video (o modo simulación estricto)
    cap = None
    if not USE_SIMULATION and CAMERA_INDEX >= 0:
        cap = cv2.VideoCapture(CAMERA_INDEX)
        if not cap.isOpened():
            logger.error(f"No se pudo abrir la cámara index {CAMERA_INDEX}.")
            cap = None

    if cap is None:
        logger.info("▶ MODO SIMULACIÓN ACTIVO (La cámara de la laptop no se activará).")
        logger.info("  Presione 'S' para simular lectura de producto, 'F' para fallback.")

    logger.info("\nControles de Teclado:")
    logger.info("  [S] Simular lectura exitosa (Coca-Cola / Sabritas)")
    logger.info("  [F] Simular fallback (Alerta de 5 frames sin código)")
    logger.info("  [C] Crear nueva venta en el Backend")
    logger.info("  [Q] Salir\n")

    # Contadores de estado
    consecutive_no_barcode_frames = 0
    last_action_time = 0
    fps_start_time = time.time()
    fps_counter = 0
    current_fps = 0

    while True:
        ret, frame = cap.read() if cap is not None and cap.isOpened() else (True, None)

        # Si no hay cámara física disponible, crear un canvas sintético para pruebas de laboratorio
        if frame is None:
            import numpy as np
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[:] = (30, 35, 45)
            # Dibujar área simulación
            cv2.rectangle(frame, (180, 100), (460, 380), (60, 65, 80), -1)
            cv2.putText(frame, "MODO SIMULACION ACTIVO (Sin camara)", (40, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 255), 2)
            cv2.putText(frame, "Presione 'S' = Coca-Cola | 'F' = Fallback 5-frames", (40, 420),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.putText(frame, "Presione 'C' = Nueva Venta | 'Q' = Salir", (40, 445),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

        # Cálculo de FPS
        fps_counter += 1
        if time.time() - fps_start_time >= 1.0:
            current_fps = fps_counter
            fps_counter = 0
            fps_start_time = time.time()

        now = time.time()
        cooldown_activo = (now - last_action_time) < COOL_DOWN_SECONDS

        # 3. Inferencia de YOLOv8
        detecciones = yolo.detectar_objetos(frame)

        detecto_objeto = len(detecciones) > 0
        codigo_detectado = None
        bbox_actual = None
        clase_yolo = None
        confianza_yolo = 0.0

        if detecto_objeto and not cooldown_activo:
            obj = detecciones[0]
            bbox_actual = obj["bbox"]
            clase_yolo = obj["clase"]
            confianza_yolo = obj["confianza"]

            # 4. Intentar decodificar código de barras dentro del bounding box
            codigo_detectado = decodificar_codigo_barras(frame, bbox=bbox_actual)

            if codigo_detectado:
                # Detección Exitosa con pyzbar / OpenCV!
                logger.info(f"★ ¡Código de Barras Leído!: {codigo_detectado} (Clase: {clase_yolo})")
                consecutive_no_barcode_frames = 0
                last_action_time = now

                payload = {
                    "venta_id": venta_id_actual,
                    "codigo_barras": codigo_detectado,
                    "clase_yolo": clase_yolo,
                    "confianza": confianza_yolo,
                    "bounding_box": bbox_actual,
                    "es_fallback": False
                }
                enviar_deteccion_api(payload)

            else:
                # Regla de los 5 Frames: Se detecta objeto pero no se puede leer el código de barras
                consecutive_no_barcode_frames += 1
                logger.info(f"Frame {consecutive_no_barcode_frames}/{FALLBACK_FRAME_THRESHOLD} sin código de barras...")

                if consecutive_no_barcode_frames >= FALLBACK_FRAME_THRESHOLD:
                    logger.warning("⚠️ REGLA DE 5 FRAMES ALCANZADA: Activando Fallback e informando al POS...")
                    last_action_time = now

                    msg_err = f"Producto no reconocido tras {FALLBACK_FRAME_THRESHOLD} frames consecutivos."
                    
                    # 1) Registrar frame en MongoDB Atlas para re-entrenamiento
                    atlas.registrar_evento_fallback(
                        venta_id=venta_id_actual,
                        frame=frame,
                        bounding_box=bbox_actual,
                        confianza=confianza_yolo,
                        mensaje_error=msg_err
                    )

                    # 2) Enviar alerta de fallback al Backend
                    payload = {
                        "venta_id": venta_id_actual,
                        "confianza": confianza_yolo,
                        "bounding_box": bbox_actual,
                        "es_fallback": True,
                        "mensaje_error": msg_err
                    }
                    enviar_deteccion_api(payload)

                    consecutive_no_barcode_frames = 0

        # Reset contador si no hay objeto en la imagen
        if not detecto_objeto:
            consecutive_no_barcode_frames = 0

        # --- 5. Renderizado de Interfaz Visual (HUD Overlay) ---
        # Dibujar bounding boxes y métricas sobre el frame
        if bbox_actual:
            x, y, w, h = bbox_actual["x"], bbox_actual["y"], bbox_actual["w"], bbox_actual["h"]
            color = (0, 255, 0) if codigo_detectado else (0, 165, 255)
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            
            label = f"{clase_yolo} {int(confianza_yolo*100)}%"
            if codigo_detectado:
                label += f" | {codigo_detectado}"
            cv2.putText(frame, label, (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Barra superior de estado
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 35), (20, 25, 35), -1)
        cv2.putText(frame, f"POS CV Worker | FPS: {current_fps}", (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        cv2.putText(frame, f"Venta ID: {str(venta_id_actual)[:8]}...", (220, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 220, 255), 1)

        # Contador de frames de fallback
        if consecutive_no_barcode_frames > 0:
            cv2.putText(frame, f"Sin barra: {consecutive_no_barcode_frames}/{FALLBACK_FRAME_THRESHOLD}",
                        (frame.shape[1] - 150, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)

        # Mostrar ventana OpenCV
        cv2.imshow("Punto de Venta — Reconocimiento de Producto (Dev B)", frame)

        # --- 6. Manejo de Entradas de Teclado ---
        key = cv2.waitKey(30) & 0xFF
        if key == ord('q') or key == 27:
            logger.info("Cerrando worker de visión...")
            break
        elif key == ord('s'):
            # Tecla S: Simular escaneo de Coca-Cola (7501055312107)
            logger.info("Simulando lectura manual del producto Coca-Cola 600ml...")
            payload = {
                "venta_id": venta_id_actual,
                "codigo_barras": "7501055312107",
                "clase_yolo": "coca_cola",
                "confianza": 0.98,
                "bounding_box": {"x": 150, "y": 100, "w": 200, "h": 300},
                "es_fallback": False
            }
            enviar_deteccion_api(payload)
            last_action_time = time.time()
        elif key == ord('f'):
            # Tecla F: Simular disparo del Fallback (Alerta manual al POS)
            logger.info("Simulando disparo de alerta de Fallback...")
            payload = {
                "venta_id": venta_id_actual,
                "confianza": 0.70,
                "bounding_box": {"x": 150, "y": 100, "w": 200, "h": 300},
                "es_fallback": True,
                "mensaje_error": "Simulación manual de producto no reconocido tras 5 frames."
            }
            enviar_deteccion_api(payload)
            last_action_time = time.time()
        elif key == ord('c'):
            # Tecla C: Crear una nueva venta activa
            venta_id_actual = obtener_o_crear_venta_activa()

    if cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
