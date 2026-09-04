from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, status
from app.models.producto import ProductoConInventario, ProductoCreate, ProductoResponse, ProductoUpdate
from app.services.productos_service import ProductosService

router = APIRouter(prefix="/productos", tags=["Productos & Catálogo"])


@router.get("", response_model=List[ProductoConInventario], summary="Listar o buscar productos")
def listar_productos(
    categoria: Optional[str] = Query(None, description="Filtrar por categoría (ej. Bebidas, Snacks)"),
    q: Optional[str] = Query(None, description="Buscar por nombre o código de barras"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Retorna el catálogo de productos con su stock e información de inventario."""
    return ProductosService.listar(categoria=categoria, q=q, limit=limit, offset=offset)


@router.get("/codigo/{codigo_barras}", response_model=ProductoConInventario, summary="Buscar producto por código de barras")
def obtener_por_codigo_barras(codigo_barras: str):
    """Endpoint de alta velocidad para escáneres de código de barras o módulo de visión (Dev B)."""
    prod = ProductosService.obtener_por_codigo_barras(codigo_barras)
    if not prod:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto con código de barras '{codigo_barras}' no encontrado"
        )
    return prod


@router.get("/{producto_id}", response_model=ProductoConInventario, summary="Obtener producto por ID")
def obtener_por_id(producto_id: UUID):
    prod = ProductosService.obtener_por_id(producto_id)
    if not prod:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto {producto_id} no encontrado"
        )
    return prod


@router.post("", response_model=ProductoConInventario, status_code=status.HTTP_201_CREATED, summary="Crear nuevo producto")
def crear_producto(producto: ProductoCreate, stock_inicial: int = Query(0, ge=0)):
    return ProductosService.crear(producto, stock_inicial=stock_inicial)


@router.patch("/{producto_id}", response_model=ProductoConInventario, summary="Actualizar producto")
def actualizar_producto(producto_id: UUID, data: ProductoUpdate):
    prod = ProductosService.actualizar(producto_id, data)
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto {producto_id} no encontrado")
    return prod
