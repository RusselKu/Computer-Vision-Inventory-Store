from typing import List, Optional
from uuid import UUID
from app.core.supabase import get_supabase_client
from app.models.inventario import InventarioUpdate


class InventarioService:
    @staticmethod
    def listar(solo_bajo_stock: bool = False, limit: int = 100, offset: int = 0) -> List[dict]:
        supabase = get_supabase_client()
        query = supabase.table("inventario").select("*, productos(*)").order("updated_at", desc=True)

        res = query.range(offset, offset + limit - 1).execute()
        items = res.data

        if solo_bajo_stock:
            items = [item for item in items if item.get("stock_actual", 0) <= item.get("stock_minimo", 5)]

        return items

    @staticmethod
    def obtener_por_producto_id(producto_id: UUID) -> Optional[dict]:
        supabase = get_supabase_client()
        res = supabase.table("inventario").select("*, productos(*)").eq("producto_id", str(producto_id)).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def actualizar(producto_id: UUID, data: InventarioUpdate) -> Optional[dict]:
        supabase = get_supabase_client()
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        if not update_data:
            return InventarioService.obtener_por_producto_id(producto_id)

        res = supabase.table("inventario").update(update_data).eq("producto_id", str(producto_id)).execute()
        return res.data[0] if res.data else None
