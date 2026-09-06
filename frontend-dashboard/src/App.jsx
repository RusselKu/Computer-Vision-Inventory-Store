import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { supabase } from './supabaseClient';
import './App.css';

const API_URL = 'http://localhost:8000/api/v1';

function App() {
  const [inventario, setInventario] = useState([]);
  const [ventas, setVentas] = useState([]);
  const [ultimoCambio, setUltimoCambio] = useState(null);

  useEffect(() => {
    cargarInventarioBajoStock();
    cargarVentasCompletadas();
  }, []);

  async function cargarInventarioBajoStock() {
    try {
      const res = await fetch(`${API_URL}/inventario?solo_bajo_stock=true`);
      const data = await res.json();
      setInventario(data);
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

  useEffect(() => {
    const canal = supabase
      .channel('inventario-en-vivo')
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'inventario' },
        (payload) => {
          setUltimoCambio(payload.new);
          cargarInventarioBajoStock();
        }
      )
      .subscribe();

    // También escuchamos ventas nuevas para refrescar la gráfica en vivo
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
    };
  }, []);

  const totalDelDia = ventas.reduce((acc, v) => acc + Number(v.total), 0);
  const ticketPromedio = ventas.length > 0 ? totalDelDia / ventas.length : 0;
  const agotados = inventario.filter((item) => item.stock_actual === 0);
  // Recharts necesita un array simple; usamos los últimos 4 dígitos del folio como etiqueta corta
  const datosGrafica = ventas
    .slice()
    .reverse()
    .map((v) => ({
      folio: v.folio.slice(-4),
      total: Number(v.total),
    }));

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
      ? '1 producto agotado — reabastecer de inmediato'
      : `${agotados.length} productos agotados — reabastecer de inmediato`}
      </div>
      )}
      {ultimoCambio && (
        <div className="ticker">
          <span className="ticker-label">Stock actualizado</span>
          Producto {ultimoCambio.producto_id?.slice(0, 8)} → nuevo stock: {ultimoCambio.stock_actual}
        </div>
      )}

      {/* --- Métricas grandes --- */}
      <div className="stats">
        <div className="stat">
          <span className="stat-label">Total del día</span>
          <span className="stat-value">${totalDelDia.toFixed(2)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Ticket promedio</span>
          <span className="stat-value">${ticketPromedio.toFixed(2)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Ventas cerradas</span>
          <span className="stat-value">{ventas.length}</span>
        </div>
      </div>

      {/* --- Gráfica de ventas --- */}
      {datosGrafica.length > 0 && (
        <div className="chart-panel">
          <h2>Ventas por folio</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={datosGrafica}>
              <XAxis
                dataKey="folio"
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
                cursor={{ fill: 'rgba(14,124,107,0.08)' }}
              />
              <Bar dataKey="total" fill="#0E7C6B" />
            </BarChart>
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
                <span className="row-name">{item.nombre_producto ?? item.producto_id}</span>
                <span className={`stock-badge ${item.stock_actual === 0 ? 'critico' : 'bajo'}`}>
                  {item.stock_actual === 0 ? 'AGOTADO' : `${item.stock_actual} u.`}
                </span>
              </div>
            ))
          )}
        </div>

        <div className="panel">
          <h2>Ventas completadas</h2>
          {ventas.length === 0 ? (
            <p className="panel-empty">Sin ventas registradas todavía.</p>
          ) : (
            ventas.map((venta) => (
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