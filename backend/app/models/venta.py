from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field
from app.models.producto import ProductoResponse


class EstadoVenta(str, Enum):
    ABIERTA = "abierta"
    COMPLETADA = "completada"
    CANCELADA = "cancelada"


class MetodoDeteccion(str, Enum):
    CV_YOLO = "cv_yolo"
    CV_BARCODE = "cv_barcode"
    MANUAL = "manual"


class MetodoPago(str, Enum):
    EFECTIVO = "efectivo"
    TARJETA = "tarjeta"
    TRANSFERENCIA = "transferencia"
    OTRO = "otro"


# --- Items de Venta ---

class ItemVentaCreate(BaseModel):
    producto_id: Optional[UUID] = Field(None, description="UUID del producto (opcional si se pasa codigo_barras)")
    codigo_barras: Optional[str] = Field(None, description="Código de barras detectado o escaneado")
    cantidad: int = Field(default=1, gt=0, description="Cantidad a agregar")
    metodo_deteccion: MetodoDeteccion = Field(
        default=MetodoDeteccion.MANUAL,
        description="Origen de la detección: cv_yolo, cv_barcode o manual"
    )


class ItemVentaUpdate(BaseModel):
    cantidad: int = Field(..., gt=0, description="Nueva cantidad para el producto")


class DetalleVentaResponse(BaseModel):
    id: UUID
    venta_id: UUID
    producto_id: UUID
    cantidad: int
    precio_unitario: float
    subtotal: float
    metodo_deteccion: str
    created_at: datetime
    producto: Optional[ProductoResponse] = None

    model_config = {"from_attributes": True}


# --- Ventas ---

class VentaCreate(BaseModel):
    pass  # Crea una venta vacía con folio autogenerado


class VentaCerrarRequest(BaseModel):
    metodo_pago: MetodoPago = Field(default=MetodoPago.EFECTIVO, description="Método con el que paga el cliente")


class VentaResponse(BaseModel):
    sync_status: str = "online"
    id: UUID
    folio: str
    estado: EstadoVenta
    subtotal: float
    impuestos: float
    total: float
    metodo_pago: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: List[DetalleVentaResponse] = []

    model_config = {"from_attributes": True}


class VentaCerradaResponse(BaseModel):
    sync_status: str = "synced"
    success: bool
    venta_id: UUID
    folio: str
    total: float
    estado: str
    metodo_pago: str
    mensaje: str = "Venta completada e inventario descontado con éxito."
