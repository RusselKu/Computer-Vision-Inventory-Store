"""Run only against a dedicated test environment: creates and cancels carts."""
import os
from locust import HttpUser, between, task


class POSUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        self.sale_id = None

    @task(3)
    def catalog(self):
        barcode = os.getenv('LOAD_BARCODE', '7501055312107')
        self.client.get(f'/api/v1/productos/codigo/{barcode}', name='/productos/codigo/[barcode]')

    @task
    def cart(self):
        if self.sale_id:
            self.cancel()
            if self.sale_id:
                return
        response = self.client.post('/api/v1/ventas', name='/ventas crear')
        if response.status_code != 201:
            return
        self.sale_id = response.json()['id']
        try:
            self.client.post(f'/api/v1/ventas/{self.sale_id}/items',
                             json={'codigo_barras': os.getenv('LOAD_BARCODE', '7501055312107'),
                                   'cantidad': 1, 'metodo_deteccion': 'manual'},
                             name='/ventas/[id]/items')
        finally:
            self.cancel()

    def cancel(self):
        if self.sale_id:
            response = self.client.post(f'/api/v1/ventas/{self.sale_id}/cancelar',
                                        name='/ventas/[id]/cancelar')
            if response.status_code == 200:
                self.sale_id = None

    def on_stop(self):
        self.cancel()
