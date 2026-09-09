from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class ProductoBase(BaseModel):
    codigo_barras: str = Field(..., description="Código de barras EAN/UPC o identificador único")
    nombre: str = Field(..., min_length=1, max_length=255)
    descripcion: Optional[str] = None
    precio: float = Field(..., ge=0, description="Precio unitario de venta")
    categoria: Optional[str] = "General"
    imagen_url: Optional[str] = None
    activo: bool = True


class ProductoCreate(ProductoBase):
    pass


class ProductoUpdate(BaseModel):
    codigo_barras: Optional[str] = None
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    precio: Optional[float] = Field(None, ge=0)
    categoria: Optional[str] = None
    imagen_url: Optional[str] = None
    activo: Optional[bool] = None


class ProductoResponse(ProductoBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductoConInventario(ProductoResponse):
    stock_actual: int = 0
    stock_minimo: int = 5
    ubicacion: Optional[str] = None


class VectorSearchRequest(BaseModel):
    vector: List[float] = Field(..., description="Vector embedding de 512 dimensiones normalizado")
    umbral: float = Field(default=0.75, ge=0.0, le=1.0, description="Umbral mínimo de similitud de coseno")
    limite: int = Field(default=3, ge=1, le=20, description="Cantidad máxima de coincidencias")


class VectorMatchResponse(BaseModel):
    id: UUID
    codigo_barras: str
    nombre: str
    precio: float
    similitud: float

