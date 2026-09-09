import pytest
pytestmark = pytest.mark.integration
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["supabase"] == "connected"


def test_listar_productos():
    response = client.get("/api/v1/productos")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    # Validar campos del primer producto
    prod = data[0]
    assert "codigo_barras" in prod
    assert "nombre" in prod
    assert "precio" in prod
    assert "stock_actual" in prod


def test_buscar_producto_por_codigo_barras():
    codigo = "7501055312107"  # Coca-Cola del seed
    response = client.get(f"/api/v1/productos/codigo/{codigo}")
    assert response.status_code == 200
    data = response.json()
    assert data["codigo_barras"] == codigo
    assert "Coca-Cola" in data["nombre"]


def test_flujo_completo_pos_y_cierre():
    # 1. Iniciar venta
    res_crear = client.post("/api/v1/ventas")
    assert res_crear.status_code == 201
    venta = res_crear.json()
    venta_id = venta["id"]
    assert venta["estado"] == "abierta"
    assert venta["total"] == 0.0

    # 2. Agregar item por código de barras (Coca-Cola)
    res_item1 = client.post(
        f"/api/v1/ventas/{venta_id}/items",
        json={
            "codigo_barras": "7501055312107",
            "cantidad": 2,
            "metodo_deteccion": "cv_barcode"
        }
    )
    assert res_item1.status_code == 200
    venta_actualizada = res_item1.json()
    assert len(venta_actualizada["items"]) == 1
    # 2 x 18.00 = 36.00
    assert venta_actualizada["total"] == 36.00

    # 3. Agregar otro item (Sabritas Sal)
    res_item2 = client.post(
        f"/api/v1/ventas/{venta_id}/items",
        json={
            "codigo_barras": "7501000111203",
            "cantidad": 1,
            "metodo_deteccion": "cv_yolo"
        }
    )
    assert res_item2.status_code == 200
    venta_actualizada = res_item2.json()
    assert len(venta_actualizada["items"]) == 2
    # 36.00 + 22.00 = 58.00
    assert venta_actualizada["total"] == 58.00

    # 4. Eliminar el segundo item
    item_sabritas = next(it for it in venta_actualizada["items"] if it["producto"]["codigo_barras"] == "7501000111203")
    res_del = client.delete(f"/api/v1/ventas/{venta_id}/items/{item_sabritas['id']}")
    assert res_del.status_code == 200
    venta_actualizada = res_del.json()
    assert len(venta_actualizada["items"]) == 1
    assert venta_actualizada["total"] == 36.00

    # 5. Cerrar la venta (descuenta inventario de forma atómica en Supabase)
    res_cerrar = client.post(
        f"/api/v1/ventas/{venta_id}/cerrar",
        json={"metodo_pago": "efectivo"}
    )
    assert res_cerrar.status_code == 200
    resultado_cierre = res_cerrar.json()
    assert resultado_cierre["success"] is True
    assert resultado_cierre["estado"] == "completada"
    assert resultado_cierre["total"] == 36.00

    # 6. Repetir el cierre devuelve la misma confirmación sin descontar otra vez.
    res_cerrar_duplicado = client.post(
        f"/api/v1/ventas/{venta_id}/cerrar",
        json={"metodo_pago": "efectivo"}
    )
    assert res_cerrar_duplicado.status_code == 200
    assert res_cerrar_duplicado.json()['total'] == resultado_cierre['total']


def test_evento_cv_integracion():
    # 1. Iniciar venta
    res_crear = client.post("/api/v1/ventas")
    venta_id = res_crear.json()["id"]

    # 2. Enviar evento de detección exitoso de Dev B
    res_cv = client.post(
        "/api/v1/cv/deteccion",
        json={
            "venta_id": venta_id,
            "codigo_barras": "7501055312107",  # Coca-Cola Original 600ml
            "clase_yolo": "coca_cola",
            "confianza": 0.96,
            "bounding_box": {"x": 100, "y": 150, "w": 300, "h": 400},
            "es_fallback": False
        }
    )
    assert res_cv.status_code == 200
    data_cv = res_cv.json()
    assert data_cv["status"] == "agregado"
    assert "Coca-Cola" in data_cv["producto"]["nombre"]

    # 3. Enviar evento de fallback (falla de lectura en cámara)
    res_fallback = client.post(
        "/api/v1/cv/deteccion",
        json={
            "venta_id": venta_id,
            "confianza": 0.20,
            "es_fallback": True,
            "mensaje_error": "Producto no reconocido tras 5 frames."
        }
    )
    assert res_fallback.status_code == 200
    data_fallback = res_fallback.json()
    assert data_fallback["status"] == "requiere_manual"


def test_busqueda_vectorial_pgvector_api():
    import sys, os, cv2
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "cv-worker")))
    from vector_engine import VectorEngine

    img = cv2.imread("SetImagenesBuenas/CocaColaSet/Cocacolanormal.jpg")
    assert img is not None
    engine = VectorEngine()
    vec = engine.extraer_vector(img).tolist()

    response = client.post("/api/v1/productos/buscar-vector", json={
        "vector": vec,
        "umbral": 0.70,
        "limite": 2
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert "Coca-Cola" in data[0]["nombre"]
    assert data[0]["similitud"] >= 0.75


def test_evento_cv_deteccion_por_vector():
    import sys, os, cv2
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "cv-worker")))
    from vector_engine import VectorEngine

    # 1. Iniciar venta
    res_crear = client.post("/api/v1/ventas")
    venta_id = res_crear.json()["id"]

    # 2. Extraer vector de Sabritas
    img = cv2.imread("SetImagenesBuenas/SabritasPapas/Papasnormal.png")
    assert img is not None
    engine = VectorEngine()
    vec = engine.extraer_vector(img).tolist()

    # 3. Enviar evento CV sin código de barras pero con vector
    res_cv = client.post(
        "/api/v1/cv/deteccion",
        json={
            "venta_id": venta_id,
            "vector": vec,
            "clase_yolo": "sabritas",
            "confianza": 0.90,
            "es_fallback": False
        }
    )
    assert res_cv.status_code == 200
    data = res_cv.json()
    assert data["status"] == "agregado"
    assert "Sabritas" in data["producto"]["nombre"]

