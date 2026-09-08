"""Summarize JSON exported from window.POS_LATENCY_SAMPLES in the POS browser."""
import argparse
import json
import math
from pathlib import Path


def summarize(samples):
    values = [sample['frame_to_cart_ms'] for sample in samples if sample.get('source') == 'camera']
    if not values or any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('Sin muestras reales válidas; verifica reloj compartido y captura.')
    return len(values), sorted(values)[math.ceil(len(values) * 0.95) - 1]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('json_file')
    args = parser.parse_args()
    count, p95 = summarize(json.loads(Path(args.json_file).read_text(encoding='utf-8')))
    print(f'Cámara → actualización del carrito: n={count}, p95={p95:.1f} ms')
    print('Incluye inferencia y red; excluye el buffer físico anterior a la entrega del frame al worker.')
    raise SystemExit(0 if count >= 30 and p95 < 1500 else 1)
