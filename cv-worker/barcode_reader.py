import cv2
import logging

logger = logging.getLogger("BarcodeReader")

# Intentar importar pyzbar
PYZBAR_AVAILABLE = False
try:
    from pyzbar import pyzbar
    PYZBAR_AVAILABLE = True
except Exception as e:
    logger.warning(f"pyzbar no disponible o faltan DLLs C++ ({e}). Se usará OpenCV BarcodeDetector como fallback.")

# Instancia de respaldos con OpenCV si pyzbar no está
_cv_barcode_detector = None
if hasattr(cv2, 'barcode_BarcodeDetector'):
    try:
        _cv_barcode_detector = cv2.barcode_BarcodeDetector()
    except Exception:
        pass


def decodificar_codigo_barras(imagen, bbox=None):
    """
    Intenta leer código de barras (EAN-13, UPC-A, Code128, etc.) en una imagen o dentro de un bounding box.
    Retorna: string con el código decodificado o None si no se encontró nada.
    """
    if imagen is None or imagen.size == 0:
        return None

    # Si se provee bounding box (x, y, w, h), recortar la región de interés (ROI)
    roi = imagen
    if bbox:
        x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
        h_img, w_img = imagen.shape[:2]
        # Asegurar coordenadas dentro de los límites del frame
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w_img, x + w), min(h_img, y + h)
        if x2 > x1 and y2 > y1:
            roi = imagen[y1:y2, x1:x2]

    # Preprocesamiento ultra-rápido
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if len(roi.shape) == 3 else roi
    
    # Pasada 1: Lectura directa (súper rápida ~2ms)
    codigo = _procesar_con_pyzbar_o_cv(gray)
    if codigo:
        return codigo

    # Pasada 2: Contraste CLAHE solo si la pasada directa falla
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast_img = clahe.apply(gray)
    codigo = _procesar_con_pyzbar_o_cv(contrast_img)
    if codigo:
        return codigo

    return None


def _procesar_con_pyzbar_o_cv(img):
    if PYZBAR_AVAILABLE:
        try:
            barcodes = pyzbar.decode(img)
            for b in barcodes:
                barcode_data = b.data.decode("utf-8").strip()
                if barcode_data:
                    return barcode_data
        except Exception:
            pass
        return None

    # Fallback a OpenCV BarcodeDetector solo si pyzbar no está instalado
    if _cv_barcode_detector is not None:
        try:
            ok, decoded_info, decoded_type, _ = _cv_barcode_detector.detectAndDecode(img)
            if ok and decoded_info:
                for info in decoded_info:
                    if info and info.strip():
                        return info.strip()
        except Exception:
            pass

    return None
