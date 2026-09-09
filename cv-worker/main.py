import os
import cv2
import time
import requests
import logging
from uuid import UUID

import concurrent.futures
from config import (
    API_URL, CAMERA_INDEX, USE_SIMULATION, VENTA_ID, YOLO_MODEL_PATH, YOLO_CONF_THRESHOLD,
    FALLBACK_FRAME_THRESHOLD, COOL_DOWN_SECONDS, PROCESS_EVERY_N_FRAMES, SHOW_DEBUG_WINDOW
)
from barcode_reader import decodificar_codigo_barras
from yolo_detector import DetectorYOLO
from atlas_logger import AtlasLogger
from vector_engine import VectorEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CVWorkerMain")

import threading

stream_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
api_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
_last_stream_time = 0.0

class ThreadedCamera:
    """Captura fotogramas continuamente en un hilo dedicado para garantizar latencia CERO y eliminar lag de buffer."""
    def __init__(self, src=1, api_pref=cv2.CAP_ANY):
        self.cap = cv2.VideoCapture(src, api_pref)
        self.ret = False
        self.frame = None
        self.stopped = False
        if self.cap.isOpened():
            self.ret, self.frame = self.cap.read()
        self.thread = threading.Thread(target=self.update, args=(), daemon=True)
        self.thread.start()

    def update(self):
        while not self.stopped:
            if not self.cap.isOpened():
                break
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.ret, self.frame = ret, frame
            else:
                time.sleep(0.005)

    def read(self):
        return (self.ret, self.frame.copy()) if (self.ret and self.frame is not None) else (False, None)

    def isOpened(self):
        return self.cap.isOpened() and not self.stopped

    def release(self):
        self.stopped = True
        if self.cap:
            self.cap.release()


def enviar_frame_stream_async(frame_to_send):
    """Envía el fotograma procesado a la API para el stream MJPEG del Dashboard POS con rate limiting."""
    global _last_stream_time
    now = time.time()
    if now - _last_stream_time < 0.066:  # Limitar transmisión a max ~15 FPS para reducir carga CPU
        return
    _last_stream_time = now

    try:
        # Reducir resolución y compresión JPEG para transmisión ultra liviana
        small_frame = cv2.resize(frame_to_send, (480, 360))
        success, jpeg = cv2.imencode('.jpg', small_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 45])
        if success:
            jpeg_bytes = jpeg.tobytes()
            stream_executor.submit(
                requests.post,
                f"{API_URL}/cv/stream-frame",
                data=jpeg_bytes,
                headers={'Content-Type': 'image/jpeg'},
                timeout=0.1
            )
    except Exception:
        pass


def obtener_o_crear_venta_activa():
    """Obtiene una venta activa existente (del POS en navegador) o crea una nueva."""
    if VENTA_ID:
        return VENTA_ID

    logger.info(f"Conectando a API en {API_URL} para buscar la venta activa del POS...")
    try:
        # 1. Buscar si hay una venta abierta actualmente en el POS
        res_list = requests.get(f"{API_URL}/ventas?estado=abierta&limit=1", timeout=3)
        if res_list.status_code == 200:
            ventas_abiertas = res_list.json()
            if ventas_abiertas and len(ventas_abiertas) > 0:
                v = ventas_abiertas[0]
                logger.info(f"✓ Sincronizado con la Venta Activa del POS: {v['id']} (Folio: {v.get('folio')})")
                return v["id"]

        # 2. Si no hay venta abierta, crear una nueva
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


def abrir_camara(index):
    """Abre la cámara probando DirectShow primero (óptimo y rápido en Windows) y luego backend estándar."""
    try:
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            ret, test_frame = cap.read()
            if ret and test_frame is not None:
                return cap
            cap.release()
    except Exception:
        pass

    try:
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            ret, test_frame = cap.read()
            if ret and test_frame is not None:
                return cap
            cap.release()
    except Exception:
        pass

    return None


