import copy
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.services.checkout_queue import CheckoutQueue


SALE_ID = '00000000-0000-0000-0000-000000000001'
STAMP = '2026-09-08T12:00:00Z'


class Remote:
    def __init__(self):
        self.sale = dict(id=SALE_ID, folio='TEST-1', estado='abierta',
                         subtotal=18, total=18, impuestos=0,
                         created_at=STAMP, updated_at=STAMP, metodo_pago=None)
        self.items = [dict(id='00000000-0000-0000-0000-000000000002',
                           producto_id='00000000-0000-0000-0000-000000000003',
                           venta_id=SALE_ID, cantidad=1, precio_unitario=18,
                           subtotal=18, metodo_deteccion='manual', created_at=STAMP)]
        self.offline = False
        self.drop_response = False
        self.reject = False
        self.closes = 0

    def snapshot(self):
        return {**copy.deepcopy(self.sale), 'items': copy.deepcopy(self.items)}

    def table(self, table):
        remote = self
        class Query:
            def select(self, *args): return self
            def eq(self, *args): return self
            def order(self, *args): return self
            def limit(self, *args): return self
            def execute(self):
                if remote.offline:
                    raise httpx.ConnectError('offline')
                return SimpleNamespace(data=copy.deepcopy([remote.sale] if table == 'ventas' else remote.items))
        return Query()

    def rpc(self, name, args):
        assert name == 'fn_cerrar_venta'
        def execute():
            if self.offline:
                raise httpx.ConnectError('offline')
            if self.reject:
                raise HTTPException(400, 'Stock insuficiente')
            assert self.sale['estado'] == 'abierta', 'duplicate remote close'
            self.sale.update(estado='completada', metodo_pago=args['p_metodo_pago'])
            self.closes += 1
            if self.drop_response:
                self.drop_response = False
                raise httpx.ReadTimeout('response lost after commit')
            return SimpleNamespace(data=copy.deepcopy(self.sale))
        return SimpleNamespace(execute=execute)


@pytest.fixture
def setup_queue(tmp_path):
    remote = Remote()
    queue = CheckoutQueue(tmp_path / 'outbox.sqlite3', lambda: remote, retry_seconds=0)
    queue.cache(remote.snapshot())
    return queue, remote


def test_offline_restart_recovery_and_duplicate(setup_queue):
    queue, remote = setup_queue
    remote.offline = True
    queue.enqueue(SALE_ID, 'efectivo', queue.cached(SALE_ID))
    assert queue.process(SALE_ID)['success'] is False
    restored = CheckoutQueue(queue.path, lambda: remote, retry_seconds=0)
    assert restored.cached(SALE_ID)['total'] == 18
    remote.offline = False
    restored.drain()
    assert restored.response(SALE_ID)['success'] is True
    restored.enqueue(SALE_ID, 'efectivo', None)
    restored.process(SALE_ID)
    assert remote.closes == 1


def test_lost_response_is_reconciled_without_second_stock_discount(setup_queue):
    queue, remote = setup_queue
    remote.drop_response = True
    queue.enqueue(SALE_ID, 'efectivo', remote.snapshot())
    assert queue.process(SALE_ID)['sync_status'] == 'pending'
    assert remote.closes == 1
    queue.drain()
    assert queue.response(SALE_ID)['sync_status'] == 'synced'
    assert remote.closes == 1


def test_stock_rejection_is_visible_and_not_retried(setup_queue):
    queue, remote = setup_queue
    remote.reject = True
    queue.enqueue(SALE_ID, 'efectivo', remote.snapshot())
    queue.drain()
    assert queue.status()['counts']['rejected'] == 1
    assert queue.get(SALE_ID)['error'] == 'Stock insuficiente'
    queue.drain()
    assert queue.get(SALE_ID)['attempts'] == 1
    queue.assert_editable(SALE_ID)
    remote.reject = False
    queue.enqueue(SALE_ID, 'efectivo', remote.snapshot())
    assert queue.process(SALE_ID)['success']


def test_immutable_payment_and_frozen_cart(setup_queue):
    queue, remote = setup_queue
    queue.enqueue(SALE_ID, 'efectivo', remote.snapshot())
    with pytest.raises(HTTPException) as error:
        queue.enqueue(SALE_ID, 'tarjeta', None)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException):
        queue.assert_editable(SALE_ID)


