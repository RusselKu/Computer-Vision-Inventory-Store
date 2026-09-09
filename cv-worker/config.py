import os
from dotenv import load_dotenv

# Cargar variables de entorno desde cv-worker/.env o raíz .env
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
if not os.path.exists(dotenv_path):
    dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path)

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
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

# Configuración de Streaming y Visualización Web
SHOW_CV2_WINDOW = os.getenv("SHOW_CV2_WINDOW", os.getenv("SHOW_DEBUG_WINDOW", "false")).lower() in ("true", "1", "yes")
SHOW_DEBUG_WINDOW = SHOW_CV2_WINDOW
ENABLE_STREAM = os.getenv("ENABLE_STREAM", "true").lower() in ("true", "1", "yes")
STREAM_PORT = int(os.getenv("STREAM_PORT", "8088"))
STREAM_HOST = os.getenv("STREAM_HOST", "0.0.0.0")
VECTOR_SIMILARITY_THRESHOLD = float(os.getenv("VECTOR_SIMILARITY_THRESHOLD", "0.70"))

