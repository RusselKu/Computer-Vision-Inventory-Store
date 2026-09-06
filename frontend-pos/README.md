# Frontend POS — Terminal de Cajero (Dev C)

Aplicación web moderna en **React + Vite** para la pantalla táctil/interfaz del cajero.

---

## 🛠️ Funcionalidades Implementadas

1. **Conexión WebSocket en Tiempo Real (`ws://localhost:8000/api/v1/ws/pos/{venta_id}`):**
   - Transmisión en vivo de detecciones de la cámara/worker de visión (Dev B).
   - Inyección automática de productos al carrito con sonido beep de confirmación.

2. **Alertas de Fallback (5 Frames):**
   - Modal emergente con aviso sonoro y visual cuando la cámara solicita la captura manual de un producto no identificado.

3. **Gestión Completa de Carrito:**
   - Control de cantidades (+ / -), eliminación de items e ingreso manual por código de barras.

4. **Cobro y Generación de Ticket:**
   - Selección de método de pago (Efectivo / Tarjeta).
   - Cierre atómico de la transacción en Supabase con descuento de stock e impresión de Ticket con Folio único.

---

## 🚀 Cómo Ejecutar el Frontend POS

```bash
cd frontend-pos
npm install
npm run dev
```

La aplicación se abrirá en `http://localhost:3000`.
