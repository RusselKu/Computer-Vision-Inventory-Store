import base64
import cv2
import datetime
import logging
from config import MONGODB_URI, MONGODB_DB_NAME, MONGODB_COLLECTION

logger = logging.getLogger("AtlasLogger")

PYMONGO_AVAILABLE = False
try:
    import pymongo
    PYMONGO_AVAILABLE = True
except ImportError:
    logger.warning("pymongo no instalado. Los frames no leídos se registrarán únicamente en consola local.")


class AtlasLogger:
    def __init__(self):
        self.client = None
        self.db = None
        self.collection = None

        if PYMONGO_AVAILABLE and MONGODB_URI:
            try:
                self.client = pymongo.MongoClient(MONGODB_URI, serverSelectionTimeoutMS=3000, socketTimeoutMS=3000)
                self.client.admin.command('ping')
                self.db = self.client[MONGODB_DB_NAME]
                self.collection = self.db[MONGODB_COLLECTION]
                logger.info(f"Conectado exitosamente a MongoDB Atlas ({MONGODB_DB_NAME}.{MONGODB_COLLECTION})")
            except Exception as e:
                logger.warning(f"No se pudo conectar a MongoDB Atlas: {e}. Modo offline.")

    def registrar_evento_fallback(self, venta_id, frame, bounding_box, confianza, mensaje_error):
        """
        Guarda el frame no reconocido codificado en Base64 junto con sus metadatos
        en la colección 'eventos_vision' de MongoDB Atlas para re-entrenamiento futuro.
        """
        # Convertir frame a JPEG base64
        image_base64 = ""
        if frame is not None:
            try:
                _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                image_base64 = base64.b64encode(buffer).decode('utf-8')
            except Exception as e:
                logger.error(f"Error codificando frame a base64: {e}")

        documento = {
            "venta_id": str(venta_id),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "confianza_yolo": confianza,
            "bounding_box": bounding_box,
            "mensaje_error": mensaje_error,
            "frame_base64": image_base64,
            "revisado_para_retrain": False
        }

        if self.collection is not None:
            try:
                self.collection.insert_one(documento)
                logger.info(f"Frame no reconocido guardado en MongoDB Atlas para venta {venta_id}")
            except Exception as e:
                logger.error(f"Error guardando evento en MongoDB Atlas: {e}")
        else:
            logger.warning(f"[OFFLINE] Evento Fallback registrado localmente (sin conexión Atlas): Venta {venta_id} | {mensaje_error}")
