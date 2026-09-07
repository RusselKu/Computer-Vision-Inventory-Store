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
import './PosView.css';

const API_BASE = 'http://localhost:8000/api/v1';
const WS_BASE = 'ws://localhost:8000/api/v1/ws/pos';

export default function PosView() {
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
          reproducirSonido('beep');
          recargarVenta(venta.id);
        } else if (payload.type === 'ALERTA_CV_FALLBACK') {
          reproducirSonido('alerta');
          setAlertaFallback(payload.data);
        }
      } catch (e) {
        console.error('Error parseando mensaje WebSocket:', e);
      }
    };

    ws.onclose = () => {
      console.log('✗ WebSocket POS desconectado');
      setWsConnected(false);
    };

    ws.onerror = (err) => {
      console.error('Error en WebSocket POS:', err);
    };

    return () => {
      ws.close();
    };
  }, [venta?.id]);

  const reproducirSonido = (tipo) => {
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();

      osc.connect(gain);
      gain.connect(audioCtx.destination);

      if (tipo === 'beep') {
        osc.frequency.value = 880; // A5
        gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.15);
      } else if (tipo === 'alerta') {
        osc.frequency.value = 330; // E4
        gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.3);
      }
    } catch (e) {
      console.log('Audio Context no permitido sin interacción previa');
    }
  };

  const iniciarNuevaVenta = async () => {
    setCargando(true);
    try {
      const res = await fetch(`${API_BASE}/ventas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      if (res.ok) {
        const data = await res.json();
        setVenta(data);
      } else {
        console.error('Error al iniciar nueva venta');
      }
    } catch (err) {
      console.error('Error de red al iniciar venta:', err);
    } finally {
      setCargando(false);
    }
  };

  const recargarVenta = async (ventaId) => {
    try {
      const res = await fetch(`${API_BASE}/ventas/${ventaId}`);
      if (res.ok) {
        const data = await res.json();
        setVenta(data);
      }
    } catch (err) {
      console.error('Error al recargar venta:', err);
    }
  };

  const agregarProductoManual = async (e) => {
    e.preventDefault();
    if (!codigoManual.trim() || !venta?.id) return;

    setCargando(true);
    try {
      const res = await fetch(`${API_BASE}/ventas/${venta.id}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          codigo: codigoManual,
          cantidad: 1
        })
      });

      if (res.ok) {
        setCodigoManual('');
        reproducirSonido('beep');
        recargarVenta(venta.id);
        if (alertaFallback) setAlertaFallback(null);
      } else {
        const errData = await res.json();
        alert(`Error: ${errData.detail || 'No se encontró el producto'}`);
      }
    } catch (err) {
      console.error('Error al agregar producto manualmente:', err);
    } finally {
      setCargando(false);
    }
  };

  const cambiarCantidad = async (itemId, nuevaCantidad) => {
    if (nuevaCantidad <= 0) {
      eliminarItem(itemId);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/ventas/${venta.id}/items/${itemId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cantidad: nuevaCantidad })
      });
      if (res.ok) {
        recargarVenta(venta.id);
      }
    } catch (err) {
      console.error('Error al actualizar cantidad:', err);
    }
  };

  const eliminarItem = async (itemId) => {
    try {
      const res = await fetch(`${API_BASE}/ventas/${venta.id}/items/${itemId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        recargarVenta(venta.id);
      }
    } catch (err) {
      console.error('Error al eliminar item:', err);
    }
  };

  const completarCobro = async () => {
    if (!venta?.id || !venta?.items || venta.items.length === 0) return;

    setCargando(true);
    try {
      const res = await fetch(`${API_BASE}/ventas/${venta.id}/checkout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ metodo_pago: metodoPago })
      });

      if (res.ok) {
        const data = await res.json();
        setTicketModal(data);
      } else {
        const errData = await res.json();
        alert(`Error en checkout: ${errData.detail || 'Falló la transacción'}`);
      }
    } catch (err) {
      console.error('Error al realizar checkout:', err);
    } finally {
      setCargando(false);
    }
  };

  const cerrarTicketEIniciarNueva = () => {
    setTicketModal(null);
    setAlertaFallback(null);
    iniciarNuevaVenta();
  };

  return (
    <div className="pos-app-container">
      {/* HEADER DE ESTADO POS */}
      <header className="pos-header">
        <div className="pos-header-brand">
          <div className="pos-header-icon">🛒</div>
          <div>
            <h1 className="pos-title">Punto de Venta POS</h1>
            <p className="pos-subtitle">
              {venta?.folio ? `Folio: ${venta.folio}` : 'Cargando venta...'}
            </p>
          </div>
        </div>

        <div className="pos-header-actions">
          <div className={`ws-status-pill ${wsConnected ? 'connected' : 'disconnected'}`}>
            <Camera className="w-4 h-4" />
            <span>{wsConnected ? 'CV Activo (Cámara Conectada)' : 'CV Desconectado'}</span>
            <span className="pulse-dot"></span>
          </div>

          <button 
            className="btn-secundario"
            onClick={iniciarNuevaVenta}
            disabled={cargando}
          >
            Nueva Venta
          </button>
        </div>
      </header>

      {/* CONTENIDO PRINCIPAL */}
      <main className="pos-main">
        {/* PANEL IZQUIERDO: DETALLE DE VENTA Y CARRITO */}
        <section className="pos-cart-section">
          <div className="pos-cart-header">
            <h2>Artículos en la Orden</h2>
            <span className="item-count-badge">
              {venta?.items?.reduce((acc, i) => acc + i.cantidad, 0) || 0} ítems
            </span>
          </div>

          <div className="pos-cart-items-container">
            {!venta?.items || venta.items.length === 0 ? (
              <div className="pos-empty-cart">
                <ShoppingCart className="w-16 h-16 text-slate-500 mb-2" />
                <p className="text-lg font-medium text-slate-300">El carrito está vacío</p>
                <p className="text-sm text-slate-400">Pasa los productos frente a la cámara o ingresa el código manual</p>
              </div>
            ) : (
              <table className="pos-table">
                <thead>
                  <tr>
                    <th>Producto</th>
                    <th>Precio</th>
                    <th>Cant.</th>
                    <th>Subtotal</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {venta.items.map((item) => (
                    <tr key={item.id}>
                      <td className="col-producto">
                        <div className="product-info-cell">
                          {item.producto?.imagen_url ? (
                            <img 
                              src={item.producto.imagen_url} 
                              alt={item.producto.nombre} 
                              className="product-thumb"
                            />
                          ) : (
                            <div className="product-thumb-placeholder">📦</div>
                          )}
                          <div>
                            <p className="font-semibold text-slate-100">{item.producto?.nombre || 'Producto'}</p>
                            <span className="font-mono text-xs text-slate-400">{item.producto?.codigo_barras}</span>
                          </div>
                        </div>
                      </td>
                      <td className="font-mono">${Number(item.precio_unitario).toFixed(2)}</td>
                      <td>
                        <div className="qty-controls">
                          <button 
                            className="btn-qty" 
                            onClick={() => cambiarCantidad(item.id, item.cantidad - 1)}
                          >
                            <Minus className="w-3 h-3" />
                          </button>
                          <span className="qty-value">{item.cantidad}</span>
                          <button 
                            className="btn-qty" 
                            onClick={() => cambiarCantidad(item.id, item.cantidad + 1)}
                          >
                            <Plus className="w-3 h-3" />
                          </button>
                        </div>
                      </td>
                      <td className="font-mono font-bold text-emerald-400">
                        ${Number(item.subtotal).toFixed(2)}
                      </td>
                      <td>
                        <button 
                          className="btn-delete"
                          onClick={() => eliminarItem(item.id)}
                          title="Eliminar producto"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        {/* PANEL DERECHO: BUSQUEDA MANUAL Y RESUMEN DE COBRO */}
        <section className="pos-checkout-section">
          {/* BUSQUEDA MANUAL POR CODIGO */}
          <div className="pos-card pos-manual-card">
            <h3><Barcode className="w-5 h-5 inline mr-1 text-cyan-400" /> Búsqueda Manual</h3>
            <form onSubmit={agregarProductoManual} className="pos-search-form">
              <div className="input-group">
                <input 
                  type="text" 
                  placeholder="Código de barras / SKU..."
                  value={codigoManual}
                  onChange={(e) => setCodigoManual(e.target.value)}
                  className="pos-input"
                />
                <button type="submit" className="btn-primario" disabled={cargando}>
                  <Search className="w-4 h-4" />
                  <span>Agregar</span>
                </button>
              </div>
            </form>
          </div>

          {/* RESUMEN DE PAGO */}
          <div className="pos-card pos-summary-card">
            <h3>Resumen de Pago</h3>

            <div className="summary-details">
              <div className="summary-row">
                <span>Subtotal:</span>
                <span className="font-mono">${Number(venta?.total || 0).toFixed(2)}</span>
              </div>
              <div className="summary-row">
                <span>IVA (0%):</span>
                <span className="font-mono">$0.00</span>
              </div>
              <div className="summary-divider"></div>
              <div className="summary-row total-row">
                <span>Total a Cobrar:</span>
                <span className="font-mono total-amount">${Number(venta?.total || 0).toFixed(2)}</span>
              </div>
            </div>

            {/* SELECCION DE METODO DE PAGO */}
            <div className="payment-methods">
              <p className="payment-label">Método de Pago:</p>
              <div className="payment-options">
                <button 
                  type="button"
                  className={`btn-payment ${metodoPago === 'efectivo' ? 'active' : ''}`}
                  onClick={() => setMetodoPago('efectivo')}
                >
                  <Banknote className="w-5 h-5" />
                  <span>Efectivo</span>
                </button>
                <button 
                  type="button"
                  className={`btn-payment ${metodoPago === 'tarjeta' ? 'active' : ''}`}
                  onClick={() => setMetodoPago('tarjeta')}
                >
                  <CreditCard className="w-5 h-5" />
                  <span>Tarjeta</span>
                </button>
              </div>
            </div>

            {/* BOTON DE COBRAR */}
            <button 
              className="btn-checkout"
              disabled={!venta?.items || venta.items.length === 0 || cargando}
              onClick={completarCobro}
            >
              <CheckCircle2 className="w-6 h-6 mr-2" />
              <span>COBRAR (${Number(venta?.total || 0).toFixed(2)})</span>
            </button>
          </div>
        </section>
      </main>

      {/* MODAL ALERTA FALLBACK DE VISION POR COMPUTADORA */}
      {alertaFallback && (
        <div className="pos-modal-overlay">
          <div className="pos-modal pos-modal-alert">
            <div className="modal-alert-icon">
              <AlertTriangle className="w-12 h-12 text-amber-400" />
            </div>
            <h2>Intervención de Cajero Requerida</h2>
            <p className="modal-alert-msg">{alertaFallback.mensaje}</p>
            <div className="modal-alert-details">
              <span>Baja confianza en detección de visión por computadora.</span>
            </div>

            <div className="modal-alert-actions">
              <button 
                className="btn-secundario"
                onClick={() => setAlertaFallback(null)}
              >
                Cancelar / Regresar
              </button>
              <form onSubmit={agregarProductoManual} className="modal-alert-form">
                <input 
                  type="text"
                  placeholder="Escanea el código de barras..."
                  value={codigoManual}
                  onChange={(e) => setCodigoManual(e.target.value)}
                  className="pos-input"
                  autoFocus
                />
                <button type="submit" className="btn-primario">
                  Confirmar Manualmente
                </button>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* MODAL DE TICKET / TRANSACCION EXITOSA */}
      {ticketModal && (
        <div className="pos-modal-overlay">
          <div className="pos-modal pos-modal-ticket">
            <div className="ticket-header">
              <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-2" />
              <h2>¡Venta Completada!</h2>
              <p className="text-sm text-slate-400">Folio: {ticketModal.venta?.folio}</p>
            </div>

            <div className="ticket-body">
              <div className="ticket-row">
                <span>Fecha:</span>
                <span>{new Date(ticketModal.venta?.created_at || Date.now()).toLocaleString()}</span>
              </div>
              <div className="ticket-row">
                <span>Método de Pago:</span>
                <span className="uppercase font-semibold">{ticketModal.venta?.metodo_pago}</span>
              </div>
              <div className="ticket-divider"></div>

              <div className="ticket-items">
                {ticketModal.venta?.items?.map((item) => (
                  <div key={item.id} className="ticket-item-row">
                    <span>{item.cantidad}x {item.producto?.nombre}</span>
                    <span className="font-mono">${Number(item.subtotal).toFixed(2)}</span>
                  </div>
                ))}
              </div>

              <div className="ticket-divider"></div>
              <div className="ticket-row ticket-total">
                <span>TOTAL:</span>
                <span className="font-mono text-emerald-400">${Number(ticketModal.venta?.total).toFixed(2)}</span>
              </div>
            </div>

            <div className="ticket-footer">
              <button 
                className="btn-secundario"
                onClick={() => window.print()}
              >
                <Printer className="w-4 h-4 mr-1" /> Imprimir
              </button>
              <button 
                className="btn-primario"
                onClick={cerrarTicketEIniciarNueva}
              >
                Siguiente Venta
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
