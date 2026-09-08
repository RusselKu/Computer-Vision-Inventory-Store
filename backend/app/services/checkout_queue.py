"""Durable checkout outbox. SQLite belongs to one POS API instance.

Remote stock remains authoritative. A pending request is NOT a confirmed sale.
The existing atomic fn_cerrar_venta is the remote duplicate-close guard.
"""
import json
import sqlite3
import threading
import time
from functools import wraps
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import HTTPException


def is_transient(error):
    if isinstance(error, (httpx.TransportError, ConnectionError, TimeoutError)):
        return True
    # PostgREST connection/pool failures; business SQL exceptions must not retry.
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in {429, 500, 502, 503, 504}
    return str(getattr(error, "code", "")) in {
        "PGRST000", "PGRST001", "PGRST002", "PGRST003", "53300", "57P01",
        "429", "500", "502", "503", "504",
    }


def serialize_sale(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with get_checkout_queue().lock:
            return function(*args, **kwargs)
    return wrapped


class CheckoutQueue:
    def __init__(self, path, client_factory, retry_seconds=5):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        self.client_factory = client_factory
        self.retry_seconds = retry_seconds
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    venta_id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checkouts (
                    venta_id TEXT PRIMARY KEY, metodo_pago TEXT NOT NULL,
                    snapshot TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0,
                    owner TEXT, result TEXT, error TEXT,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def cache(self, sale):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO snapshots VALUES (?, ?)",
                       (str(sale['id']), json.dumps(sale, default=str)))
        return sale

    def cached(self, sale_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM snapshots WHERE venta_id=?", (str(sale_id),)).fetchone()
        return json.loads(row['payload']) if row else None

    def cached_sales(self, state=None, limit=50, offset=0):
        with self.connect() as db:
            sales = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM snapshots')]
        for sale in sales:
            sale['sync_status'] = 'offline'
            entry = self.get(sale['id'])
            if entry:
                sale['sync_status'] = entry['state']
                if entry['state'] == 'synced':
                    sale['estado'] = 'completada'
                    sale['metodo_pago'] = entry['metodo_pago']
        sales = [sale for sale in sales if not state or sale['estado'] == state]
        sales.sort(key=lambda sale: sale['created_at'], reverse=True)
        return sales[offset:offset + limit]

    def get(self, sale_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM checkouts WHERE venta_id=?", (str(sale_id),)).fetchone()
        return dict(row) if row else None

    def assert_editable(self, sale_id):
        entry = self.get(sale_id)
        if entry and entry['state'] != 'rejected':
            raise HTTPException(409, "La venta tiene un cierre registrado; no se puede modificar.")

    def enqueue(self, sale_id, method, snapshot):
        sale_id = str(sale_id)
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM checkouts WHERE venta_id=?", (sale_id,)).fetchone()
            if row and row['state'] != 'rejected':
                if row['metodo_pago'] != method:
                    raise HTTPException(409, "El cierre ya está registrado con otro método de pago.")
                return
            if not snapshot or snapshot['estado'] != 'abierta' or not snapshot.get('items'):
                raise HTTPException(409, "Se requiere un carrito abierto, no vacío y previamente cargado.")
            db.execute("""INSERT OR REPLACE INTO checkouts
                (venta_id, metodo_pago, snapshot, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)""",
                (sale_id, method, json.dumps(snapshot, default=str), now, now))

    @staticmethod
    def result(sale, sale_id, method):
        return dict(success=True, venta_id=str(sale_id), folio=sale['folio'],
                    total=float(sale['total']), estado='completada',
                    metodo_pago=sale.get('metodo_pago') or method,
                    mensaje='Venta confirmada en Supabase.', sync_status='synced')

    def process(self, sale_id):
        sale_id = str(sale_id)
        owner = str(uuid4())
        now = time.time()
        with self.connect() as db:
            # Lease survives process crashes and prevents concurrent workers claiming a row.
            changed = db.execute("""UPDATE checkouts SET state='processing', owner=?,
                next_attempt=?, attempts=attempts+1, updated_at=?
                WHERE venta_id=? AND state IN ('pending','processing') AND next_attempt<=?""",
                (owner, now + 120, now, sale_id, now)).rowcount
        if not changed:
            return self.response(sale_id)
        entry = self.get(sale_id)
        try:
            client = self.client_factory()
            rows = client.table('ventas').select('*').eq('id', sale_id).execute().data
            if not rows:
                raise HTTPException(409, 'La venta ya no existe en Supabase.')
            remote = rows[0]
            snapshot = json.loads(entry['snapshot'])
            if float(remote['total']) != float(snapshot['total']):
                raise HTTPException(409, 'El total remoto cambió; revisar el carrito antes de cobrar.')
            if remote['estado'] == 'completada':
                if remote.get('metodo_pago') != entry['metodo_pago']:
                    raise HTTPException(409, 'Venta cerrada con otro método; requiere conciliación.')
                result = self.result(remote, sale_id, entry['metodo_pago'])
            elif remote['estado'] != 'abierta':
                raise HTTPException(409, 'La venta fue cancelada; requiere conciliación.')
            else:
                remote_items = client.table('detalle_ventas').select('*').eq('venta_id', sale_id).execute().data
                def signature(items):
                    return sorted((str(i['id']), str(i['producto_id']), int(i['cantidad']),
                                   float(i['precio_unitario'])) for i in items)
                if signature(remote_items) != signature(snapshot['items']):
                    raise HTTPException(409, 'El carrito remoto cambió; requiere revisión.')
                data = client.rpc('fn_cerrar_venta', {
                    'p_venta_id': sale_id, 'p_metodo_pago': entry['metodo_pago']
                }).execute().data
                result = self.result(data, sale_id, entry['metodo_pago'])
            self.finish(sale_id, owner, 'synced', result=result)
        except Exception as error:
            if is_transient(error):
                delay = min(300, self.retry_seconds * 2 ** min(entry['attempts'] - 1, 6))
                self.finish(sale_id, owner, 'pending', error='Conexión no disponible; se reintentará.', delay=delay)
            else:
                # Never retry a stock/business/configuration failure automatically.
                message = error.detail if isinstance(error, HTTPException) else 'Cierre rechazado por Supabase; revisar stock y configuración.'
                self.finish(sale_id, owner, 'rejected', error=str(message))
        return self.response(sale_id)

    def finish(self, sale_id, owner, state, result=None, error=None, delay=0):
        with self.connect() as db:
            db.execute("""UPDATE checkouts SET state=?, result=?, error=?, next_attempt=?,
                updated_at=?, owner=NULL WHERE venta_id=? AND owner=?""",
                (state, json.dumps(result) if result else None, error,
                 time.time() + delay, time.time(), sale_id, owner))

    def response(self, sale_id):
        entry = self.get(sale_id)
        if entry['state'] == 'synced':
            return json.loads(entry['result'])
        if entry['state'] == 'rejected':
            raise HTTPException(409, entry['error'])
        sale = json.loads(entry['snapshot'])
        return dict(success=False, venta_id=str(sale_id), folio=sale['folio'],
                    total=float(sale['total']), estado='pendiente_sincronizacion',
                    metodo_pago=entry['metodo_pago'], sync_status='pending',
                    mensaje='Cierre guardado localmente. Pendiente de confirmar stock y venta en Supabase.')

    def drain(self):
        with self.lock:
            with self.connect() as db:
                ids = db.execute("""SELECT venta_id FROM checkouts
                    WHERE state IN ('pending','processing') AND next_attempt<=?
                    ORDER BY created_at LIMIT 20""", (time.time(),)).fetchall()
            for row in ids:
                try:
                    self.process(row['venta_id'])
                except HTTPException:
                    pass  # A rejected sale must not starve the rest of the queue.

    def status(self):
        with self.connect() as db:
            counts = {row['state']: row['n'] for row in db.execute(
                "SELECT state, count(*) n FROM checkouts GROUP BY state")}
            pending = [dict(row) for row in db.execute("""SELECT venta_id, state,
                attempts, error, created_at, updated_at FROM checkouts
                WHERE state != 'synced' ORDER BY created_at LIMIT 100""")]
        return {'counts': counts, 'operations': pending}


_queue = None
_queue_lock = threading.Lock()


def get_checkout_queue():
    global _queue
    with _queue_lock:
        if _queue is None:
            from app.core.config import settings
            from app.core.supabase import get_supabase_client
            _queue = CheckoutQueue(settings.OFFLINE_DB_PATH, get_supabase_client,
                                   settings.SYNC_INTERVAL_SECONDS)
    return _queue
