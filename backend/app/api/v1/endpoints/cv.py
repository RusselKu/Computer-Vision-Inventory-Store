from fastapi import APIRouter, status
from app.models.cv import CVDetectionEvent, CVDetectionResult
from app.models.venta import ItemVentaCreate, MetodoDeteccion
from app.services.productos_service import ProductosService
from app.services.ventas_service import VentasService
from app.api.v1.endpoints.ws import broadcast_pos_event

router = APIRouter(prefix="/cv", tags=["Visión por Computadora (Dev B)"])


@router.post("/deteccion", response_model=CVDetectionResult, summary="Recepción de evento de visión por computadora")
async def recibir_deteccion_cv(evento: CVDetectionEvent):
    """
    Contrato con Dev B:
    Recibe la inferencia de YOLOv8 o lectura de pyzbar.
    - Si la detección fue exitosa, inyecta el producto al carrito de la venta activa y notifica por WebSocket.
    - Si es fallback o baja confianza, genera una alerta para que el POS solicite captura manual.
    """
    # 1. Manejo de Fallback (Lectura fallida tras N frames o evento sin datos)
    if evento.es_fallback or (not evento.codigo_barras and not evento.clase_yolo and not evento.vector):
        mensaje_alerta = evento.mensaje_error or "Detección fallida o no concluyente. Requiere captura manual."
        await broadcast_pos_event(str(evento.venta_id), {
            "type": "ALERTA_CV_FALLBACK",
            "mensaje": mensaje_alerta,
            "confianza": evento.confianza,
            "bounding_box": evento.bounding_box.model_dump() if evento.bounding_box else None
        })
        return CVDetectionResult(
            status="requiere_manual",
            mensaje=mensaje_alerta,
            venta_id=evento.venta_id
        )

    # 2. Determinar método y código de barras
    codigo_a_buscar = evento.codigo_barras
    metodo = MetodoDeteccion.CV_BARCODE if evento.codigo_barras else MetodoDeteccion.CV_YOLO

    # Si no hay código de barras pero se envió vector embedding, buscar en Supabase (pgvector)
    if not codigo_a_buscar and evento.vector:
        matches = ProductosService.buscar_por_vector(evento.vector, umbral=0.75, limite=1)
        if matches:
            top_match = matches[0]
            codigo_a_buscar = top_match["codigo_barras"]
            evento.confianza = float(top_match.get("similitud", evento.confianza))
            metodo = MetodoDeteccion.CV_YOLO

    # Si solo viene clase YOLO y aún no hay código, buscar por coincidencia en catálogo
    if not codigo_a_buscar and evento.clase_yolo:
        prods = ProductosService.listar(q=evento.clase_yolo, limit=1)
        if prods:
            codigo_a_buscar = prods[0]["codigo_barras"]

    if not codigo_a_buscar:
        mensaje = f"No se encontró producto asociado a la detección: clase='{evento.clase_yolo}'"
        await broadcast_pos_event(str(evento.venta_id), {
            "type": "ALERTA_CV_NO_ENCONTRADO",
            "mensaje": mensaje
        })
        return CVDetectionResult(
            status="requiere_manual",
            mensaje=mensaje,
            venta_id=evento.venta_id
        )

    # 3. Agregar al carrito de la venta activa
    try:
        venta_actualizada = VentasService.agregar_item(
            venta_id=evento.venta_id,
            item_data=ItemVentaCreate(
                codigo_barras=codigo_a_buscar,
                cantidad=1,
                metodo_deteccion=metodo
            )
        )

        prod_agregado = ProductosService.obtener_por_codigo_barras(codigo_a_buscar)

        # Notificar en tiempo real al POS por WebSocket
        await broadcast_pos_event(str(evento.venta_id), {
            "type": "ITEM_AGREGADO_CV",
            "producto": prod_agregado,
            "metodo": metodo.value,
            "confianza": evento.confianza,
            "total_venta": venta_actualizada.get("total", 0.0)
        })

        return CVDetectionResult(
            status="agregado",
            mensaje=f"Producto '{prod_agregado['nombre']}' agregado con éxito mediante visión.",
            producto=prod_agregado,
            venta_id=evento.venta_id
        )
    except Exception as e:
        await broadcast_pos_event(str(evento.venta_id), {
            "type": "ERROR_CV_AGREGAR",
            "mensaje": str(e)
        })
        return CVDetectionResult(
            status="error",
            mensaje=f"Error al registrar item: {str(e)}",
            venta_id=evento.venta_id
        )
