import { useEffect, useState, useRef } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { supabase } from './supabaseClient';
import './App.css';

const API_URL = 'http://localhost:8000/api/v1';

function App() {
  const [inventario, setInventario] = useState([]);
  const [ventas, setVentas] = useState([]);
  const [ultimoCambio, setUltimoCambio] = useState(null);
  const [nombresProductos, setNombresProductos] = useState({});
  const [rango, setRango] = useState('hoy'); // 'hoy' | '7dias' | 'todo'

  const timeoutRef = useRef(null);

  useEffect(() => {
    cargarInventarioBajoStock();
    cargarVentasCompletadas();
  }, []);

  async function cargarInventarioBajoStock() {
    try {
      const res = await fetch(`${API_URL}/inventario?solo_bajo_stock=true`);
      const data = await res.json();
      setInventario(data);
      // Resolvemos el nombre real de cada producto que no tengamos en caché
      data.forEach((item) => resolverNombreProducto(item.producto_id));
    } catch (err) {
      console.error('Error cargando inventario:', err);
    }
  }

  async function cargarVentasCompletadas() {
    try {
      const res = await fetch(`${API_URL}/ventas?estado=completada`);
      const data = await res.json();
      setVentas(data);
    } catch (err) {
      console.error('Error cargando ventas:', err);
    }
  }

  // --- Mejora 1: nombres reales en vez de UUIDs ---
  async function resolverNombreProducto(id) {
    if (!id || nombresProductos[id]) return;
    try {
      const res = await fetch(`${API_URL}/productos/${id}`);
      if (!res.ok) return;
      const data = await res.json();
      setNombresProductos((prev) => ({ ...prev, [id]: data.nombre }));
    } catch (err) {
      console.error('Error resolviendo nombre de producto:', err);
    }
  }

  useEffect(() => {
    const canal = supabase
      .channel('inventario-en-vivo')
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'inventario' },
        (payload) => {
          setUltimoCambio(payload.new);
          resolverNombreProducto(payload.new.producto_id);
          cargarInventarioBajoStock();

          // --- Mejora 4: la notificación puntual se autooculta a los 5s ---
          if (timeoutRef.current) clearTimeout(timeoutRef.current);
          timeoutRef.current = setTimeout(() => setUltimoCambio(null), 5000);
        }
      )
      .subscribe();

    const canalVentas = supabase
      .channel('ventas-en-vivo')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'ventas' },
        () => {
          cargarVentasCompletadas();
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(canal);
      supabase.removeChannel(canalVentas);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  // --- Mejora 3: filtro por rango de fechas (calculado en el navegador) ---
  function dentroDelRango(fechaISO) {
    const fecha = new Date(fechaISO);
    const ahora = new Date();
    if (rango === 'todo') return true;
    if (rango === 'hoy') {
      return fecha.toDateString() === ahora.toDateString();
    }
    if (rango === '7dias') {
      const haceSieteDias = new Date(ahora);
      haceSieteDias.setDate(ahora.getDate() - 7);
      return fecha >= haceSieteDias;
    }
    return true;
  }

  const ventasFiltradas = ventas.filter((v) => dentroDelRango(v.created_at));

  const totalDelDia = ventasFiltradas.reduce((acc, v) => acc + Number(v.total), 0);
  const ticketPromedio = ventasFiltradas.length > 0 ? totalDelDia / ventasFiltradas.length : 0;
  const agotados = inventario.filter((item) => item.stock_actual === 0);

  // --- Mejora 2: gráfica agrupada por hora, en línea (tendencia del día) ---
  const ventasPorHora = {};
  ventasFiltradas.forEach((v) => {
    const hora = new Date(v.created_at).toLocaleTimeString('es-MX', {
      hour: '2-digit',
      minute: '2-digit',
    });
    ventasPorHora[hora] = (ventasPorHora[hora] || 0) + Number(v.total);
  });
  const datosGrafica = Object.entries(ventasPorHora)
    .map(([hora, total]) => ({ hora, total }))
    .sort((a, b) => (a.hora > b.hora ? 1 : -1));

  const nombreUltimoCambio = ultimoCambio
    ? nombresProductos[ultimoCambio.producto_id] ?? ultimoCambio.producto_id?.slice(0, 8)
    : null;

  return (
    <div className="board">
      <div className="board-header">
        <h1>Tienda — Centro de Operaciones</h1>
        <div className="board-status">
          <span className="dot-live"></span>
          EN VIVO
        </div>
      </div>

      {agotados.length > 0 && (
        <div className="alert-agotado">
          <span className="alert-icon">⛔</span>
          {agotados.length === 1
            ? `${nombresProductos[agotados[0].producto_id] ?? '1 producto'} agotado — reabastecer de inmediato`
            : `${agotados.length} productos agotados — reabastecer de inmediato`}
        </div>
      )}

      {ultimoCambio && (
        <div className="ticker">
          <span className="ticker-label">Stock actualizado</span>
          {nombreUltimoCambio} → nuevo stock: {ultimoCambio.stock_actual}
        </div>
      )}

      {/* --- Filtro de rango --- */}
      <div className="filtro-rango">
        <button className={rango === 'hoy' ? 'activo' : ''} onClick={() => setRango('hoy')}>
          Hoy
        </button>
        <button className={rango === '7dias' ? 'activo' : ''} onClick={() => setRango('7dias')}>
          Últimos 7 días
        </button>
        <button className={rango === 'todo' ? 'activo' : ''} onClick={() => setRango('todo')}>
          Todo
        </button>
      </div>

      <div className="stats">
        <div className="stat">
          <span className="stat-label">Total ({rango})</span>
          <span className="stat-value">${totalDelDia.toFixed(2)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Ticket promedio</span>
          <span className="stat-value">${ticketPromedio.toFixed(2)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Ventas cerradas</span>
          <span className="stat-value">{ventasFiltradas.length}</span>
        </div>
      </div>

      {datosGrafica.length > 0 && (
        <div className="chart-panel">
          <h2>Tendencia de ventas por hora</h2>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={datosGrafica}>
              <XAxis
                dataKey="hora"
                tick={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, fill: '#6B7280' }}
                axisLine={{ stroke: '#DEDAD0' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, fill: '#6B7280' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, border: '1px solid #1A2333' }}
              />
              <Line type="monotone" dataKey="total" stroke="#0E7C6B" strokeWidth={2.5} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="panels">
        <div className="panel">
          <h2>⚠ Bajo stock</h2>
          {inventario.length === 0 ? (
            <p className="panel-empty">Todo el inventario está en niveles normales.</p>
          ) : (
            inventario.map((item) => (
              <div className="row" key={item.id}>
                <span className="row-name">
                  {nombresProductos[item.producto_id] ?? item.producto_id}
                </span>
                <span className={`stock-badge ${item.stock_actual === 0 ? 'critico' : 'bajo'}`}>
                  {item.stock_actual === 0 ? 'AGOTADO' : `${item.stock_actual} u.`}
                </span>
              </div>
            ))
          )}
        </div>

        <div className="panel">
          <h2>Ventas completadas</h2>
          {ventasFiltradas.length === 0 ? (
            <p className="panel-empty">Sin ventas en este rango.</p>
          ) : (
            ventasFiltradas.map((venta) => (
              <div className="row" key={venta.id}>
                <span className="row-name">{venta.folio}</span>
                <span className="sale-total">${venta.total}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default App;