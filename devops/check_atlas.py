"""Verify MongoDB (local or Atlas); --initialize creates collections/indexes."""
import argparse
import os
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv
from pymongo import MongoClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--initialize', action='store_true')
    parser.add_argument('--write-probe', action='store_true')
    args = parser.parse_args()
    load_dotenv()
    uri = os.getenv('MONGODB_URI')
    if not uri:
        parser.error('Configura MONGODB_URI en .env; no pases credenciales por argumentos.')
    with MongoClient(uri, serverSelectionTimeoutMS=5000, socketTimeoutMS=5000) as client:
        client.admin.command('ping')
        db = client[os.getenv('MONGODB_DB_NAME', 'pos_telemetria')]
        existing = set(db.list_collection_names())
        for name in ['logs_sistema', 'eventos_vision']:
            if args.initialize:
                if name not in existing:
                    db.create_collection(name)
                db[name].create_index('timestamp')
                if name == 'eventos_vision':
                    db[name].create_index('venta_id')
            elif name not in existing:
                raise RuntimeError(f'Falta la colección {name}; ejecuta --initialize.')
            db[name].find_one({}, {'_id': 1})
            if args.write_probe:
                probe_id = 'dev-e-probe-' + str(uuid4())
                try:
                    db[name].insert_one({'_id': probe_id, 'timestamp': datetime.now(timezone.utc).isoformat(),
                                         'tipo': 'verificacion_dev_e'})
                    assert db[name].find_one({'_id': probe_id})
                finally:
                    db[name].delete_one({'_id': probe_id})
            print(f'{name}: OK')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Avoid printing a connection URI or credentials in diagnostic logs.
        raise SystemExit(f'Verificación fallida ({type(error).__name__}). Revisa que MongoDB esté disponible y la configuración de acceso.')
