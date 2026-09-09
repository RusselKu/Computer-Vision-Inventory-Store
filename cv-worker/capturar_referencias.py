"""
Herramienta de captura de fotos de referencia para el catálogo vectorial.

Toma fotos del producto REAL con la misma cámara/iluminación que usará el worker en
producción (en vez de fotos de stock de internet), para minimizar el "domain gap"
entre el catálogo y lo que la cámara realmente ve en el punto de venta.

Uso:
    python capturar_referencias.py

Controles:
    [1] Coca-Cola      [2] Sabritas      [3] Ruffles      [4] Agua Ciel      [5] Chokis
    [ESPACIO] Guardar foto para el producto actualmente seleccionado
    [Q] Salir
"""
import os
import time
import cv2

from config import CAMERA_INDEX

CARPETAS = {
    ord('1'): ("CocaColaSet", "Coca-Cola Original 600ml"),
    ord('2'): ("SabritasPapas", "Sabritas Sal 45g"),
    ord('3'): ("RuflesQueso", "Ruffles Queso 50g"),
    ord('4'): ("BoteAgua", "Agua Ciel Purificada 1L"),
    ord('5'): ("GalletasChokis", "Galletas Chokis"),
}

DATASET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SetImagenesBuenas")


def abrir_camara():
    for api_pref in [cv2.CAP_ANY, cv2.CAP_MSMF, cv2.CAP_DSHOW]:
        cap = cv2.VideoCapture(CAMERA_INDEX, api_pref)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                return cap
            cap.release()
    return None


def main():
    cap = abrir_camara()
    if cap is None:
        print(f"No se pudo abrir la camara (index {CAMERA_INDEX}). Revisa que no este en uso por otro proceso.")
        return

    producto_actual = ord('2')  # Sabritas por defecto
    print("Controles: [1] Coca-Cola  [2] Sabritas  [3] Ruffles  [4] Agua  [5] Chokis  [ESPACIO] Guardar  [Q] Salir")

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        carpeta, nombre = CARPETAS[producto_actual]
        vista = frame.copy()
        cv2.rectangle(vista, (0, 0), (vista.shape[1], 40), (20, 25, 35), -1)
        cv2.putText(vista, f"Producto: {nombre} | [ESPACIO]=Guardar [1-5]=Cambiar [Q]=Salir",
                    (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 200), 1)
        cv2.imshow("Captura de Referencias - Catalogo Vectorial", vista)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break
        elif key in CARPETAS:
            producto_actual = key
        elif key == ord(' '):
            carpeta, nombre = CARPETAS[producto_actual]
            destino = os.path.join(DATASET_DIR, carpeta)
            os.makedirs(destino, exist_ok=True)
            filename = os.path.join(destino, f"real_cam_{int(time.time()*1000)}.jpg")
            cv2.imwrite(filename, frame)
            print(f"[OK] Guardado: {filename}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
