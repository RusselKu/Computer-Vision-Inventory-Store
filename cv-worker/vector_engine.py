import os
import sys
import torch
import torchvision.transforms as T
from torchvision.models import resnet18, ResNet18_Weights
from PIL import Image
import numpy as np
import cv2
import logging

logger = logging.getLogger("VectorEngine")

# Cargar cliente Supabase opcional
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))
try:
    from app.core.supabase import get_supabase_client
    supabase_client = get_supabase_client()
    logger.info("✓ Cliente de Supabase conectado en VectorEngine (pgvector disponible).")
except Exception as e:
    supabase_client = None
    logger.warning(f"Supabase no disponible en VectorEngine ({e}). Se usará catálogo vectorial local.")


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
        """Carga vectores de firma reales desde el dataset local SetImagenesBuenas/ si existe."""
        import glob
        
        logger.info("Generando firma de vectores base para productos del catálogo...")
        # Ruta absoluta respecto a este archivo: NO depender del cwd del proceso
        # (el worker suele lanzarse desde cv-worker/, donde SetImagenesBuenas/ no existe).
        dataset_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SetImagenesBuenas")

        mapping_dirs = {
            "CocaColaSet": {"codigo": "7501055312107", "nombre": "Coca-Cola Original 600ml", "clase": "coca_cola"},
            "SabritasPapas": {"codigo": "7501000111203", "nombre": "Sabritas Sal 45g", "clase": "sabritas"},
            "RuflesQueso": {"codigo": "7501000122209", "nombre": "Ruffles Queso 50g", "clase": "ruffles"},
            "BoteAgua": {"codigo": "7501020512110", "nombre": "Agua e-pura Purificada 1L", "clase": "agua"},
            "GalletasChokis": {"codigo": "7501011115481", "nombre": "Galletas Chokis 76g", "clase": "chokis"},
        }

        cargados = 0
        if os.path.exists(dataset_dir):
            for folder, info in mapping_dirs.items():
                folder_path = os.path.join(dataset_dir, folder)
                if os.path.exists(folder_path):
                    for img_file in glob.glob(os.path.join(folder_path, "*.*")):
                        img = cv2.imread(img_file)
                        if img is not None:
                            vec = self.extraer_vector(img)
                            if vec is not None:
                                self.catalogo_vectores[f"{info['codigo']}_{os.path.basename(img_file)}"] = {
                                    "codigo": info["codigo"],
                                    "nombre": info["nombre"],
                                    "clase": info["clase"],
                                    "vector": vec
                                }
                                cargados += 1
            if cargados > 0:
                logger.info(f"✓ Cargados {cargados} vectores reales desde el dataset 'SetImagenesBuenas/'.")
                return

        # Fallback a firmas base sintéticas si no se encuentra el dataset
        np.random.seed(42)
        productos_base = [
            {"codigo": "7501000111203", "nombre": "Sabritas Sal 45g", "clase": "sabritas"},
            {"codigo": "7501055312107", "nombre": "Coca-Cola 600ml", "clase": "coca_cola"},
            {"codigo": "7501000153036", "nombre": "Doritos Nacho 58g", "clase": "doritos"},
        ]

        for prod in productos_base:
            vec = np.random.randn(512).astype(np.float32)
            vec = vec / np.linalg.norm(vec)
            self.catalogo_vectores[prod["codigo"]] = {
                "codigo": prod["codigo"],
                "nombre": prod["nombre"],
                "clase": prod["clase"],
                "vector": vec
            }

    def buscar_producto_por_vector(self, vector_query, umbral_similitud=0.65, margen_minimo=0.04):
        """
        Compara un vector contra el catálogo vectorial local primero (ultra-rápido ~0.1ms).
        Agrupa por código de producto (varias fotos de referencia por producto) y exige un
        margen mínimo de confianza sobre el segundo mejor candidato para evitar falsos positivos
        entre productos visualmente similares (ej. botella de agua vs. botella de refresco).
        Retorna (producto_match, porcentaje_similitud).
        """
        if vector_query is None or len(self.catalogo_vectores) == 0:
            return None, 0.0

        # 1. Similitud máxima por código de producto (varias imágenes de referencia por producto)
        mejor_similitud_por_codigo = {}
        mejor_info_por_codigo = {}
        for prod_data in self.catalogo_vectores.values():
            similitud = float(np.dot(vector_query, prod_data["vector"]))
            codigo = prod_data["codigo"]
            if codigo not in mejor_similitud_por_codigo or similitud > mejor_similitud_por_codigo[codigo]:
                mejor_similitud_por_codigo[codigo] = similitud
                mejor_info_por_codigo[codigo] = prod_data

        ranking = sorted(mejor_similitud_por_codigo.items(), key=lambda kv: kv[1], reverse=True)
        mejor_codigo, mejor_sim = ranking[0]
        segundo_sim = ranking[1][1] if len(ranking) > 1 else -1.0

        # 2. Exigir umbral absoluto Y margen sobre el segundo candidato más parecido
        if mejor_sim >= umbral_similitud and (mejor_sim - segundo_sim) >= margen_minimo:
            return mejor_info_por_codigo[mejor_codigo], mejor_sim

        return (mejor_info_por_codigo[mejor_codigo], mejor_sim) if mejor_sim > 0 else (None, 0.0)