def main():
    logger.info("==========================================================")
    logger.info("   Worker de Visión por Computadora — POS CV System       ")
    logger.info("==========================================================")

    # 1. Inicializar Venta, Detector YOLO, Logger de Atlas y Motor Vectorial ResNet18
    venta_id_actual = obtener_o_crear_venta_activa()
    yolo = DetectorYOLO(model_path=YOLO_MODEL_PATH, conf_thresh=YOLO_CONF_THRESHOLD)
    atlas = AtlasLogger()
    vector_engine = VectorEngine()

    # 2. Iniciar Captura de Video con Auto-Detección y DirectShow
    cap = None
    cam_index_actual = CAMERA_INDEX

    if not USE_SIMULATION and cam_index_actual >= 0:
        logger.info(f"Conectando a la cámara configurada (Index {cam_index_actual})...")
        cap = abrir_camara(cam_index_actual)
        if cap is None:
            logger.warning(f"No se pudo abrir cámara en index {cam_index_actual}. Buscando en otros índices disponibles [1, 0, 2]...")
            for fallback_idx in [1, 0, 2]:
                if fallback_idx != cam_index_actual:
                    cap = abrir_camara(fallback_idx)
                    if cap is not None:
                        cam_index_actual = fallback_idx
                        logger.info(f"✓ ¡Cámara detectada y conectada automáticamente en Index {fallback_idx}!")
                        break

    if cap is not None:
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(f"✓ Cámara activa en Index {cam_index_actual} ({actual_w}x{actual_h}). Transmitiendo video en vivo.")
    else:
        logger.info("▶ MODO SIMULACIÓN ACTIVO (Presione 'T' para activar cámara física).")
        logger.info("  Presione 'S' para simular lectura de producto, 'V' para vectorización, 'F' para fallback.")

    logger.info("\nControles de Teclado:")
    logger.info("  [S] Simular lectura exitosa por código de barras (Sabritas / Doritos)")
    logger.info("  [V] Simular reconocimiento VECTORIAL por visión (ResNet18 Embeddings)")
    logger.info("  [F] Simular fallback (Alerta de 5 frames sin código)")
    logger.info("  [C] Crear nueva venta en el Backend")
    logger.info("  [Q] Salir\n")

    # Contadores de estado
    consecutive_no_barcode_frames = 0
    last_action_time = 0
    fps_start_time = time.time()
    fps_counter = 0
    current_fps = 0
    frame_skip_count = 0
    last_detecciones = []

    sim_product_index = 0
    sim_productos = [
        {"codigo": "7501055312107", "clase": "coca_cola", "nombre": "Coca-Cola Original 600ml", "img": "SetImagenesBuenas/CocaColaSet/Cocacolanormal.jpg"},
        {"codigo": "7501000111203", "clase": "sabritas", "nombre": "Sabritas Sal 45g", "img": "SetImagenesBuenas/SabritasPapas/Papasnormal.png"},
        {"codigo": "7501000122209", "clase": "ruffles", "nombre": "Ruffles Queso 50g", "img": "SetImagenesBuenas/RuflesQueso/Rufles1.jpg"},
        {"codigo": "7501020512110", "clase": "agua", "nombre": "Agua e·pura Purificada 1L", "img": "SetImagenesBuenas/BoteAgua/AguaEpura.jpg"},
        {"codigo": "7501011115481", "clase": "chokis", "nombre": "Galletas Chokis 76g", "img": "SetImagenesBuenas/GalletasChokis/Chokis1.png"},
    ]

    while True:
        if cap is not None and cap.isOpened():
            ret, frame = cap.read()
            if not ret or frame is None:
                frame = None
        else:
            frame = None

        # Dev E: start at delivery to the processing loop (excludes camera hardware buffering).
        captured_at_ms = time.time() * 1000
        measurement_source = 'camera' if frame is not None else 'simulation'

        if frame is not None:
            frame = cv2.resize(frame, (640, 480))

        # Si no hay cámara física disponible, crear un canvas sintético para pruebas de laboratorio
        if frame is None:
            import numpy as np
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[:] = (30, 35, 45)
            # Dibujar área simulación
            cv2.rectangle(frame, (180, 100), (460, 380), (60, 65, 80), -1)
            cv2.putText(frame, "MODO SIMULACION ACTIVO (Sin camara)", (40, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 255), 2)
            cv2.putText(frame, "Presione 'S' = Codigo | 'V' = Vector Embeddings | 'F' = Fallback", (30, 420),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
            cv2.putText(frame, "Presione 'C' = Nueva Venta | 'Q' = Salir", (30, 445),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

        # Cálculo de FPS
        fps_counter += 1
        if time.time() - fps_start_time >= 1.0:
            current_fps = fps_counter
            fps_counter = 0
            fps_start_time = time.time()

        now = time.time()
        cooldown_activo = (now - last_action_time) < COOL_DOWN_SECONDS

        # 3. Inferencia de YOLOv8 (Frame Skipping: Ejecutar 1 de cada N fotogramas)
        frame_skip_count += 1
        es_frame_de_proceso = (frame_skip_count % PROCESS_EVERY_N_FRAMES == 0)
        if es_frame_de_proceso:
            detecciones = yolo.detectar_objetos(frame)
            last_detecciones = detecciones
        else:
            detecciones = last_detecciones

        detecto_objeto = len(detecciones) > 0
        codigo_detectado = None
        bbox_actual = None
        clase_yolo = None
        confianza_yolo = 0.0

        # Dibujar el bbox en TODOS los fotogramas (barato) para que el HUD no parpadee,
        # aunque el reconocimiento pesado solo corra en frames de proceso.
        if detecto_objeto:
            obj = detecciones[0]
            bbox_actual = obj["bbox"]
            clase_yolo = obj["clase"]
            confianza_yolo = obj["confianza"]

        # El reconocimiento pesado (codigo de barras + vector ResNet18) corre SOLO en frames de proceso,
        # sincronizado con YOLO, para no duplicar inferencia GPU en cada fotograma y evitar trabarse al mover el producto.
        if detecto_objeto and not cooldown_activo and es_frame_de_proceso:
            # 4. Intentar decodificar código de barras primero
            codigo_detectado = decodificar_codigo_barras(frame, bbox=bbox_actual)

            # 5. Si no hay código de barras, RECONOCER VISUALMENTE POR VECTOR DE EMBEDDINGS (ResNet18 / Supabase)
            reconocimiento_visual_match = None
            if not codigo_detectado and bbox_actual:
                # Recortar ROI del producto detectado
                x, y, w, h = bbox_actual["x"], bbox_actual["y"], bbox_actual["w"], bbox_actual["h"]
                roi = frame[max(0, y):max(0, y+h), max(0, x):max(0, x+w)]
                if roi.size > 0:
                    vec = vector_engine.extraer_vector(roi)
                    match_data, sim_score = vector_engine.buscar_producto_por_vector(vec, umbral_similitud=0.78)
                    if match_data:
                        reconocimiento_visual_match = {
                            "codigo": match_data["codigo"],
                            "nombre": match_data["nombre"],
                            "clase": match_data.get("clase", clase_yolo),
                            "sim": sim_score,
                            "vector": vec.tolist() if vec is not None else None
                        }

            if codigo_detectado:
                # Detección Exitosa por Código de Barras
                logger.info(f"★ ¡Código de Barras Leído!: {codigo_detectado} (Clase: {clase_yolo})")
                consecutive_no_barcode_frames = 0
                last_action_time = now

                payload = {
                    "venta_id": venta_id_actual,
                    "captured_at_ms": captured_at_ms,
                    "measurement_source": measurement_source,
                    "codigo_barras": codigo_detectado,
                    "clase_yolo": clase_yolo,
                    "confianza": confianza_yolo,
                    "bounding_box": bbox_actual,
                    "es_fallback": False
                }
                api_executor.submit(enviar_deteccion_api, payload)

            elif reconocimiento_visual_match:
                # Detección Exitosa 100% VISUAL POR VECTOR DE EMBEDDINGS (Sin código de barras)
                codigo_visual = reconocimiento_visual_match["codigo"]
                nombre_visual = reconocimiento_visual_match["nombre"]
                sim_visual = reconocimiento_visual_match["sim"]
                
                logger.info(f"★ ¡RECONOCIMIENTO VISUAL VECTORIAL EXITOSO!: '{nombre_visual}' (Clase: {clase_yolo}, Similitud: {round(sim_visual*100, 1)}%)")
                consecutive_no_barcode_frames = 0
                last_action_time = now

                payload = {
                    "venta_id": venta_id_actual,
                    "captured_at_ms": captured_at_ms,
                    "measurement_source": measurement_source,
                    "codigo_barras": codigo_visual,
                    "clase_yolo": clase_yolo,
                    "confianza": round(float(sim_visual), 2),
                    "vector": reconocimiento_visual_match.get("vector"),
                    "bounding_box": bbox_actual,
                    "es_fallback": False
                }
                api_executor.submit(enviar_deteccion_api, payload)

            else:
                # Regla de N Frames: Se detecta objeto no identificado
                consecutive_no_barcode_frames += 1
                logger.info(f"Frame {consecutive_no_barcode_frames}/{FALLBACK_FRAME_THRESHOLD} sin reconocimiento visual...")

                if consecutive_no_barcode_frames >= FALLBACK_FRAME_THRESHOLD:
                    logger.warning(f"⚠️ LIMITE DE {FALLBACK_FRAME_THRESHOLD} FRAMES ALCANZADO: Activando Fallback e informando al POS...")
                    consecutive_no_barcode_frames = 0
                    last_action_time = now

                    msg_err = f"Producto no reconocido tras {FALLBACK_FRAME_THRESHOLD} frames consecutivos."
                    
                    # 1) Registrar frame en MongoDB Atlas para re-entrenamiento (async: no bloquear cámara)
                    api_executor.submit(
                        atlas.registrar_evento_fallback,
                        venta_id_actual, frame.copy(), bbox_actual, confianza_yolo, msg_err
                    )

                    # 2) Enviar alerta de fallback al Backend (async: no bloquear cámara)
                    payload = {
                        "venta_id": venta_id_actual,
                    "captured_at_ms": captured_at_ms,
                    "measurement_source": measurement_source,
                        "confianza": confianza_yolo,
                        "bounding_box": bbox_actual,
                        "es_fallback": True,
                        "mensaje_error": msg_err
                    }
                    api_executor.submit(enviar_deteccion_api, payload)

                    consecutive_no_barcode_frames = 0

        # Reset contador si no hay objeto en la imagen
        if not detecto_objeto:
            consecutive_no_barcode_frames = 0

        # --- 5. Renderizado de Interfaz Visual (HUD Overlay Táctico con Vectores) ---
        if bbox_actual:
            x, y, w, h = bbox_actual["x"], bbox_actual["y"], bbox_actual["w"], bbox_actual["h"]
            
            # Dibujar esquinas tácticas (Corner Brackets)
            color = (0, 255, 0) if codigo_detectado else ((255, 230, 0) if 'reconocimiento_visual_match' in locals() and reconocimiento_visual_match else (0, 165, 255))
            l = int(min(w, h) * 0.2)
            # Esquina superior izquierda
            cv2.line(frame, (x, y), (x + l, y), color, 3)
            cv2.line(frame, (x, y), (x, y + l), color, 3)
            # Esquina superior derecha
            cv2.line(frame, (x + w, y), (x + w - l, y), color, 3)
            cv2.line(frame, (x + w, y), (x + w, y + l), color, 3)
            # Esquina inferior izquierda
            cv2.line(frame, (x, y + h), (x + l, y + h), color, 3)
            cv2.line(frame, (x, y + h), (x, y + h - l), color, 3)
            # Esquina inferior derecha
            cv2.line(frame, (x + w, y + h), (x + w - l, y + h), color, 3)
            cv2.line(frame, (x + w, y + h), (x + w, y + h - l), color, 3)

            # Dibujar rejilla de puntos de extracción de características de vectores (Feature Nodes Overlay)
            for gx in range(1, 4):
                for gy in range(1, 4):
                    px = x + int(w * gx / 4)
                    py = y + int(h * gy / 4)
                    cv2.circle(frame, (px, py), 3, (255, 255, 0), -1)

            # Etiqueta de reconocimiento vectorial o código de barras
            if codigo_detectado:
                label = f"BARCODE: {codigo_detectado} ({clase_yolo})"
            elif 'reconocimiento_visual_match' in locals() and reconocimiento_visual_match:
                sim_pct = int(reconocimiento_visual_match["sim"] * 100)
                label = f"VECTOR MATCH: {sim_pct}% | {reconocimiento_visual_match['nombre']}"
            else:
                sim_val = int(best_sim * 100) if 'best_sim' in locals() else 0
                label = f"ANALIZANDO VECTOR (512D ResNet18)... Sim: {sim_val}%"

            cv2.rectangle(frame, (x, max(0, y - 25)), (x + len(label) * 9, max(25, y)), (20, 25, 35), -1)
            cv2.putText(frame, label, (x + 5, max(18, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

        # Barra superior de estado con info de GPU y FPS
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 35), (15, 20, 30), -1)
        import torch
        gpu_badge = "GPU: RTX 4050 (CUDA)" if torch.cuda.is_available() else "CPU"
        cv2.putText(frame, f"POS CV Worker | FPS: {current_fps} | {gpu_badge}", (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 200), 1)
        cv2.putText(frame, f"Venta ID: {str(venta_id_actual)[:8]}...", (340, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 220, 255), 1)

        # Contador de frames de fallback
        if consecutive_no_barcode_frames > 0:
            cv2.putText(frame, f"Sin barra: {consecutive_no_barcode_frames}/{FALLBACK_FRAME_THRESHOLD}",
                        (frame.shape[1] - 150, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)

        # Transmitir fotograma procesado al backend para el stream MJPEG web
        enviar_frame_stream_async(frame)

        # Mostrar ventana OpenCV local (opcional: el Dashboard ya muestra el mismo stream via /cv/stream)
        if SHOW_DEBUG_WINDOW:
            cv2.imshow("Punto de Venta — Reconocimiento de Producto (Dev B)", frame)

        # --- 6. Manejo de Entradas de Teclado ---
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            logger.info("Cerrando worker de visión...")
            break
        elif key == ord('t'):
            # Tecla T: Alternar en tiempo real entre Cámara Externa (Index 1), Integrada (Index 0) y Simulación
            if cap is not None and cap.isOpened():
                cap.release()
                cap = None
                siguiente_idx = 0 if cam_index_actual == 1 else 1
                logger.info(f"▶ Cambiando de cámara... Probando Index {siguiente_idx}...")
                nuevo_cap = abrir_camara(siguiente_idx)
                if nuevo_cap is not None:
                    cap = nuevo_cap
                    cam_index_actual = siguiente_idx
                    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    logger.info(f"✓ Cambiado exitosamente a Cámara Index {cam_index_actual} ({actual_w}x{actual_h}).")
                else:
                    logger.info("▶ Pasando a MODO SIMULACIÓN (Cámara liberada).")
            else:
                logger.info("▶ Reactivando cámara física...")
                for test_idx in [1, 0, 2]:
                    cap = abrir_camara(test_idx)
                    if cap is not None:
                        cam_index_actual = test_idx
                        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        logger.info(f"✓ Cámara conectada en Index {cam_index_actual} ({actual_w}x{actual_h}).")
                        break
                if cap is None:
                    logger.error("No se pudo abrir ninguna cámara en los índices 1, 0 o 2.")
        elif key == ord('s'):
            # Tecla S: Simular escaneo por Código de Barras
            prod = sim_productos[sim_product_index % len(sim_productos)]
            sim_product_index += 1
            logger.info(f"Simulando lectura de Código de Barras: '{prod['nombre']}' ({prod['codigo']})...")
            payload = {
                "venta_id": venta_id_actual,
                "captured_at_ms": captured_at_ms,
                "measurement_source": "simulation",
                "codigo_barras": prod["codigo"],
                "clase_yolo": prod["clase"],
                "confianza": 0.98,
                "bounding_box": {"x": 150, "y": 100, "w": 200, "h": 300},
                "es_fallback": False
            }
            enviar_deteccion_api(payload)
            last_action_time = time.time()
        elif key == ord('v'):
            # Tecla V: Evaluar Reconocimiento VECTORIAL Real (ResNet18 Embeddings + Supabase Catalog)
            sample_prod = sim_productos[sim_product_index % len(sim_productos)]
            sim_product_index += 1
            
            # Cargar imagen real de prueba del dataset o usar frame de cámara
            img_to_test = None
            if sample_prod.get("img") and os.path.exists(sample_prod["img"]):
                img_to_test = cv2.imread(sample_prod["img"])
            if img_to_test is None:
                img_to_test = frame

            vec = vector_engine.extraer_vector(img_to_test)
            match, sim_pct = vector_engine.buscar_producto_por_vector(vec, umbral_similitud=0.75)
            
            if match:
                logger.info(f"★ ¡Reconocimiento Vectorial en Base de Datos Exitoso!: '{match['nombre']}' (Similitud: {round(sim_pct*100, 1)}%)")
                payload = {
                    "venta_id": venta_id_actual,
                    "codigo_barras": match["codigo"],
                    "clase_yolo": match.get("clase", sample_prod["clase"]),
                    "confianza": round(float(sim_pct), 2),
                    "vector": vec.tolist() if vec is not None else None,
                    "bounding_box": {"x": 150, "y": 100, "w": 200, "h": 300},
                    "es_fallback": False
                }
                enviar_deteccion_api(payload)
            else:
                logger.warning(f"⚠️ Similitud insuficiente ({round(sim_pct*100, 1)}%). Activando fallback...")
                payload = {
                    "venta_id": venta_id_actual,
                    "confianza": round(float(sim_pct), 2),
                    "bounding_box": {"x": 150, "y": 100, "w": 200, "h": 300},
                    "es_fallback": True,
                    "mensaje_error": f"Similitud vectorial insuficiente ({round(sim_pct*100, 1)}%)."
                }
                enviar_deteccion_api(payload)
            last_action_time = time.time()
        elif key == ord('f'):
            # Tecla F: Simular disparo del Fallback (Alerta manual al POS)
            logger.info("Simulando disparo de alerta de Fallback...")
            payload = {
                "venta_id": venta_id_actual,
                "captured_at_ms": captured_at_ms,
                "measurement_source": "simulation",
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

    if cap is not None and cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
