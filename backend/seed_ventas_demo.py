"""
Genera ventas de muestra (demo) en Supabase para poder probar el Informe
Ejecutivo con datos reales de "Hoy", "Semana", "Mes" y rangos personalizados.

Usa el mismo cliente de Supabase que ya configura el backend (lee las
credenciales de backend/.env), y solo escribe en las tablas `ventas` y
`detalle_ventas`. NO modifica el inventario (stock_actual) para no alterar
tus datos reales de stock.

Cómo correrlo (elige una opción):

  A) Dentro del contenedor del backend (recomendado, ya tiene las libs y el .env):
       docker exec -it pos_core_api python seed_ventas_demo.py

  B) Localmente, parado en la carpeta backend/, con tu venv activado:
       cd backend
       pip install -r requirements.txt   # si no lo has hecho
       python seed_ventas_demo.py

Parámetros opcionales:
  --num   N   número de ventas a crear (default: 25)
  --dias  N   ventana de días hacia atrás en la que se distribuyen (default: 30)
  --dry-run   solo muestra qué haría, sin escribir nada en la base de datos

Ejemplos:
  python seed_ventas_demo.py --num 40 --dias 45
  python seed_ventas_demo.py --dry-run
"""

import argparse
import random
import uuid
from datetime import datetime, timedelta, timezone

from app.core.supabase import get_supabase_client


def cargar_productos(supabase):
    """Trae productos activos con precio > 0, para armar tickets realistas."""
    res = (
        supabase.table("productos")
        .select("id, nombre, precio, categoria, activo")
        .eq("activo", True)
        .execute()
    )
    productos = [p for p in (res.data or []) if p.get("precio", 0) > 0]
    if not productos:
        raise SystemExit(
            "No se encontraron productos activos con precio > 0 en la tabla 'productos'. "
            "Agrega productos al catálogo antes de generar ventas de muestra."
        )
    return productos


def fecha_aleatoria(dias_atras, ahora):
    """
    Genera una fecha/hora aleatoria dentro de la ventana, con más peso en
    horario "de tienda" (9am-9pm) para que se vea realista en 'hora pico'.
    """
    dia_offset = random.randint(0, dias_atras)
    hora = random.choices(
        population=list(range(24)),
        weights=[1, 1, 1, 1, 1, 1, 2, 4, 6, 8, 9, 9, 10, 9, 8, 9, 10, 10, 9, 7, 5, 3, 2, 1],
        k=1,
    )[0]
    minuto = random.randint(0, 59)
    segundo = random.randint(0, 59)
    fecha = ahora - timedelta(days=dia_offset)
    fecha = fecha.replace(hour=hora, minute=minuto, second=segundo, microsecond=0)

    # Nunca generar una venta "en el futuro" (p. ej. si hoy es 4pm, no crear
    # una venta de las 9pm de hoy mismo).
    if fecha > ahora:
        fecha = ahora - timedelta(minutes=random.randint(1, 180))

    return fecha


def generar_venta(productos, fecha):
    """Arma una venta con 1-4 productos distintos y cantidades 1-3."""
    n_items = random.randint(1, min(4, len(productos)))
    elegidos = random.sample(productos, n_items)

    items = []
    subtotal_total = 0.0
    for prod in elegidos:
        cantidad = random.randint(1, 3)
        precio_unitario = float(prod["precio"])
        subtotal = round(cantidad * precio_unitario, 2)
        subtotal_total += subtotal

        # 80% detectado por cámara/código de barras, 20% manual
        metodo = random.choices(
            population=["cv_yolo", "cv_barcode", "manual"],
            weights=[45, 35, 20],
            k=1,
        )[0]

        items.append({
            "producto_id": prod["id"],
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "subtotal": subtotal,
            "metodo_deteccion": metodo,
        })

    metodo_pago = random.choices(
        population=["efectivo", "tarjeta", "transferencia"],
        weights=[55, 35, 10],
        k=1,
    )[0]

    total = round(subtotal_total, 2)
    folio = f"VTA-DEMO-{fecha.strftime('%Y%m%d%H%M')}-{random.randint(1000, 9999)}"

    return {
        "folio": folio,
        "subtotal": total,
        "impuestos": 0.0,
        "total": total,
        "metodo_pago": metodo_pago,
        "created_at": fecha.isoformat(),
        "updated_at": fecha.isoformat(),
        "items": items,
    }


def main():
    parser = argparse.ArgumentParser(description="Genera ventas de muestra para el Informe Ejecutivo.")
    parser.add_argument("--num", type=int, default=25, help="Número de ventas a crear (default: 25)")
    parser.add_argument("--dias", type=int, default=30, help="Ventana de días hacia atrás (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="No escribe en la base de datos, solo muestra el plan")
    args = parser.parse_args()

    ahora = datetime.now(timezone.utc)

    if args.dry_run:
        print(f"[DRY RUN] Se generarían {args.num} ventas distribuidas en los últimos {args.dias} días.\n")
        # En dry-run no necesitamos productos reales, solo mostrar el patrón de fechas
        for _ in range(min(args.num, 10)):
            f = fecha_aleatoria(args.dias, ahora)
            print(f"  - {f.strftime('%Y-%m-%d %H:%M')}")
        if args.num > 10:
            print(f"  ... y {args.num - 10} más")
        print("\nCorre sin --dry-run para escribir de verdad en Supabase.")
        return

    supabase = get_supabase_client()
    productos = cargar_productos(supabase)
    print(f"Catálogo cargado: {len(productos)} producto(s) activo(s) disponibles para generar ventas.\n")

    creadas = 0
    total_generado = 0.0

    for _ in range(args.num):
        fecha = fecha_aleatoria(args.dias, ahora)
        venta = generar_venta(productos, fecha)
        items = venta.pop("items")

        # 1) Crear la venta ya como 'completada', con la fecha backdateada
        venta_row = {
            **venta,
            "id": str(uuid.uuid4()),
            "estado": "completada",
        }
        res_venta = supabase.table("ventas").insert(venta_row).execute()
        if not res_venta.data:
            print(f"  ! No se pudo crear la venta {venta_row['folio']}, se omite.")
            continue
        venta_id = res_venta.data[0]["id"]

        # 2) Insertar los items de esa venta
        for item in items:
            supabase.table("detalle_ventas").insert({
                **item,
                "venta_id": venta_id,
                "created_at": venta_row["created_at"],
            }).execute()

        # 3) Re-afirmar fecha/estado/total por si algún trigger los recalculó con NOW()
        supabase.table("ventas").update({
            "estado": "completada",
            "subtotal": venta_row["subtotal"],
            "total": venta_row["total"],
            "created_at": venta_row["created_at"],
            "updated_at": venta_row["updated_at"],
        }).eq("id", venta_id).execute()

        creadas += 1
        total_generado += venta_row["total"]
        print(f"  ✓ {venta_row['folio']}  ·  {venta_row['created_at'][:16].replace('T', ' ')}  ·  ${venta_row['total']:.2f}  ·  {len(items)} producto(s)")

    print(f"\nListo: {creadas}/{args.num} ventas de muestra creadas.")
    print(f"Ingresos totales generados: ${total_generado:.2f}")
    print("El inventario (stock_actual) NO se modificó.")


if __name__ == "__main__":
    main()
