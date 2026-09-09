"""Measure synthetic detection -> WS -> refreshed cart. Does not measure camera/AI."""
import argparse
import asyncio
import csv
import json
import math
import time
from pathlib import Path

import httpx
from websockets.asyncio.client import connect


async def measure(base, barcode, samples, output):
    values = []
    async with httpx.AsyncClient(base_url=base, timeout=15) as client:
        for _ in range(samples):
            response = await client.post('/api/v1/ventas')
            response.raise_for_status()
            sale_id = response.json()['id']
            try:
                ws_url = base.replace('http://', 'ws://').replace('https://', 'wss://') + f'/api/v1/ws/pos/{sale_id}'
                async with connect(ws_url) as ws:
                    await asyncio.wait_for(ws.recv(), timeout=10)  # Connected acknowledgement.
                    started = time.perf_counter()
                    response = await client.post('/api/v1/cv/deteccion', json={
                        'venta_id': sale_id, 'codigo_barras': barcode, 'confianza': 1,
                    })
                    response.raise_for_status()
                    if response.json()['status'] != 'agregado':
                        raise RuntimeError('El producto no se agregó; muestra inválida.')
                    async with asyncio.timeout(15):
                        while json.loads(await ws.recv()).get('type') != 'ITEM_AGREGADO_CV':
                            pass
                    response = await client.get(f'/api/v1/ventas/{sale_id}')
                    response.raise_for_status()
                    assert response.json()['items']
                    values.append((time.perf_counter() - started) * 1000)
            finally:
                response = await client.post(f'/api/v1/ventas/{sale_id}/cancelar')
                response.raise_for_status()
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['sample', 'synthetic_detection_to_cart_ms'])
        writer.writerows(enumerate(values, start=1))
    p95 = sorted(values)[math.ceil(len(values) * 0.95) - 1]
    print(f'n={len(values)}, p95={p95:.1f} ms; excluye cámara, inferencia y render del navegador.')
    return p95


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://localhost:8000')
    parser.add_argument('--barcode', default='7501055312107')
    parser.add_argument('--samples', type=int, default=30)
    parser.add_argument('--output', default='reports/latency.csv')
    args = parser.parse_args()
    if args.samples < 1:
        parser.error('--samples debe ser positivo')
    p95 = asyncio.run(measure(args.base.rstrip('/'), args.barcode, args.samples, args.output))
    raise SystemExit(0 if p95 < 1500 else 1)
