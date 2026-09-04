from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field
from app.models.producto import ProductoResponse


class InventarioBase(BaseModel):
    stock_actual: int = Field(..., ge=0, description="Cantidad disponible actual en tienda")
    stock_minimo: int = Field(default=5, ge=0, description="Umbral para alerta de reabastecimiento")
    ubicacion: Optional[str] = Field(default="Estante A-1", description="Ubicación física en tienda/almacén")


class InventarioUpdate(BaseModel):
    stock_actual: Optional[int] = Field(None, ge=0)
    stock_minimo: Optional[int] = Field(None, ge=0)
    ubicacion: Optional[str] = None


class InventarioResponse(InventarioBase):
    id: UUID
    producto_id: UUID
    updated_at: datetime
    producto: Optional[ProductoResponse] = None

    model_config = {"from_attributes": True}
