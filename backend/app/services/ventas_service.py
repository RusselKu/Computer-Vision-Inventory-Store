import datetime
import random
from typing import List, Optional
from uuid import UUID
from fastapi import HTTPException, status
from app.core.supabase import get_supabase_client
from app.models.venta import ItemVentaCreate, MetodoDeteccion, MetodoPago
from app.services.productos_service import ProductosService
from app.services.checkout_queue import get_checkout_queue, is_transient, serialize_sale


class VentasService:
    @staticmethod
    def _generar_folio() -> str:
        """Genera un folio único para la venta: VTA-YYYYMMDD-XXXX."""
        now = datetime.datetime.now(datetime.timezone.utc)
        sufijo = f"{random.randint(1000, 9999)}"
        return f"VTA-{now.strftime('%Y%m%d%H%M')}-{sufijo}"

    @staticmethod
    def crear_venta() -> dict:
        supabase = get_supabase_client()
        folio = VentasService._generar_folio()
        res = supabase.table("ventas").insert({
            "folio": folio,
            "estado": "abierta",
            "subtotal": 0.0,
            "impuestos": 0.0,
            "total": 0.0
        }).execute()

        if not res.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo crear la venta")
        
        venta = res.data[0]
        venta["items"] = []
        return venta

    @staticmethod
    def obtener_venta(venta_id: UUID) -> dict:
        queue = get_checkout_queue()
        try:
            venta = VentasService._obtener_venta_remota(venta_id)
            queue.cache(venta)
        except Exception as error:
            venta = queue.cached(venta_id) if is_transient(error) else None
            if venta is None:
                raise
            venta['sync_status'] = 'offline'
        entry = queue.get(venta_id)
        if entry:
            venta['sync_status'] = entry['state']
            if entry['state'] == 'synced':
                venta['estado'] = 'completada'
                venta['metodo_pago'] = entry['metodo_pago']
        return venta

    @staticmethod
    def _obtener_venta_remota(venta_id: UUID) -> dict:
        supabase = get_supabase_client()
        res = supabase.table("ventas").select("*").eq("id", str(venta_id)).execute()
        if not res.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Venta {venta_id} no encontrada")

        venta = res.data[0]
        # Cargar detalle con productos
        items_res = (
            supabase.table("detalle_ventas")
            .select("*, producto:productos(*)")
            .eq("venta_id", str(venta_id))
            .order("created_at")
            .execute()
        )
        venta["items"] = items_res.data or []
        return venta

    @staticmethod
    def listar_ventas(estado: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[dict]:
        queue = get_checkout_queue()
        try:
            sales = VentasService._listar_ventas_remotas(estado, limit, offset)
        except Exception as error:
            if not is_transient(error):
                raise
            return queue.cached_sales(estado, limit, offset)
        for sale in sales:
            queue.cache(sale)
            entry = queue.get(sale['id'])
            if entry:
                sale['sync_status'] = entry['state']
        return sales

    @staticmethod
    def _listar_ventas_remotas(estado: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[dict]:
        supabase = get_supabase_client()
        query = supabase.table("ventas").select("*, items:detalle_ventas(*, producto:productos(*))").order("created_at", desc=True)
        if estado:
            query = query.eq("estado", estado)
        res = query.range(offset, offset + limit - 1).execute()
        return res.data or []

    @staticmethod
    @serialize_sale
    def agregar_item(venta_id: UUID, item_data: ItemVentaCreate) -> dict:
        get_checkout_queue().assert_editable(venta_id)
        supabase = get_supabase_client()
        venta = VentasService.obtener_venta(venta_id)
        if venta["estado"] != "abierta":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se pueden agregar productos a una venta con estado '{venta['estado']}'"
            )

        # 1. Resolver producto
        producto = None
        if item_data.producto_id:
            producto = ProductosService.obtener_por_id(item_data.producto_id)
        elif item_data.codigo_barras:
            producto = ProductosService.obtener_por_codigo_barras(item_data.codigo_barras)

        if not producto:
            identificador = item_data.codigo_barras or item_data.producto_id
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto con identificador '{identificador}' no encontrado en el catálogo"
            )

        if not producto.get("activo", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El producto '{producto['nombre']}' se encuentra inactivo"
            )

        # 2. Verificar existencia en inventario
        stock_disponible = producto.get("stock_actual", 0)
        if stock_disponible < item_data.cantidad:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stock insuficiente para '{producto['nombre']}'. Disponible: {stock_disponible}, Solicitado: {item_data.cantidad}"
            )

        producto_id_str = str(producto["id"])
        precio_unitario = float(producto["precio"])

        # 3. Comprobar si el producto ya existe en el carrito
        item_existente = next((it for it in venta["items"] if it["producto_id"] == producto_id_str), None)

        if item_existente:
            nueva_cantidad = item_existente["cantidad"] + item_data.cantidad
            if stock_disponible < nueva_cantidad:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Stock insuficiente para incrementar '{producto['nombre']}'. Disponible: {stock_disponible}, Total en carrito: {nueva_cantidad}"
                )
            nuevo_subtotal = round(nueva_cantidad * precio_unitario, 2)
            supabase.table("detalle_ventas").update({
                "cantidad": nueva_cantidad,
                "subtotal": nuevo_subtotal,
                "metodo_deteccion": item_data.metodo_deteccion.value
            }).eq("id", item_existente["id"]).execute()
        else:
            subtotal = round(item_data.cantidad * precio_unitario, 2)
            supabase.table("detalle_ventas").insert({
                "venta_id": str(venta_id),
                "producto_id": producto_id_str,
                "cantidad": item_data.cantidad,
                "precio_unitario": precio_unitario,
                "subtotal": subtotal,
                "metodo_deteccion": item_data.metodo_deteccion.value
            }).execute()

        # Retornar la venta actualizada con totales recalculados por el trigger
        return VentasService.obtener_venta(venta_id)

    @staticmethod
    @serialize_sale
    def eliminar_item(venta_id: UUID, item_id: UUID) -> dict:
        get_checkout_queue().assert_editable(venta_id)
        supabase = get_supabase_client()
        venta = VentasService.obtener_venta(venta_id)
        if venta["estado"] != "abierta":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se pueden eliminar productos de una venta con estado '{venta['estado']}'"
            )

        res = supabase.table("detalle_ventas").delete().eq("id", str(item_id)).eq("venta_id", str(venta_id)).execute()
        if not res.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item de venta no encontrado")

        return VentasService.obtener_venta(venta_id)

    @staticmethod
    @serialize_sale
    def actualizar_cantidad_item(venta_id: UUID, item_id: UUID, nueva_cantidad: int) -> dict:
        get_checkout_queue().assert_editable(venta_id)
        supabase = get_supabase_client()
        venta = VentasService.obtener_venta(venta_id)
        if venta["estado"] != "abierta":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se puede modificar una venta con estado '{venta['estado']}'"
            )

        item = next((it for it in venta["items"] if it["id"] == str(item_id)), None)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item no encontrado en la venta")

        # Validar stock
        prod = ProductosService.obtener_por_id(UUID(item["producto_id"]))
        if prod and prod.get("stock_actual", 0) < nueva_cantidad:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stock insuficiente. Disponible: {prod.get('stock_actual', 0)}, Solicitado: {nueva_cantidad}"
            )

        precio_unitario = float(item["precio_unitario"])
        nuevo_subtotal = round(nueva_cantidad * precio_unitario, 2)

        supabase.table("detalle_ventas").update({
            "cantidad": nueva_cantidad,
            "subtotal": nuevo_subtotal
        }).eq("id", str(item_id)).execute()

        return VentasService.obtener_venta(venta_id)

    @staticmethod
    def cerrar_venta(venta_id: UUID, metodo_pago: MetodoPago = MetodoPago.EFECTIVO) -> dict:
        queue = get_checkout_queue()
        with queue.lock:
            entry = queue.get(venta_id)
            snapshot = None
            if not entry or entry['state'] == 'rejected':
                snapshot = VentasService.obtener_venta(venta_id)
            queue.enqueue(venta_id, metodo_pago.value, snapshot)
            return queue.process(venta_id)

    @staticmethod
    @serialize_sale
    def cancelar_venta(venta_id: UUID) -> dict:
        get_checkout_queue().assert_editable(venta_id)
        supabase = get_supabase_client()
        venta = VentasService.obtener_venta(venta_id)
        if venta["estado"] != "abierta":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Solo se pueden cancelar ventas abiertas (estado actual: '{venta['estado']}')"
            )

        supabase.table("ventas").update({
            "estado": "cancelada"
        }).eq("id", str(venta_id)).execute()

        return VentasService.obtener_venta(venta_id)
