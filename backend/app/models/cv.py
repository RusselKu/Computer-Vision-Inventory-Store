from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    x: int
    y: int
    w: int
    h: int


class CVDetectionEvent(BaseModel):
    venta_id: UUID = Field(..., description="ID de la venta activa en el POS")
    codigo_barras: Optional[str] = Field(None, description="Código de barras decodificado por pyzbar/QR")
    clase_yolo: Optional[str] = Field(None, description="Etiqueta o clase predicha por YOLOv8 (ej. coca_cola)")
    confianza: float = Field(default=1.0, ge=0.0, le=1.0, description="Nivel de confianza de la inferencia (0 a 1)")
    bounding_box: Optional[BoundingBox] = Field(None, description="Coordenadas del producto en el frame")
    es_fallback: bool = Field(default=False, description="True si la detección falló o tiene baja confianza y requiere atención manual")
    mensaje_error: Optional[str] = Field(None, description="Detalle técnico en caso de fallo de visión")


class CVDetectionResult(BaseModel):
    status: str = Field(..., description="'agregado', 'requiere_manual', o 'error'")
    mensaje: str
    producto: Optional[dict] = None
    item_id: Optional[UUID] = None
    venta_id: UUID
