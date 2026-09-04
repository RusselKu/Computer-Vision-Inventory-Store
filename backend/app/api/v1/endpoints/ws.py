import json
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["WebSockets"])

# Almacén en memoria de conexiones activas por venta_id
_active_connections: Dict[str, List[WebSocket]] = {}


async def connect_pos(venta_id: str, websocket: WebSocket):
    await websocket.accept()
    if venta_id not in _active_connections:
        _active_connections[venta_id] = []
    _active_connections[venta_id].append(websocket)


def disconnect_pos(venta_id: str, websocket: WebSocket):
    if venta_id in _active_connections:
        if websocket in _active_connections[venta_id]:
            _active_connections[venta_id].remove(websocket)
        if not _active_connections[venta_id]:
            del _active_connections[venta_id]


async def broadcast_pos_event(venta_id: str, payload: dict):
    """Transmite un evento a todos los clientes POS conectados a esta venta."""
    if venta_id in _active_connections:
        mensaje = json.dumps(payload)
        for ws in _active_connections[venta_id]:
            try:
                await ws.send_text(mensaje)
            except Exception:
                pass


@router.websocket("/ws/pos/{venta_id}")
async def websocket_pos_endpoint(websocket: WebSocket, venta_id: str):
    """
    Canal WebSocket en vivo para la pantalla del POS (Dev C).
    Recibe eventos en tiempo real cuando Dev B detecta un producto por visión.
    """
    await connect_pos(venta_id, websocket)
    try:
        # Enviar confirmación de conexión
        await websocket.send_text(json.dumps({
            "type": "CONECTADO",
            "venta_id": venta_id,
            "mensaje": "Conexión en tiempo real con POS establecida."
        }))
        while True:
            # Mantener conexión viva y escuchar mensajes de control del frontend
            data = await websocket.receive_text()
            # Echo / Ping-Pong
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        disconnect_pos(venta_id, websocket)
    except Exception:
        disconnect_pos(venta_id, websocket)
