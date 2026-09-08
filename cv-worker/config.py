import os
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000/api/v1")
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "1"))
USE_SIMULATION = os.getenv("USE_SIMULATION", "false").lower() in ("true", "1", "yes")
VENTA_ID = os.getenv("VENTA_ID", "")
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "yolov8n.pt")
YOLO_CONF_THRESHOLD = float(os.getenv("YOLO_CONF_THRESHOLD", "0.45"))

MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "pos_telemetria")
MONGODB_COLLECTION = os.getenv("MONGODB_COLLECTION", "eventos_vision")

FALLBACK_FRAME_THRESHOLD = int(os.getenv("FALLBACK_FRAME_THRESHOLD", "25"))
COOL_DOWN_SECONDS = float(os.getenv("COOL_DOWN_SECONDS", "2.0"))

# Rendimiento: procesar 1 de cada N frames con YOLO + ResNet18 (ambos sincronizados)
PROCESS_EVERY_N_FRAMES = int(os.getenv("PROCESS_EVERY_N_FRAMES", "3"))
# Ventana de depuración local (cv2.imshow). Desactivar en producción: solo se necesita el stream del Dashboard.
SHOW_DEBUG_WINDOW = os.getenv("SHOW_DEBUG_WINDOW", "true").lower() in ("true", "1", "yes")

