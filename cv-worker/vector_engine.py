import sys
import json
import os
import glob
import torch
import torchvision.transforms as T
from torchvision.models import resnet18, ResNet18_Weights
from PIL import Image
import numpy as np
import cv2
import logging

try:
    from config import SUPABASE_URL, SUPABASE_KEY
except ImportError:
    SUPABASE_URL, SUPABASE_KEY = "", ""

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

    def _cargar_catalogo_desde_supabase(self) -> bool:
        """Intenta sincronizar los vectores 512d directamente desde Supabase (pgvector)."""
        if not SUPABASE_URL or not SUPABASE_KEY:
            return False

        try:
            from supabase import create_client
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            res = supabase.table("productos").select("id, codigo_barras, nombre, categoria, embedding").eq("activo", True).execute()
            
            cargados = 0
            for row in (res.data or []):
                raw_emb = row.get("embedding")
                if not raw_emb:
                    continue
                
                # Convertir lista o string de pgvector a numpy array
                if isinstance(raw_emb, str):
                    raw_emb = json.loads(raw_emb)
                vec = np.array(raw_emb, dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                
                self.catalogo_vectores[row["codigo_barras"]] = {
                    "id": row["id"],
                    "codigo": row["codigo_barras"],
                    "nombre": row["nombre"],
                    "clase": row.get("categoria", "producto"),
                    "vector": vec
                }
                cargados += 1
                
            if cargados > 0:
                logger.info(f"✓ Sincronizados {cargados} vectores de productos directamente desde Supabase (pgvector).")
                return True
        except Exception as e:
            logger.warning(f"No se pudo cargar vectores desde Supabase ({e}). Usando fallback de imágenes locales...")
            
        return False

    def _inicializar_catalogo_referencia(self):
        """Inicializa vectores desde Supabase o calculando centroides desde SetImagenesBuenas/."""
        # 1. Intentar cargar desde la base de datos Supabase
        if self._cargar_catalogo_desde_supabase():
            return

        # 2. Fallback: computar vectores reales desde dataset local si la DB no responde
        dataset_dir = "SetImagenesBuenas"
        if not os.path.exists(dataset_dir):
            dataset_dir = os.path.join(os.path.dirname(__file__), "..", "SetImagenesBuenas")
        
        mapping_dirs = {
            "CocaColaSet": {"codigo": "7501055312107", "nombre": "Coca-Cola Original 600ml", "clase": "coca_cola"},
            "SabritasPapas": {"codigo": "7501000111203", "nombre": "Sabritas Sal 45g", "clase": "sabritas"},
            "RuflesQueso": {"codigo": "7501000122209", "nombre": "Ruffles Queso 50g", "clase": "ruffles"},
            "BoteAgua": {"codigo": "7501020512110", "nombre": "Agua e-pura Purificada 1L", "clase": "agua"},
            "GalletasChokis": {"codigo": "7501011115481", "nombre": "Galletas Chokis 76g", "clase": "chokis"},
            "BoteAgua": {"codigo": "7501020512110", "nombre": "Agua e·pura Purificada 1L", "clase": "agua"},
        }

        if os.path.exists(dataset_dir):
            logger.info("Calculando vectores centroides desde imágenes de SetImagenesBuenas/...")
            for folder, info in mapping_dirs.items():
                folder_path = os.path.join(dataset_dir, folder)
                if os.path.exists(folder_path):
                    vecs_producto = []
                    for img_file in glob.glob(os.path.join(folder_path, "*.*")):
                        img = cv2.imread(img_file)
                        if img is not None:
                            vec = self.extraer_vector(img)
                            if vec is not None:
                                vecs_producto.append(vec)
                    if vecs_producto:
                        centroide = np.mean(vecs_producto, axis=0)
                        centroide = centroide / np.linalg.norm(centroide)
                        self.catalogo_vectores[info["codigo"]] = {
                            "codigo": info["codigo"],
                            "nombre": info["nombre"],
                            "clase": info["clase"],
                            "vector": centroide
                        }
            logger.info(f"✓ Inicializados {len(self.catalogo_vectores)} vectores centroides desde imágenes locales.")

    def buscar_producto_por_vector(self, vector_query, umbral_similitud=0.78):
        """
        Compara un vector contra el catálogo mediante Similitud de Coseno.
        Retorna (producto_match, porcentaje_similitud) si supera el umbral, sino (None, max_similitud).
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

        return None, max_similitud

