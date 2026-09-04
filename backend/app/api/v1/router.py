from fastapi import APIRouter
from app.api.v1.endpoints import cv, inventario, productos, ventas, ws

api_router = APIRouter()

api_router.include_router(productos.router)
api_router.include_router(inventario.router)
api_router.include_router(ventas.router)
api_router.include_router(cv.router)
api_router.include_router(ws.router)
