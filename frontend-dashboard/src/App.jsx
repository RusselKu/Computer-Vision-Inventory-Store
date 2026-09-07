import { useEffect, useState, useRef } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, BarChart, Bar,
} from 'recharts';
import { ShoppingCart, BarChart3 } from 'lucide-react';
import { supabase } from './supabaseClient';
import PosView from './PosView';
import './App.css';

const API_URL = 'http://localhost:8000/api/v1';

function App() {
  const [activeTab, setActiveTab] = useState('pos'); // 'pos' o 'dashboard'
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
      const data = await res.json();
      setProductosInfo((prev) => ({ ...prev, [id]: data }));
    } catch {
      // Ignorar error si no se encuentra
    }
  }

  useEffect(() => {
    const canal = supabase
      .channel('realtime:inventario')
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'inventario' },
        (payload) => {
          const nuevoItem = payload.new;
          resolverProducto(nuevoItem.producto_id);

          setInventario((prev) => {
            const existe = prev.some((i) => i.id === nuevoItem.id);
            if (nuevoItem.stock_actual <= nuevoItem.stock_minimo) {
              return existe ? prev.map((i) => (i.id === nuevoItem.id ? nuevoItem : i)) : [...prev, nuevoItem];
            }
            return prev.filter((i) => i.id !== nuevoItem.id);
          });

          setInventarioCompleto((prev) =>
            prev.map((i) => (i.id === nuevoItem.id ? nuevoItem : i))
          );

          setUltimoCambio(nuevoItem);
          if (timeoutRef.current) clearTimeout(timeoutRef.current);
          timeoutRef.current = setTimeout(() => setUltimoCambio(null), 5000);
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(canal);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  useEffect(() => {
    const canalVentas = supabase
      .channel('realtime:ventas')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'ventas' },
        (payload) => {
          const nuevaVenta = payload.new;
          if (nuevaVenta.estado === 'completada') {
            setVentas((prev) => [nuevaVenta, ...prev]);
          }
        }
      )
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'ventas' },
        (payload) => {
          const ventaActualizada = payload.new;
          if (ventaActualizada.estado === 'completada') {
            setVentas((prev) => {
              const existe = prev.some((v) => v.id === ventaActualizada.id);
              if (existe) {
                return prev.map((v) => (v.id === ventaActualizada.id ? ventaActualizada : v));
              }
              return [ventaActualizada, ...prev];
            });
          }
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(canalVentas);
    };
  }, []);

  useEffect(() => {
    ventas.forEach((v) => {
      if (!itemsPorVenta[v.id]) {
        fetch(`${API_URL}/ventas/${v.id}`)
          .then((res) => res.json())
          .then((data) => {
            if (data.items) {
              setItemsPorVenta((prev) => ({ ...prev, [v.id]: data.items }));
              data.items.forEach((item) => {
                if (item.producto_id) resolverProducto(item.producto_id);
              });
            }
          })
          .catch(() => {});
      }
    });
  }, [ventas]);

  const agotados = inventario.filter((item) => item.stock_actual === 0);

  const ventasFiltradas = ventas.filter((v) => {
    if (!v.created_at) return true;
    const fechaVenta = new Date(v.created_at);
    const ahora = new Date();
    if (rango === 'hoy') {
      return fechaVenta.toDateString() === ahora.toDateString();
    }
    if (rango === '7dias') {
      const hace7dias = new Date();
      hace7dias.setDate(ahora.getDate() - 7);
      return fechaVenta >= hace7dias;
    }
    return true;
  });

  const totalDelDia = ventasFiltradas.reduce((acc, v) => acc + Number(v.total || 0), 0);
  const ticketPromedio = ventasFiltradas.length > 0 ? totalDelDia / ventasFiltradas.length : 0;

  const ventasPorHora = ventasFiltradas.reduce((acc, v) => {
    if (!v.created_at) return acc;
    const hora = new Date(v.created_at).getHours();
    const etiqueta = `${hora.toString().padStart(2, '0')}:00`;
    acc[etiqueta] = (acc[etiqueta] || 0) + Number(v.total || 0);
    return acc;
  }, {});

  const datosGrafica = Object.entries(ventasPorHora)
    .map(([hora, total]) => ({ hora, total }))
    .sort((a, b) => a.hora.localeCompare(b.hora));

  const totalStockCritico = inventarioCompleto.filter((i) => i.stock_actual <= i.stock_minimo).length;
  const totalStockNormal = inventarioCompleto.length - totalStockCritico;

  const datosDona = inventarioCompleto.length === 0 ? [] : [
    { name: 'Normal', value: totalStockNormal, color: '#38BDF8' },
    { name: 'Bajo/Agotado', value: totalStockCritico, color: '#F43F5E' },
  ];

  const ingresosPorProducto = {};
  ventasFiltradas.forEach((v) => {
    const items = itemsPorVenta[v.id] || [];
    items.forEach((item) => {
      const nombre = productosInfo[item.producto_id]?.nombre || item.producto_id?.slice(0, 8) || 'Producto';
      ingresosPorProducto[nombre] = (ingresosPorProducto[nombre] || 0) + Number(item.subtotal || 0);
    });
  });

  const topProductos = Object.entries(ingresosPorProducto)
    .map(([nombre, total]) => ({ nombre, total }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 5);

  const infoUltimoCambio = ultimoCambio ? productosInfo[ultimoCambio.producto_id] : null;

  return (
    <div className="unified-app-wrapper">
      {/* BARRA SUPERIOR DE NAVEGACION POR PESTAÑAS */}
      <header className="main-top-navbar">
        <div className="navbar-brand">
          <div className="brand-logo-badge">TM</div>
          <div>
            <span className="navbar-app-title">Tienda Mérida</span>
            <span className="navbar-app-subtitle">Sistema POS & Analytics CV</span>
          </div>
        </div>

        <nav className="navbar-tabs">
          <button 
            className={`nav-tab-btn ${activeTab === 'pos' ? 'active' : ''}`}
            onClick={() => setActiveTab('pos')}
          >
            <ShoppingCart className="w-4 h-4" />
            <span>Punto de Venta (Cajero)</span>
          </button>

          <button 
            className={`nav-tab-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >
            <BarChart3 className="w-4 h-4" />
            <span>Panel de Métricas (Gerente)</span>
          </button>
        </nav>

        <div className="navbar-status-badge">
          <span className="dot-live"></span>
          <span>SISTEMA ACTIVO</span>
        </div>
      </header>

      {/* CONTENIDO SEGÚN PESTAÑA ACTIVA */}
      {activeTab === 'pos' ? (
        <PosView />
      ) : (
        <div className="board">
          <div className="board-header">
            <div className="brand">
              <div>
                <h1>Panel de Control Administrativo</h1>
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
      )}
    </div>
  );
}

export default App;