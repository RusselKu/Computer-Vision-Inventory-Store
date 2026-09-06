import React, { useState, useEffect, useRef } from 'react';
import { 
  ShoppingCart, 
  Trash2, 
  Plus, 
  Minus, 
  CreditCard, 
  Banknote, 
  AlertTriangle, 
  CheckCircle2, 
  Camera, 
  Printer, 
  Barcode,
  Search
} from 'lucide-react';
import './index.css';

const API_BASE = 'http://localhost:8000/api/v1';
const WS_BASE = 'ws://localhost:8000/api/v1/ws/pos';

export default function App() {
  const [venta, setVenta] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [metodoPago, setMetodoPago] = useState('efectivo');
  const [codigoManual, setCodigoManual] = useState('');
  const [alertaFallback, setAlertaFallback] = useState(null);
  const [ticketModal, setTicketModal] = useState(null);
  const [cargando, setCargando] = useState(false);

  const wsRef = useRef(null);

  // Iniciar venta al cargar la aplicación
  useEffect(() => {
    iniciarNuevaVenta();
  }, []);

  // Manejar conexión de WebSocket cuando existe una venta activa
  useEffect(() => {
    if (!venta?.id) return;

    const wsUrl = `${WS_BASE}/${venta.id}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('✓ WebSocket POS conectado:', wsUrl);
      setWsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        console.log('⚡ Evento WebSocket recibido:', payload);

        if (payload.type === 'ITEM_AGREGADO_CV') {
          // Reproducir beep de escaneo exitoso
          reproducirSonido('beep');
          recargarVenta(venta.id);
        } else if (payload.type === 'ALERTA_CV_FALLBACK') {
          // Reproducir aviso de alerta
          reproducirSonido('alerta');
          setAlertaFallback(payload.mensaje || 'Producto no reconocido tras 5 frames.');
        }
      } catch (err) {
        console.error('Error procesando evento WebSocket:', err);
      }
    };

    ws.onclose = () => {
      console.log('✗ WebSocket desconectado.');
      setWsConnected(false);
    };

    return () => {
      ws.close();
    };
  }, [venta?.id]);

  function reproducirSonido(tipo) {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);

      if (tipo === 'beep') {
        osc.frequency.value = 1046.5; // Nota C6 (Beep de escáner)
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        osc.start();
        osc.stop(ctx.currentTime + 0.12);
      } else if (tipo === 'alerta') {
        osc.frequency.value = 440; // Nota A4 (Alerta)
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        osc.start();
        osc.stop(ctx.currentTime + 0.25);
      }
    } catch (e) {
      // Ignorar restricciones de audio del navegador
    }
  }

  async function iniciarNuevaVenta() {
    setCargando(true);
    try {
      // 1. Verificar si ya existe una venta abierta activa en la API
      const resExistente = await fetch(`${API_BASE}/ventas?estado=abierta&limit=1`);
      if (resExistente.ok) {
        const abiertas = await resExistente.json();
        if (abiertas && abiertas.length > 0) {
          await recargarVenta(abiertas[0].id);
          setCargando(false);
          return;
        }
      }

      // 2. Si no hay venta abierta, crear una nueva
      const res = await fetch(`${API_BASE}/ventas`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setVenta(data);
      } else {
        console.error('Error iniciando venta');
      }
    } catch (err) {
      console.error('Error de red iniciando venta:', err);
    } finally {
      setCargando(false);
    }
  }

  async function recargarVenta(ventaId) {
    try {
      const res = await fetch(`${API_BASE}/ventas/${ventaId}`);
      if (res.ok) {
        const data = await res.json();
        setVenta(data);
      }
    } catch (err) {
      console.error('Error recargando venta:', err);
    }
  }

  async function agregarItemManual(e) {
    e?.preventDefault();
    if (!codigoManual.trim() || !venta?.id) return;

    try {
      const res = await fetch(`${API_BASE}/ventas/${venta.id}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          codigo_barras: codigoManual.trim(),
          cantidad: 1,
          metodo_deteccion: 'manual'
        })
      });

      if (res.ok) {
        const data = await res.json();
        setVenta(data);
        setCodigoManual('');
        setAlertaFallback(null); // Cerrar modal de fallback si estaba abierto
        reproducirSonido('beep');
      } else {
        const errData = await res.json();
        alert(`Error: ${errData.detail || 'Producto no encontrado'}`);
      }
    } catch (err) {
      alert('Error agregando producto');
    }
  }

  async function cambiarCantidad(itemId, nuevaCantidad) {
    if (nuevaCantidad <= 0) return eliminarItem(itemId);
    try {
      const res = await fetch(`${API_BASE}/ventas/${venta.id}/items/${itemId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cantidad: nuevaCantidad })
      });
      if (res.ok) {
        const data = await res.json();
        setVenta(data);
      }
    } catch (err) {
      console.error('Error actualizando cantidad:', err);
    }
  }

  async function eliminarItem(itemId) {
    try {
      const res = await fetch(`${API_BASE}/ventas/${venta.id}/items/${itemId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        const data = await res.json();
        setVenta(data);
      }
    } catch (err) {
      console.error('Error eliminando item:', err);
    }
  }

  async function procesarCobro() {
    if (!venta?.items?.length) return;
    setCargando(true);
    try {
      const res = await fetch(`${API_BASE}/ventas/${venta.id}/cerrar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ metodo_pago: metodoPago })
      });

      if (res.ok) {
        const resultado = await res.json();
        // Mostrar Ticket Modal
        setTicketModal({
          folio: resultado.folio,
          total: resultado.total,
          metodo_pago: resultado.metodo_pago,
          items: venta.items,
          fecha: new Date().toLocaleString('es-MX')
        });
      } else {
        const err = await res.json();
        alert(`Error al cobrar: ${err.detail}`);
      }
    } catch (err) {
      alert('Error de red procesando cobro');
    } finally {
      setCargando(false);
    }
  }

  function finalizarYReiniciar() {
    setTicketModal(null);
    iniciarNuevaVenta();
  }

  return (
    <div className="pos-app">
      {/* Header Bar */}
      <header className="pos-header">
        <div className="brand-title">
          <div className="brand-icon">
            <Camera size={22} />
          </div>
          <div className="brand-text">
            <h1>POS Visión Computacional</h1>
            <p>Terminal de Cajero — Dev C</p>
          </div>
        </div>

        <div className="header-actions">
          {venta?.folio && (
            <div className="folio-badge">
              FOLIO: {venta.folio}
            </div>
          )}

          <div className={`status-pill ${wsConnected ? '' : 'disconnected'}`}>
            <span className="pulse-dot"></span>
            {wsConnected ? 'CAMARA EN VIVO (WS)' : 'DESCONECTADO'}
          </div>
        </div>
      </header>

      {/* Body Content */}
      <main className="pos-body">
        {/* Left Column: Cart & Manual Entry */}
        <section className="cart-section">
          {/* Manual Input Bar */}
          <form className="scan-bar" onSubmit={agregarItemManual}>
            <Barcode size={22} className="scan-icon" style={{ color: '#94a3b8' }} />
            <input
              type="text"
              className="scan-input"
              placeholder="Escanee o ingrese código de barras manualmente (ej. 7501055312107)..."
              value={codigoManual}
              onChange={(e) => setCodigoManual(e.target.value)}
              autoFocus
            />
            <button type="submit" className="scan-btn">
              Agregar
            </button>
          </form>

          {/* Cart Items Table */}
          <div className="table-container">
            {venta?.items?.length > 0 ? (
              <table className="cart-table">
                <thead>
                  <tr>
                    <th>Producto</th>
                    <th>Detección</th>
                    <th>Cant.</th>
                    <th>Precio</th>
                    <th>Subtotal</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {venta.items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.producto?.nombre || 'Producto'}</strong>
                        <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                          EAN: {item.producto?.codigo_barras}
                        </div>
                      </td>
                      <td>
                        <span className={`item-origin-tag ${item.metodo_deteccion}`}>
                          {item.metodo_deteccion === 'cv_yolo' && '📸 IA Vision'}
                          {item.metodo_deteccion === 'cv_barcode' && '🔍 Escáner'}
                          {item.metodo_deteccion === 'manual' && '⌨️ Manual'}
                        </span>
                      </td>
                      <td>
                        <div className="qty-controls">
                          <button 
                            className="qty-btn" 
                            onClick={() => cambiarCantidad(item.id, item.cantidad - 1)}
                          >
                            <Minus size={14} />
                          </button>
                          <span className="qty-val">{item.cantidad}</span>
                          <button 
                            className="qty-btn" 
                            onClick={() => cambiarCantidad(item.id, item.cantidad + 1)}
                          >
                            <Plus size={14} />
                          </button>
                        </div>
                      </td>
                      <td className="price-col">${Number(item.precio_unitario).toFixed(2)}</td>
                      <td className="price-col" style={{ color: '#10b981' }}>
                        ${Number(item.subtotal).toFixed(2)}
                      </td>
                      <td>
                        <button 
                          className="delete-btn" 
                          onClick={() => eliminarItem(item.id)}
                          title="Eliminar producto"
                        >
                          <Trash2 size={18} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-cart">
                <ShoppingCart size={48} className="empty-icon" />
                <h3>Carrito Vacío</h3>
                <p>Muestre un producto a la cámara o ingrese el código arriba.</p>
              </div>
            )}
          </div>
        </section>

        {/* Right Column: Totals & Checkout */}
        <section className="checkout-panel">
          <div className="totals-breakdown">
            <h2 className="totals-title">Resumen de Cuenta</h2>

            <div className="total-row">
              <span>Subtotal:</span>
              <span>${Number(venta?.subtotal || 0).toFixed(2)}</span>
            </div>

            <div className="total-row">
              <span>Impuestos (IVA 0%):</span>
              <span>$0.00</span>
            </div>

            <div className="total-row grand-total">
              <span>TOTAL:</span>
              <span className="amount">${Number(venta?.total || 0).toFixed(2)}</span>
            </div>

            {/* Payment Method Selector */}
            <div className="pay-methods">
              <span className="pay-methods-title">Método de Pago</span>
              <div className="pay-grid">
                <button
                  className={`pay-card ${metodoPago === 'efectivo' ? 'active' : ''}`}
                  onClick={() => setMetodoPago('efectivo')}
                >
                  <Banknote size={24} />
                  Efectivo
                </button>
                <button
                  className={`pay-card ${metodoPago === 'tarjeta' ? 'active' : ''}`}
                  onClick={() => setMetodoPago('tarjeta')}
                >
                  <CreditCard size={24} />
                  Tarjeta
                </button>
              </div>
            </div>
          </div>

          <button
            className="checkout-action-btn"
            disabled={!venta?.items?.length || cargando}
            onClick={procesarCobro}
          >
            <CheckCircle2 size={24} />
            {cargando ? 'Procesando...' : 'Cobrar Venta'}
          </button>
        </section>
      </main>

      {/* Modal 1: Alerta Fallback (5 frames sin código) */}
      {alertaFallback && (
        <div className="modal-overlay">
          <div className="fallback-modal">
            <div className="fallback-icon">
              <AlertTriangle size={36} />
            </div>
            <h2>Atención Cajero</h2>
            <p>{alertaFallback}</p>

            <form onSubmit={agregarItemManual}>
              <input
                type="text"
                className="scan-input"
                style={{
                  background: 'rgba(15,23,42,0.8)',
                  border: '1px solid #f97316',
                  padding: '12px',
                  borderRadius: '8px',
                  width: '100%',
                  textAlign: 'center',
                  marginBottom: '16px'
                }}
                placeholder="Ingrese código de barras manualmente..."
                value={codigoManual}
                onChange={(e) => setCodigoManual(e.target.value)}
                autoFocus
              />
              <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
                <button type="submit" className="scan-btn" style={{ flex: 1, padding: '12px' }}>
                  Confirmar e Ingresar
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setAlertaFallback(null);
                    setCodigoManual('');
                  }}
                  style={{
                    flex: 1,
                    padding: '12px',
                    background: 'rgba(239, 68, 68, 0.15)',
                    border: '1px solid #ef4444',
                    color: '#f87171',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontWeight: '600',
                    transition: 'all 0.2s ease'
                  }}
                >
                  Cancelar / Regresar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal 2: Ticket de Cobro Exitoso */}
      {ticketModal && (
        <div className="modal-overlay">
          <div className="ticket-modal">
            <div className="ticket-header">
              <h3>TIENDA POS VIRTUAL</h3>
              <p>Comprobante de Pago</p>
              <div style={{ fontSize: '0.75rem', marginTop: '6px' }}>
                Folio: {ticketModal.folio}
              </div>
              <div style={{ fontSize: '0.75rem' }}>
                Fecha: {ticketModal.fecha}
              </div>
            </div>

            <div className="ticket-items">
              {ticketModal.items.map((it) => (
                <div key={it.id} className="ticket-item-row">
                  <span>{it.cantidad}x {it.producto?.nombre?.slice(0, 20)}</span>
                  <span>${Number(it.subtotal).toFixed(2)}</span>
                </div>
              ))}
            </div>

            <div className="ticket-footer">
              <div className="ticket-item-row" style={{ fontWeight: 'bold', fontSize: '1rem', color: '#111827' }}>
                <span>TOTAL PAGADO:</span>
                <span>${Number(ticketModal.total).toFixed(2)}</span>
              </div>
              <p style={{ marginTop: '8px' }}>Método: {ticketModal.metodo_pago?.toUpperCase()}</p>
              <p style={{ marginTop: '12px' }}>¡Gracias por su compra!</p>

              <button className="close-ticket-btn" onClick={finalizarYReiniciar}>
                Siguiente Venta
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
