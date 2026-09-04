from typing import List, Optional
from uuid import UUID
from app.core.supabase import get_supabase_client
from app.models.producto import ProductoCreate, ProductoUpdate


class ProductosService:
    @staticmethod
    def listar(categoria: Optional[str] = None, q: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[dict]:
        supabase = get_supabase_client()
        query = supabase.table("productos").select("*, inventario(stock_actual, stock_minimo, ubicacion)")

        if categoria:
            query = query.eq("categoria", categoria)
        if q:
            # Búsqueda por nombre o código de barras
            query = query.or_(f"nombre.ilike.%{q}%,codigo_barras.ilike.%{q}%")

        query = query.order("nombre").range(offset, offset + limit - 1)
        res = query.execute()

        productos = []
        for row in res.data:
            inv = row.pop("inventario", None)
            if isinstance(inv, list) and len(inv) > 0:
                inv = inv[0]
            elif not isinstance(inv, dict):
                inv = {}

            row["stock_actual"] = inv.get("stock_actual", 0)
            row["stock_minimo"] = inv.get("stock_minimo", 5)
            row["ubicacion"] = inv.get("ubicacion", "Estante A-1")
            productos.append(row)

        return productos

    @staticmethod
    def obtener_por_id(producto_id: UUID) -> Optional[dict]:
        supabase = get_supabase_client()
        res = supabase.table("productos").select("*, inventario(stock_actual, stock_minimo, ubicacion)").eq("id", str(producto_id)).execute()
        if not res.data:
            return None
        row = res.data[0]
        inv = row.pop("inventario", None)
        if isinstance(inv, list) and len(inv) > 0:
            inv = inv[0]
        elif not isinstance(inv, dict):
            inv = {}
        row["stock_actual"] = inv.get("stock_actual", 0)
        row["stock_minimo"] = inv.get("stock_minimo", 5)
        row["ubicacion"] = inv.get("ubicacion", "Estante A-1")
        return row

    @staticmethod
    def obtener_por_codigo_barras(codigo_barras: str) -> Optional[dict]:
        supabase = get_supabase_client()
        res = supabase.table("productos").select("*, inventario(stock_actual, stock_minimo, ubicacion)").eq("codigo_barras", codigo_barras).execute()
        if not res.data:
            return None
        row = res.data[0]
        inv = row.pop("inventario", None)
        if isinstance(inv, list) and len(inv) > 0:
            inv = inv[0]
        elif not isinstance(inv, dict):
            inv = {}
        row["stock_actual"] = inv.get("stock_actual", 0)
        row["stock_minimo"] = inv.get("stock_minimo", 5)
        row["ubicacion"] = inv.get("ubicacion", "Estante A-1")
        return row

    @staticmethod
    def crear(data: ProductoCreate, stock_inicial: int = 0) -> dict:
        supabase = get_supabase_client()
        prod_data = data.model_dump()
        res = supabase.table("productos").insert(prod_data).execute()
        nuevo_prod = res.data[0]

        # Crear fila de inventario asociada
        supabase.table("inventario").insert({
            "producto_id": nuevo_prod["id"],
            "stock_actual": stock_inicial,
            "stock_minimo": 5,
            "ubicacion": "Estante A-1"
        }).execute()

        nuevo_prod["stock_actual"] = stock_inicial
        nuevo_prod["stock_minimo"] = 5
        nuevo_prod["ubicacion"] = "Estante A-1"
        return nuevo_prod

    @staticmethod
    def actualizar(producto_id: UUID, data: ProductoUpdate) -> Optional[dict]:
        supabase = get_supabase_client()
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        if not update_data:
            return ProductosService.obtener_por_id(producto_id)

        res = supabase.table("productos").update(update_data).eq("id", str(producto_id)).execute()
        if not res.data:
            return None
        return ProductosService.obtener_por_id(producto_id)
