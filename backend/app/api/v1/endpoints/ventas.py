from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Response, status
from app.models.venta import (
    ItemVentaCreate,
    ItemVentaUpdate,
    VentaCerradaResponse,
    VentaCerrarRequest,
    VentaCreate,
    VentaResponse,
)
from app.services.ventas_service import VentasService

router = APIRouter(prefix="/ventas", tags=["Ventas & POS Core"])


@router.post("", response_model=VentaResponse, status_code=status.HTTP_201_CREATED, summary="Iniciar nueva venta / carrito")
def crear_venta():
    """Genera una nueva venta vacía con folio único en estado 'abierta'."""
    return VentasService.crear_venta()


@router.get("", response_model=List[VentaResponse], summary="Listar ventas")
def listar_ventas(
    estado: Optional[str] = Query(None, description="Filtrar por estado: abierta, completada, cancelada"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    return VentasService.listar_ventas(estado=estado, limit=limit, offset=offset)


@router.get("/{venta_id}", response_model=VentaResponse, summary="Obtener detalle de la venta / carrito actual")
def obtener_venta(venta_id: UUID):
    """Devuelve la venta con todos los items calculados, subtotal, impuestos y total."""
    return VentasService.obtener_venta(venta_id)


@router.post("/{venta_id}/items", response_model=VentaResponse, summary="Agregar item al carrito (agregar_item)")
def agregar_item(venta_id: UUID, item: ItemVentaCreate):
    """
    Agrega un producto a la venta.
    Soporta lookup por `producto_id` o directamente por `codigo_barras`.
    Permite especificar el origen de detección (`cv_yolo`, `cv_barcode`, `manual`).
    """
    return VentasService.agregar_item(venta_id, item)


@router.delete("/{venta_id}/items/{item_id}", response_model=VentaResponse, summary="Eliminar item del carrito (eliminar_item)")
def eliminar_item(venta_id: UUID, item_id: UUID):
    """Elimina una línea de producto del carrito y recalcula el total automáticamente."""
    return VentasService.eliminar_item(venta_id, item_id)


@router.patch("/{venta_id}/items/{item_id}", response_model=VentaResponse, summary="Actualizar cantidad de un item")
@router.put("/{venta_id}/items/{item_id}", response_model=VentaResponse, summary="Actualizar cantidad de un item (PUT alias)")
def actualizar_cantidad_item(venta_id: UUID, item_id: UUID, payload: ItemVentaUpdate):
    """Modifica la cantidad de unidades de un producto en el carrito."""
    return VentasService.actualizar_cantidad_item(venta_id, item_id, payload.cantidad)


@router.post("/{venta_id}/cerrar", response_model=VentaCerradaResponse, summary="Cerrar y cobrar la venta (cerrar_venta)")
def cerrar_venta(venta_id: UUID, response: Response, payload: VentaCerrarRequest = VentaCerrarRequest()):
    """
    Finaliza la transacción de forma atómica:
    1. Bloquea las filas en Postgres y verifica existencias de cada producto.
    2. Descuenta el inventario formalmente.
    3. Cambia el estado a 'completada'.
    4. Emite el evento en Supabase Realtime para Dev D (Dashboard).
    """
    result = VentasService.cerrar_venta(venta_id, payload.metodo_pago)
    if not result['success']:
        response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.post("/{venta_id}/cancelar", response_model=VentaResponse, summary="Cancelar venta abierta")
def cancelar_venta(venta_id: UUID):
    """Cancela una venta abierta y libera los productos."""
    return VentasService.cancelar_venta(venta_id)
