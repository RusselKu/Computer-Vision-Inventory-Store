import cv2
import logging

logger = logging.getLogger("YOLODetector")

ULTRALYTICS_AVAILABLE = False
try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    logger.warning("ultralytics YOLO no está instalado. Se usará detector sintético/contornos para desarrollo.")


class DetectorYOLO:
    def __init__(self, model_path="yolov8n.pt", conf_thresh=0.45):
        self.conf_thresh = conf_thresh
        self.model = None
        if ULTRALYTICS_AVAILABLE:
            try:
                self.model = YOLO(model_path)
                logger.info(f"Modelo YOLOv8 cargado exitosamente desde {model_path}")
            except Exception as e:
                logger.error(f"No se pudo cargar el modelo YOLO ({e}). Usando fallback de contornos.")

    def detectar_objetos(self, frame):
        """
        Inferencia de YOLOv8 sobre el frame.
        Retorna lista de diccionarios:
        [
           {
               "clase": "coca_cola",
               "confianza": 0.92,
               "bbox": {"x": 100, "y": 50, "w": 200, "h": 300}
           }
        ]
        """
        if frame is None:
            return []

        if self.model is not None:
            try:
                results = self.model(frame, conf=self.conf_thresh, verbose=False)
                detecciones = []
                for r in results:
                    boxes = r.boxes
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                        conf = float(box.conf[0].cpu().numpy())
                        cls_id = int(box.cls[0].cpu().numpy())
                        cls_name = r.names.get(cls_id, f"clase_{cls_id}")

                        detecciones.append({
                            "clase": cls_name,
                            "confianza": round(conf, 2),
                            "bbox": {
                                "x": int(x1),
                                "y": int(y1),
                                "w": int(x2 - x1),
                                "h": int(y2 - y1)
                            }
                        })
                return detecciones
            except Exception as e:
                logger.error(f"Error en inferencia YOLO: {e}")

        # Fallback si no hay modelo YOLO activo: buscar objeto relevante en el centro de la imagen
        return self._detectar_fallback_contornos(frame)

    def _detectar_fallback_contornos(self, frame):
        """Detecta contornos significativos cerca del área de escaneo central."""
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)
        
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        detecciones = []
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            # Filtrar contornos muy pequeños (ruido) o gigantescos (pantalla completa)
            if (bw * bh > (w * h * 0.05)) and (bw * bh < (w * h * 0.8)):
                detecciones.append({
                    "clase": "objeto_desconocido",
                    "confianza": 0.85,
                    "bbox": {"x": x, "y": y, "w": bw, "h": bh}
                })
                # Retornar el mayor objeto detectado
                break

        return detecciones
