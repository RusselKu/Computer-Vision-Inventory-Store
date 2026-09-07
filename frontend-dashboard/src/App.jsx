import { useEffect, useState, useRef } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, BarChart, Bar,
} from 'recharts';
import { supabase } from './supabaseClient';
import './App.css';

const API_URL = 'http://localhost:8000/api/v1';

function App() {
  const [inventario, setInventario] = useState([]); // solo bajo stock (para el panel de lista)
  const [inventarioCompleto, setInventarioCompleto] = useState([]); // todo, para la dona
  const [ventas, setVentas] = useState([]);
  const [ultimoCambio, setUltimoCambio] = useState(null);
  const [productosInfo, setProductosInfo] = useState({});
  const [rango, setRango] = useState('hoy');
  const [itemsPorVenta, setItemsPorVenta] = useState({}); // { [ventaId]: items[] }

  const timeoutRef = useRef(null);

  useEffect(() => {
    cargarInventarioBajoStock();
    cargarInventarioCompleto();
    cargarVentasCompletadas();
  }, []);

  async function cargarInventarioBajoStock() {
    try {
      const res = await fetch(`${API_URL}/inventario?solo_bajo_stock=true`);
      const data = await res.json();
      setInventario(data);
      data.forEach((item) => resolverProducto(item.producto_id));
    } catch (err) {
      console.error('Error cargando inventario bajo stock:', err);
    }
  }

  async function cargarInventarioCompleto() {
    try {
      const res = await fetch(`${API_URL}/inventario?limit=200`);
      const data = await res.json();
      setInventarioCompleto(data);
    } catch (err) {
      console.error('Error cargando inventario completo:', err);
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

  async function resolverProducto(id) {
    if (!id || productosInfo[id]) return;
    try {
      const res = await fetch(`${API_URL}/productos/${id}`);
      if (!res.ok) return;
      const data = await res.json();
      setProductosInfo((prev) => ({
        ...prev,
        [id]: { nombre: data.nombre, imagen_url: data.imagen_url },
      }));
    } catch (err) {
      console.error('Error resolviendo producto:', err);
    }
  }

  // Trae el detalle (con items) de cada venta que aún no tengamos en caché
  async function resolverItemsVenta(ventaId) {
    if (!ventaId || itemsPorVenta[ventaId]) return;
    try {
      const res = await fetch(`${API_URL}/ventas/${ventaId}`);
      if (!res.ok) return;
      const data = await res.json();
      setItemsPorVenta((prev) => ({ ...prev, [ventaId]: data.items ?? [] }));
    } catch (err) {
      console.error('Error resolviendo items de venta:', err);
    }
  }

  useEffect(() => {
    ventas.forEach((v) => resolverItemsVenta(v.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ventas]);

  useEffect(() => {
    const canal = supabase
      .channel('inventario-en-vivo')
      .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'inventario' }, (payload) => {
        setUltimoCambio(payload.new);
        resolverProducto(payload.new.producto_id);
        cargarInventarioBajoStock();
        cargarInventarioCompleto();
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        timeoutRef.current = setTimeout(() => setUltimoCambio(null), 5000);
      })
      .subscribe();

    const canalVentas = supabase
      .channel('ventas-en-vivo')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'ventas' }, () => {
        cargarVentasCompletadas();
      })
      .subscribe();

    return () => {
      supabase.removeChannel(canal);
      supabase.removeChannel(canalVentas);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  function dentroDelRango(fechaISO) {
    const fecha = new Date(fechaISO);
    const ahora = new Date();
    if (rango === 'todo') return true;
    if (rango === 'hoy') return fecha.toDateString() === ahora.toDateString();
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

  // --- Gráfica de tendencia por hora ---
  const ventasPorHora = {};
  ventasFiltradas.forEach((v) => {
    const hora = new Date(v.created_at).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
    ventasPorHora[hora] = (ventasPorHora[hora] || 0) + Number(v.total);
  });
  const datosGrafica = Object.entries(ventasPorHora)
    .map(([hora, total]) => ({ hora, total }))
    .sort((a, b) => (a.hora > b.hora ? 1 : -1));

  // --- Dona de salud de inventario ---
  const normales = inventarioCompleto.filter((i) => i.stock_actual > i.stock_minimo).length;
  const bajos = inventarioCompleto.filter((i) => i.stock_actual > 0 && i.stock_actual <= i.stock_minimo).length;
  const agotadosTotal = inventarioCompleto.filter((i) => i.stock_actual === 0).length;
  const datosDona = [
    { name: 'Normal', value: normales, color: '#22D3B9' },
    { name: 'Bajo stock', value: bajos, color: '#F5A623' },
    { name: 'Agotado', value: agotadosTotal, color: '#F43F5E' },
  ].filter((d) => d.value > 0);

  // --- Top 5 productos por ingresos ---
  const ingresosPorProducto = {};
  ventasFiltradas.forEach((v) => {
    const items = itemsPorVenta[v.id] ?? [];
    items.forEach((item) => {
      const nombre = item.producto?.nombre ?? productosInfo[item.producto_id]?.nombre ?? 'Producto';
      ingresosPorProducto[nombre] = (ingresosPorProducto[nombre] || 0) + Number(item.subtotal ?? 0);
    });
  });
  const topProductos = Object.entries(ingresosPorProducto)
    .map(([nombre, total]) => ({ nombre, total }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 5);

  const infoUltimoCambio = ultimoCambio ? productosInfo[ultimoCambio.producto_id] : null;

  return (
    <div className="board">
      <div className="board-header">
        <div className="brand">
          <div className="brand-badge">TM</div>
          <div>
            <h1>Tienda Mérida</h1>
            <p className="brand-subtitle">Centro de operaciones · Monitoreo en tiempo real</p>
          </div>
        </div>
        <div className="board-status">
          <span className="dot-live"></span>
          EN VIVO
        </div>
      </div>

      {agotados.length > 0 && (
        <div className="alert-agotado">
          <span className="alert-icon">⛔</span>
          {agotados.length === 1
            ? `${productosInfo[agotados[0].producto_id]?.nombre ?? '1 producto'} agotado — reabastecer de inmediato`
            : `${agotados.length} productos agotados — reabastecer de inmediato`}
        </div>
      )}

      {ultimoCambio && (
        <div className="ticker">
          <span className="ticker-label">Stock actualizado</span>
          {infoUltimoCambio?.nombre ?? ultimoCambio.producto_id?.slice(0, 8)} → nuevo stock: {ultimoCambio.stock_actual}
        </div>
      )}

      <div className="filtro-rango">
        <button className={rango === 'hoy' ? 'activo' : ''} onClick={() => setRango('hoy')}>Hoy</button>
        <button className={rango === '7dias' ? 'activo' : ''} onClick={() => setRango('7dias')}>Últimos 7 días</button>
        <button className={rango === 'todo' ? 'activo' : ''} onClick={() => setRango('todo')}>Todo</button>
      </div>

      <div className="stats">
        <div className="stat-card stat-card-spark">
          <div className="stat-card-top">
            <span className="stat-icon icon-purple">💵</span>
            <div>
              <span className="stat-label">Total ({rango})</span>
              <span className="stat-value">${totalDelDia.toFixed(2)}</span>
            </div>
          </div>
          {datosGrafica.length > 1 && (
            <ResponsiveContainer width="100%" height={36}>
              <LineChart data={datosGrafica}>
                <Line type="monotone" dataKey="total" stroke="#8B5CF6" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="stat-card">
          <span className="stat-icon icon-blue">🧾</span>
          <div>
            <span className="stat-label">Ticket promedio</span>
            <span className="stat-value">${ticketPromedio.toFixed(2)}</span>
          </div>
        </div>
        <div className="stat-card">
          <span className="stat-icon icon-teal">✅</span>
          <div>
            <span className="stat-label">Ventas cerradas</span>
            <span className="stat-value">{ventasFiltradas.length}</span>
          </div>
        </div>
      </div>

      {/* --- Fila de dos gráficas: tendencia + top productos --- */}
      <div className="chart-row">
        {datosGrafica.length > 0 && (
          <div className="chart-card">
            <h2>Tendencia de ventas por hora</h2>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={datosGrafica}>
                <defs>
                  <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="#8B5CF6" />
                    <stop offset="100%" stopColor="#38BDF8" />
                  </linearGradient>
                </defs>
                <XAxis dataKey="hora" tick={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, fill: '#8B92B0' }} axisLine={{ stroke: '#232842' }} tickLine={false} />
                <YAxis tick={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, fill: '#8B92B0' }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, background: '#1B2140', border: '1px solid #2E345A', borderRadius: 8, color: '#F4F5F7' }}
                  labelStyle={{ color: '#8B92B0' }}
                />
                <Line type="monotone" dataKey="total" stroke="url(#lineGrad)" strokeWidth={3} dot={{ r: 3, fill: '#38BDF8' }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {datosDona.length > 0 && (
          <div className="chart-card chart-card-donut">
            <h2>Salud del inventario</h2>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={datosDona} dataKey="value" nameKey="name" innerRadius={55} outerRadius={80} paddingAngle={3}>
                  {datosDona.map((entry, index) => (
                    <Cell key={index} fill={entry.color} stroke="none" />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, background: '#1B2140', border: '1px solid #2E345A', borderRadius: 8, color: '#F4F5F7' }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="donut-legend">
              {datosDona.map((d) => (
                <div className="donut-legend-item" key={d.name}>
                  <span className="legend-dot" style={{ background: d.color }}></span>
                  {d.name} ({d.value})
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {topProductos.length > 0 && (
        <div className="chart-card">
          <h2>Top 5 productos por ingresos ({rango})</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={topProductos} layout="vertical" margin={{ left: 20 }}>
              <defs>
                <linearGradient id="barGrad" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#8B5CF6" />
                  <stop offset="100%" stopColor="#38BDF8" />
                </linearGradient>
              </defs>
              <XAxis type="number" tick={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, fill: '#8B92B0' }} axisLine={{ stroke: '#232842' }} tickLine={false} />
              <YAxis
                type="category"
                dataKey="nombre"
                width={160}
                tick={{ fontFamily: '-apple-system, sans-serif', fontSize: 12, fill: '#F4F5F7' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, background: '#1B2140', border: '1px solid #2E345A', borderRadius: 8, color: '#F4F5F7' }}
                formatter={(value) => [`$${value.toFixed(2)}`, 'Ingresos']}
              />
              <Bar dataKey="total" fill="url(#barGrad)" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="panels">
        <div className="panel-card">
          <h2>⚠ Bajo stock</h2>
          {inventario.length === 0 ? (
            <p className="panel-empty">Todo el inventario está en niveles normales.</p>
          ) : (
            inventario.map((item) => {
              const info = productosInfo[item.producto_id];
              const capacidadEstimada = Math.max(item.stock_minimo * 5, 20);
              const pct = Math.min(100, Math.round((item.stock_actual / capacidadEstimada) * 100));
              return (
                <div className="row-stock" key={item.id}>
                  <div className="row-stock-top">
                    {info?.imagen_url ? (
                      <img src={info.imagen_url} alt={info.nombre} className="thumb" />
                    ) : (
                      <div className="thumb thumb-placeholder">📦</div>
                    )}
                    <span className="row-name">{info?.nombre ?? item.producto_id}</span>
                    <span className={`stock-badge ${item.stock_actual === 0 ? 'critico' : 'bajo'}`}>
                      {item.stock_actual === 0 ? 'AGOTADO' : `${item.stock_actual} u.`}
                    </span>
                  </div>
                  <div className="bar-track">
                    <div
                      className={`bar-fill ${item.stock_actual === 0 ? 'bar-critico' : ''}`}
                      style={{ width: `${pct}%` }}
                    ></div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="panel-card">
          <h2>Ventas completadas</h2>
          {ventasFiltradas.length === 0 ? (
            <p className="panel-empty">Sin ventas en este rango.</p>
          ) : (
            ventasFiltradas.map((venta) => (
              <div className="row-venta" key={venta.id}>
                <div className="venta-avatar">🧾</div>
                <span className="row-name">{venta.folio}</span>
                <span className="status-pill">Completada</span>
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