@pytest.mark.parametrize('change', ['total', 'items', 'cancelled', 'payment'])
def test_remote_changes_require_review(setup_queue, change):
    queue, remote = setup_queue
    queue.enqueue(SALE_ID, 'efectivo', remote.snapshot())
    if change == 'total': remote.sale['total'] = 36
    if change == 'items': remote.items[0]['cantidad'] = 2
    if change == 'cancelled': remote.sale['estado'] = 'cancelada'
    if change == 'payment': remote.sale.update(estado='completada', metodo_pago='tarjeta')
    with pytest.raises(HTTPException):
        queue.process(SALE_ID)
    assert remote.closes == 0


def test_multiple_claimants_only_close_once(setup_queue):
    queue, remote = setup_queue
    queue.enqueue(SALE_ID, 'efectivo', remote.snapshot())
    second = CheckoutQueue(queue.path, lambda: remote)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda q: q.process(SALE_ID), [queue, second]))
    assert any(r['success'] for r in results)
    assert remote.closes == 1


def test_expired_lease_recovers_after_crash(setup_queue):
    queue, remote = setup_queue
    queue.enqueue(SALE_ID, 'efectivo', remote.snapshot())
    with queue.connect() as db:
        db.execute("UPDATE checkouts SET state='processing', owner='dead', next_attempt=0")
    queue.drain()
    assert remote.closes == 1


def test_configuration_errors_do_not_retry(setup_queue):
    queue, remote = setup_queue
    queue.enqueue(SALE_ID, 'efectivo', remote.snapshot())
    def broken(): raise ValueError('invalid credentials')
    queue.client_factory = broken
    queue.drain()
    assert queue.get(SALE_ID)['state'] == 'rejected'


def test_api_pending_cached_cart_then_synced(setup_queue, monkeypatch):
    from app.main import app
    from app.services import checkout_queue, ventas_service
    queue, remote = setup_queue
    monkeypatch.setattr(checkout_queue, '_queue', queue)
    monkeypatch.setattr(ventas_service, 'get_supabase_client', lambda: remote)
    client = TestClient(app)
    remote.offline = True
    response = client.post(f'/api/v1/ventas/{SALE_ID}/cerrar', json={'metodo_pago': 'efectivo'})
    assert response.status_code == 202
    assert response.json()['success'] is False
    assert client.get(f'/api/v1/ventas/{SALE_ID}').json()['sync_status'] == 'pending'
    assert client.delete(f'/api/v1/ventas/{SALE_ID}/items/{remote.items[0]["id"]}').status_code == 409
    assert client.get('/api/v1/resiliencia').json()['counts']['pending'] == 1
    remote.offline = False
    queue.drain()
    response = client.post(f'/api/v1/ventas/{SALE_ID}/cerrar', json={'metodo_pago': 'efectivo'})
    assert response.status_code == 200
    assert response.json()['success'] is True
    assert client.get(f'/api/v1/ventas/{SALE_ID}').json()['estado'] == 'completada'
    assert remote.closes == 1


def test_no_snapshot_does_not_claim_offline_success(setup_queue, monkeypatch):
    from app.services import checkout_queue, ventas_service
    queue, remote = setup_queue
    monkeypatch.setattr(checkout_queue, '_queue', queue)
    monkeypatch.setattr(ventas_service, 'get_supabase_client', lambda: remote)
    remote.offline = True
    with pytest.raises(httpx.ConnectError):
        ventas_service.VentasService.cerrar_venta(UUID('00000000-0000-0000-0000-000000000099'))
    assert queue.status()['counts'] == {}


def test_fallback_websocket_preserves_message_and_measurement():
    from app.main import app
    client = TestClient(app)
    with client.websocket_connect(f'/api/v1/ws/pos/{SALE_ID}') as ws:
        ws.receive_json()
        response = client.post('/api/v1/cv/deteccion', json={
            'venta_id': SALE_ID, 'es_fallback': True, 'mensaje_error': 'Lectura fallida',
            'captured_at_ms': 1234, 'measurement_source': 'camera',
        })
        assert response.json()['status'] == 'requiere_manual'
        event = ws.receive_json()
        assert event['mensaje'] == 'Lectura fallida'
        assert event['captured_at_ms'] == 1234
        assert event['measurement_source'] == 'camera'


def test_cached_listing_restores_pending_after_reload(setup_queue):
    queue, remote = setup_queue
    queue.enqueue(SALE_ID, 'efectivo', remote.snapshot())
    assert queue.cached_sales('abierta')[0]['sync_status'] == 'pending'
    queue.drain()
    assert queue.cached_sales('abierta') == []
    assert queue.cached_sales('completada')[0]['sync_status'] == 'synced'
