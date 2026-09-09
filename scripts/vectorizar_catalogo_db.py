import os
import sys
import glob
import cv2
import numpy as np
from dotenv import load_dotenv
from supabase import create_client

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Asegurar path para importar cv-worker
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cv-worker")))
from vector_engine import VectorEngine

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL o SUPABASE_KEY no configurados en .env")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
engine = VectorEngine()

CATALOGO = {
    "CocaColaSet": {
        "codigo_barras": "7501055312107",
        "nombre": "Coca-Cola Original 600ml",
        "precio": 18.00,
        "categoria": "Bebidas",
        "imagen_url": f"{SUPABASE_URL}/storage/v1/object/public/productos/CocaColaSet/Cocacolanormal.jpg"
    },
    "SabritasPapas": {
        "codigo_barras": "7501000111203",
        "nombre": "Sabritas Sal 45g",
        "precio": 22.00,
        "categoria": "Snacks / Botanas",
        "imagen_url": f"{SUPABASE_URL}/storage/v1/object/public/productos/SabritasPapas/Papasnormal.png"
    },
    "RuflesQueso": {
        "codigo_barras": "7501000122209",
        "nombre": "Ruffles Queso 50g",
        "precio": 22.00,
        "categoria": "Snacks / Botanas",
        "imagen_url": f"{SUPABASE_URL}/storage/v1/object/public/productos/RuflesQueso/Rufles1.jpg"
    },
    "BoteAgua": {
        "codigo_barras": "7501020512110",
        "nombre": "Agua e·pura Purificada 1L",
        "precio": 15.00,
        "categoria": "Bebidas",
        "imagen_url": f"{SUPABASE_URL}/storage/v1/object/public/productos/BoteAgua/AguaEpura.jpg"
    },
    "GalletasChokis": {
        "codigo_barras": "7501011115481",
        "nombre": "Galletas Chokis 76g",
        "precio": 19.00,
        "categoria": "Galletas / Snacks",
        "imagen_url": f"{SUPABASE_URL}/storage/v1/object/public/productos/GalletasChokis/Chokis1.png"
    },
}

def asegurar_producto_existe(info):
    codigo = info["codigo_barras"]
    res = supabase.table("productos").select("id, nombre, codigo_barras").eq("codigo_barras", codigo).execute()
    if res.data and len(res.data) > 0:
        return res.data[0]["id"]
    
    print(f"[+] Insertando producto faltante: {info['nombre']} ({codigo})...")
    insert_res = supabase.table("productos").insert({
        "codigo_barras": codigo,
        "nombre": info["nombre"],
        "precio": info["precio"],
        "categoria": info["categoria"],
        "imagen_url": info["imagen_url"],
        "activo": True
    }).execute()
    
    nuevo_id = insert_res.data[0]["id"]
    supabase.table("inventario").insert({
        "producto_id": nuevo_id,
        "stock_actual": 30,
        "stock_minimo": 5,
        "ubicacion": "Estante B-1"
    }).execute()
    print(f"[OK] Creado producto e inventario para: {info['nombre']}")
    return nuevo_id

def vectorizar_catalogo():
    print("=" * 65)
    print("  Vectorizacion Real de Catalogo de Productos con ResNet18 (512d)")
    print("=" * 65)
    dataset_dir = "SetImagenesBuenas"
    
    if not os.path.exists(dataset_dir):
        print(f"Error: No se encontro la carpeta {dataset_dir}")
        sys.exit(1)
        
    centroides = {}

    for folder_name, info in CATALOGO.items():
        print(f"\n>> Procesando categoria: [{folder_name}] - {info['nombre']}")
        prod_id = asegurar_producto_existe(info)
        
        folder_path = os.path.join(dataset_dir, folder_name)
        img_files = glob.glob(os.path.join(folder_path, "*.*"))
        
        if not img_files:
            print(f"[!] No hay imagenes en {folder_path}")
            continue
            
        vectores_imagen = []
        for img_path in img_files:
            img = cv2.imread(img_path)
            if img is None:
                continue
            vec = engine.extraer_vector(img)
            if vec is not None:
                vectores_imagen.append(vec)
                print(f"   [OK] Vector extraido de: {os.path.basename(img_path)} (Norm: {np.linalg.norm(vec):.2f})")
                
        if not vectores_imagen:
            print(f"[!] No se pudieron extraer vectores de {folder_name}")
            continue
            
        # Calcular vector centroide normalizado L2 = 1.0
        centroid = np.mean(vectores_imagen, axis=0)
        centroid = centroid / np.linalg.norm(centroid)
        centroides[info["codigo_barras"]] = centroid
        
        # pgvector acepta lista de floats [0.1, 0.2, ...]
        vector_list = centroid.tolist()
        update_res = supabase.table("productos").update({
            "embedding": vector_list
        }).eq("id", prod_id).execute()
        
        print(f"   [*] Vector centroide guardado en Supabase para {info['nombre']} (512 dims)")

    print("\n" + "=" * 65)
    print("  Validacion de Busqueda Vectorial (RPC buscar_producto_por_vector)")
    print("=" * 65)
    
    for folder_name, info in CATALOGO.items():
        codigo = info["codigo_barras"]
        if codigo not in centroides:
            continue
            
        test_vec = centroides[codigo].tolist()
        try:
            rpc_res = supabase.rpc("buscar_producto_por_vector", {
                "query_embedding": test_vec,
                "match_threshold": 0.70,
                "match_count": 2
            }).execute()
            
            top_matches = rpc_res.data or []
            if top_matches:
                best = top_matches[0]
                pct = round(best["similitud"] * 100, 1)
                es_correcto = best["codigo_barras"] == codigo
                icon = "[OK]" if es_correcto else "[MISMATCH]"
                print(f"{icon} Query: '{info['nombre'][:22]:22}' => Match: '{best['nombre'][:22]:22}' | Similitud: {pct}%")
            else:
                print(f"[!] No hubo matches para '{info['nombre']}' con umbral 0.70")
        except Exception as e:
            print(f"[ERR] Error invocando RPC para '{info['nombre']}': {e}")

    print("\n[SUCCESS] Vectorizacion completada exitosamente!")

if __name__ == "__main__":
    vectorizar_catalogo()
