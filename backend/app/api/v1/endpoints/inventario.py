from typing import List
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, status
from app.models.inventario import InventarioResponse, InventarioUpdate
from app.services.inventario_service import InventarioService

router = APIRouter(prefix="/inventario", tags=["Inventario & Stock"])


@router.get("", response_model=List[InventarioResponse], summary="Consultar inventario general")
def listar_inventario(
    solo_bajo_stock: bool = Query(False, description="Filtrar solo productos que estén en o por debajo de su stock mínimo"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Consulta el estado del inventario para el Dashboard de tracking (Dev D)."""
    return InventarioService.listar(solo_bajo_stock=solo_bajo_stock, limit=limit, offset=offset)


@router.get("/{producto_id}", response_model=InventarioResponse, summary="Consultar stock de un producto específico")
def obtener_inventario_producto(producto_id: UUID):
    inv = InventarioService.obtener_por_producto_id(producto_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventario no encontrado para el producto {producto_id}"
        )
    return inv


@router.patch("/{producto_id}", response_model=InventarioResponse, summary="Ajustar stock o umbral mínimo")
def ajustar_inventario(producto_id: UUID, data: InventarioUpdate):
    inv = InventarioService.actualizar(producto_id, data)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventario no encontrado para el producto {producto_id}"
        )
    return inv
