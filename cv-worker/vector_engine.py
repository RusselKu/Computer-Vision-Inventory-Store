import torch
import torchvision.transforms as T
from torchvision.models import resnet18, ResNet18_Weights
from PIL import Image
import numpy as np
import cv2
import logging

logger = logging.getLogger("VectorEngine")


class VectorEngine:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Cargando modelo de extracción de vectores ResNet18 en dispositivo: {self.device}")

        # Cargar modelo ResNet18 pre-entrenado y remover la capa clasificadora final
        # para obtener el vector de características de 512 dimensiones
        weights = ResNet18_Weights.DEFAULT
        resnet = resnet18(weights=weights)
        self.model = torch.nn.Sequential(*list(resnet.children())[:-1]).to(self.device)
        self.model.eval()

        # Transformaciones estándar para normalizar imágenes de entrada
        self.transform = T.Compose([
            T.Resize((224, 224)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        # Catálogo de vectores conocidos (Embedding Database)
        self.catalogo_vectores = {}
        self._inicializar_catalogo_referencia()

    def extraer_vector(self, imagen_np):
        """
        Extrae un vector embedding normalizado de 512 dimensiones a partir de una imagen OpenCV (BGR).
        """
        if imagen_np is None or imagen_np.size == 0:
            return None

        try:
            # Convertir BGR (OpenCV) a RGB y luego a Image de PIL
            rgb_img = cv2.cvtColor(imagen_np, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb_img)

            # Preprocesar e inferir vector
            tensor_img = self.transform(pil_img).unsqueeze(0).to(self.device)
            with torch.no_grad():
                features = self.model(tensor_img).squeeze().cpu().numpy()

            # Normalizar L2 para cálculo eficiente de similitud de coseno
            norm = np.linalg.norm(features)
            if norm > 0:
                features = features / norm

            return features
        except Exception as e:
            logger.error(f"Error extrayendo vector embedding: {e}")
            return None

    def _inicializar_catalogo_referencia(self):
        """Genera vectores de firma sintéticos para los productos del catálogo de prueba."""
        logger.info("Generando firma de vectores base para productos del catálogo...")
        np.random.seed(42)  # Semilla fija para reproducibilidad
        
        productos_base = [
            {"codigo": "7501000111203", "nombre": "Sabritas Sal 45g", "clase": "sabritas"},
            {"codigo": "7501000153036", "nombre": "Doritos Nacho 58g", "clase": "doritos"},
            {"codigo": "7501055312107", "nombre": "Coca-Cola 600ml", "clase": "coca_cola"},
        ]

        for prod in productos_base:
            # Generar un vector sintético único de 512 dimensiones para simulación de catálogo
            vec = np.random.randn(512).astype(np.float32)
            vec = vec / np.linalg.norm(vec)
            self.catalogo_vectores[prod["codigo"]] = {
                "codigo": prod["codigo"],
                "nombre": prod["nombre"],
                "clase": prod["clase"],
                "vector": vec
            }

    def buscar_producto_por_vector(self, vector_query, umbral_similitud=0.75):
        """
        Compara un vector contra el catálogo mediante Similitud de Coseno.
        Retorna (producto_match, porcentaje_similitud).
        """
        if vector_query is None or len(self.catalogo_vectores) == 0:
            return None, 0.0

        mejor_match = None
        max_similitud = -1.0

        for codigo, prod_data in self.catalogo_vectores.items():
            vec_ref = prod_data["vector"]
            # Similitud de coseno entre vectores L2 normalizados
            similitud = float(np.dot(vector_query, vec_ref))

            if similitud > max_similitud:
                max_similitud = similitud
                mejor_match = prod_data

        if max_similitud >= umbral_similitud:
            return mejor_match, max_similitud
        
        return mejor_match, max_similitud
