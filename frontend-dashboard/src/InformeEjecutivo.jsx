import { useMemo, useRef } from 'react';
import { TrendingUp, TrendingDown, AlertTriangle, CheckCircle2, Download, Printer, FileSpreadsheet } from 'lucide-react';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import * as XLSX from 'xlsx';
import FiltroPeriodo from './FiltroPeriodo';
import './InformeEjecutivo.css';

const DIAS_SEMANA = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];

function rangoADias(rango, fechaInicio, fechaFin) {
  if (rango === 'hoy') return 1;
  if (rango === 'semana') return 7;
  if (rango === 'mes') return 30;
  if (rango === 'personalizado' && fechaInicio && fechaFin) {
    const inicio = new Date(`${fechaInicio}T00:00:00`);
    const fin = new Date(`${fechaFin}T23:59:59`);
    const dias = Math.round((fin - inicio) / (1000 * 60 * 60 * 24)) + 1;
    return Math.max(dias, 1);
  }
  return 90; // 'todo' -> usamos 90 días como ventana de comparación razonable
}

function formatearFecha(fechaISO) {
  if (!fechaISO) return '';
  return new Date(`${fechaISO}T00:00:00`).toLocaleDateString('es-MX', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function nombreProducto(productosInfo, id) {
  return productosInfo[id]?.nombre ?? (id ? `Producto ${id.slice(0, 8)}` : 'Producto');
}

export default function InformeEjecutivo({
  rango,
  setRango,
  fechaInicio,
  fechaFin,
  setFechaInicio,
  setFechaFin,
  ventasFiltradas,
  ventasTodas,
  itemsPorVenta,
  productosInfo,
  inventarioCompleto,
}) {
  const reporteRef = useRef(null);

  const analisis = useMemo(() => {
    const dias = rangoADias(rango, fechaInicio, fechaFin);

    // --- Periodo actual vs periodo anterior equivalente ---
    const ahora = new Date();
    let inicioActual;
    let inicioAnterior;

    if (rango === 'personalizado' && fechaInicio && fechaFin) {
      // El "periodo actual" es exactamente el rango elegido; el "anterior"
      // es un tramo de la misma duración justo antes de ese rango.
      inicioActual = new Date(`${fechaInicio}T00:00:00`);
      const finActual = new Date(`${fechaFin}T23:59:59`);
      const duracionMs = finActual - inicioActual;
      inicioAnterior = new Date(inicioActual.getTime() - duracionMs);
    } else {
      inicioActual = new Date(ahora);
      inicioActual.setDate(ahora.getDate() - dias);
      inicioAnterior = new Date(ahora);
      inicioAnterior.setDate(ahora.getDate() - dias * 2);
    }

    const ventasAnteriores = ventasTodas.filter((v) => {
      if (!v.created_at) return false;
      const f = new Date(v.created_at);
      return f >= inicioAnterior && f < inicioActual;
    });

    const totalActual = ventasFiltradas.reduce((acc, v) => acc + Number(v.total || 0), 0);
    const totalAnterior = ventasAnteriores.reduce((acc, v) => acc + Number(v.total || 0), 0);
    const variacionPct = totalAnterior > 0 ? ((totalActual - totalAnterior) / totalAnterior) * 100 : null;

    const ticketPromedio = ventasFiltradas.length > 0 ? totalActual / ventasFiltradas.length : 0;
    const ticketAnterior = ventasAnteriores.length > 0 ? totalAnterior / ventasAnteriores.length : 0;

    // --- Ingresos y unidades por producto ---
    const ingresosPorProducto = {};
    const unidadesPorProducto = {};
    const ingresosPorCategoria = {};
    let ventasAutomaticas = 0;
    let ventasManuales = 0;

    ventasFiltradas.forEach((v) => {
      const items = itemsPorVenta[v.id] || [];
      items.forEach((item) => {
        const nombre = nombreProducto(productosInfo, item.producto_id);
        const subtotal = Number(item.subtotal || 0);
        ingresosPorProducto[nombre] = (ingresosPorProducto[nombre] || 0) + subtotal;
        unidadesPorProducto[nombre] = (unidadesPorProducto[nombre] || 0) + Number(item.cantidad || 0);

        const cat = productosInfo[item.producto_id]?.categoria || 'General';
        ingresosPorCategoria[cat] = (ingresosPorCategoria[cat] || 0) + subtotal;

        if (item.metodo_deteccion === 'manual') ventasManuales += 1;
        else ventasAutomaticas += 1;
      });
    });

    const topProductos = Object.entries(ingresosPorProducto)
      .map(([nombre, total]) => ({ nombre, total, unidades: unidadesPorProducto[nombre] || 0 }))
      .sort((a, b) => b.total - a.total);

    const masVendidos = topProductos.slice(0, 5);
    const menosVendidos = [...topProductos].sort((a, b) => a.total - b.total).slice(0, 5);

    const catRanking = Object.entries(ingresosPorCategoria)
      .map(([categoria, total]) => ({ categoria, total }))
      .sort((a, b) => b.total - a.total);

    // Productos del catálogo sin NINGUNA venta en el periodo
    const idsConVenta = new Set(
      ventasFiltradas.flatMap((v) => (itemsPorVenta[v.id] || []).map((i) => i.producto_id))
    );
    const productosSinVenta = inventarioCompleto
      .filter((inv) => !idsConVenta.has(inv.producto_id))
      .map((inv) => nombreProducto(productosInfo, inv.producto_id));

    // --- Ventas por hora y por día de semana ---
    const porHora = {};
    const porDiaSemana = {};
    ventasFiltradas.forEach((v) => {
      if (!v.created_at) return;
      const f = new Date(v.created_at);
      const h = f.getHours();
      const d = f.getDay();
      porHora[h] = (porHora[h] || 0) + Number(v.total || 0);
      porDiaSemana[d] = (porDiaSemana[d] || 0) + Number(v.total || 0);
    });
    const horaPico = Object.entries(porHora).sort((a, b) => b[1] - a[1])[0];
    const diaPico = Object.entries(porDiaSemana).sort((a, b) => b[1] - a[1])[0];

    // --- Inventario ---
    const agotados = inventarioCompleto.filter((i) => i.stock_actual === 0);
    const bajoStock = inventarioCompleto.filter((i) => i.stock_actual > 0 && i.stock_actual <= i.stock_minimo);
    const valorReposicionEstimado = [...agotados, ...bajoStock].reduce((acc, i) => {
      const precio = productosInfo[i.producto_id]?.precio || 0;
      const faltante = Math.max(i.stock_minimo - i.stock_actual, 0);
      return acc + faltante * precio;
    }, 0);

    // --- % detección automática (CV) vs manual ---
    const totalDetecciones = ventasAutomaticas + ventasManuales;
    const pctManual = totalDetecciones > 0 ? (ventasManuales / totalDetecciones) * 100 : 0;

    // --- Generación de "áreas de mejora" ---
    const hallazgos = [];

    if (variacionPct !== null) {
      if (variacionPct <= -10) {
        hallazgos.push({
          tipo: 'alerta',
          texto: `Las ventas cayeron ${Math.abs(variacionPct).toFixed(1)}% comparado con el periodo anterior equivalente. Vale la pena revisar si hubo menos tráfico, cambios de precio o quiebres de stock en productos clave.`,
        });
      } else if (variacionPct >= 10) {
        hallazgos.push({
          tipo: 'positivo',
          texto: `Las ventas subieron ${variacionPct.toFixed(1)}% comparado con el periodo anterior. Identifica qué lo impulsó (producto, día, promoción) para repetirlo.`,
        });
      }
    }

    if (agotados.length > 0) {
      hallazgos.push({
        tipo: 'alerta',
        texto: `${agotados.length} producto(s) agotado(s) ahora mismo: ${agotados
          .map((i) => nombreProducto(productosInfo, i.producto_id))
          .join(', ')}. Cada día sin reabastecer es venta que se está perdiendo.`,
      });
    }

    if (bajoStock.length > 0) {
      hallazgos.push({
        tipo: 'atencion',
        texto: `${bajoStock.length} producto(s) con stock bajo el mínimo — conviene reabastecer antes de que se agoten.`,
      });
    }

    if (productosSinVenta.length > 0 && productosSinVenta.length <= 8) {
      hallazgos.push({
        tipo: 'atencion',
        texto: `${productosSinVenta.length} producto(s) del catálogo no tuvieron ni una venta en este periodo: ${productosSinVenta.join(', ')}. Revisar exhibición, precio o si vale la pena mantenerlos.`,
      });
    }

    if (pctManual > 30 && totalDetecciones >= 5) {
      hallazgos.push({
        tipo: 'atencion',
        texto: `${pctManual.toFixed(0)}% de los productos se registraron manualmente en vez de por cámara/código de barras. Si esto sigue subiendo, conviene revisar el reconocimiento visual (ángulo de cámara, catálogo de referencia).`,
      });
    }

    if (horaPico) {
      const [hora, total] = horaPico;
      hallazgos.push({
        tipo: 'info',
        texto: `La hora con más ventas es ${hora.toString().padStart(2, '0')}:00 (${total.toFixed(2)} en ingresos). Considera reforzar personal en ese horario.`,
      });
    }

    if (diaPico && rango !== 'hoy') {
      const [dia, total] = diaPico;
      hallazgos.push({
        tipo: 'info',
        texto: `${DIAS_SEMANA[Number(dia)]} es el día con más ventas en el periodo analizado (${total.toFixed(2)}).`,
      });
    }

    if (masVendidos.length > 0) {
      const topShare = totalActual > 0 ? (masVendidos[0].total / totalActual) * 100 : 0;
      if (topShare > 40) {
        hallazgos.push({
          tipo: 'atencion',
          texto: `"${masVendidos[0].nombre}" concentra ${topShare.toFixed(0)}% de los ingresos del periodo. Es tu producto más importante — asegúrate de nunca quedarte sin stock de él.`,
        });
      }
    }

    if (hallazgos.length === 0) {
      hallazgos.push({
        tipo: 'positivo',
        texto: 'No se detectaron alertas relevantes en este periodo. El negocio opera dentro de parámetros normales.',
      });
    }

    return {
      totalActual,
      totalAnterior,
      variacionPct,
      ticketPromedio,
      ticketAnterior,
      numVentas: ventasFiltradas.length,
      masVendidos,
      menosVendidos,
      catRanking,
      productosSinVenta,
      horaPico,
      diaPico,
      agotados,
      bajoStock,
      valorReposicionEstimado,
      pctManual,
      totalDetecciones,
      hallazgos,
    };
  }, [rango, fechaInicio, fechaFin, ventasFiltradas, ventasTodas, itemsPorVenta, productosInfo, inventarioCompleto]);

  const rangoLabel =
    rango === 'hoy' ? 'Hoy' :
    rango === 'semana' ? 'Últimos 7 días' :
    rango === 'mes' ? 'Últimos 30 días' :
    rango === 'personalizado' && fechaInicio && fechaFin
      ? `Del ${formatearFecha(fechaInicio)} al ${formatearFecha(fechaFin)}`
      : 'Todo el periodo';

  const rangoSlug =
    rango === 'personalizado' && fechaInicio && fechaFin
      ? `${fechaInicio}_a_${fechaFin}`
      : rango;
  const fechaGeneracion = new Date().toLocaleString('es-MX', { dateStyle: 'long', timeStyle: 'short' });

  function exportarPDF() {
    const doc = new jsPDF();
    const margenX = 14;
    let y = 18;

    doc.setFont('helvetica', 'bold');
    doc.setFontSize(16);
    doc.text('Informe Ejecutivo — Tienda Mérida', margenX, y);
    y += 7;
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(10);
    doc.setTextColor(100);
    doc.text(`Periodo: ${rangoLabel}  ·  Generado: ${fechaGeneracion}`, margenX, y);
    doc.setTextColor(0);
    y += 10;

    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.text('Resumen', margenX, y);
    y += 2;

    autoTable(doc, {
      startY: y + 2,
      theme: 'grid',
      head: [['Métrica', 'Valor']],
      body: [
        ['Ventas totales', `$${analisis.totalActual.toFixed(2)}`],
        ['Ticket promedio', `$${analisis.ticketPromedio.toFixed(2)}`],
        ['Ventas cerradas', `${analisis.numVentas}`],
        [
          'Variación vs. periodo anterior',
          analisis.variacionPct === null ? 'Sin datos previos' : `${analisis.variacionPct >= 0 ? '+' : ''}${analisis.variacionPct.toFixed(1)}%`,
        ],
        ['Productos agotados', `${analisis.agotados.length}`],
        ['Productos con stock bajo', `${analisis.bajoStock.length}`],
        ['Ventas registradas manualmente', `${analisis.pctManual.toFixed(0)}%`],
      ],
      styles: { fontSize: 9, cellPadding: 2.5 },
      headStyles: { fillColor: [139, 92, 246] },
      margin: { left: margenX, right: margenX },
    });

    y = doc.lastAutoTable.finalY + 10;
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.text('Áreas de mejora / hallazgos', margenX, y);
    y += 2;

    autoTable(doc, {
      startY: y + 2,
      theme: 'striped',
      body: analisis.hallazgos.map((h) => [h.texto]),
      styles: { fontSize: 9, cellPadding: 3 },
      margin: { left: margenX, right: margenX },
    });

    y = doc.lastAutoTable.finalY + 10;
    if (y > 250) {
      doc.addPage();
      y = 18;
    }
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.text('Top 5 productos por ingresos', margenX, y);
    autoTable(doc, {
      startY: y + 4,
      theme: 'grid',
      head: [['Producto', 'Unidades', 'Ingresos']],
      body: analisis.masVendidos.map((p) => [p.nombre, `${p.unidades}`, `$${p.total.toFixed(2)}`]),
      styles: { fontSize: 9, cellPadding: 2.5 },
      headStyles: { fillColor: [56, 189, 248] },
      margin: { left: margenX, right: margenX },
    });

    if (analisis.agotados.length > 0 || analisis.bajoStock.length > 0) {
      let y2 = doc.lastAutoTable.finalY + 10;
      if (y2 > 250) {
        doc.addPage();
        y2 = 18;
      }
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(12);
      doc.text('Inventario en riesgo', margenX, y2);
      autoTable(doc, {
        startY: y2 + 4,
        theme: 'grid',
        head: [['Producto', 'Stock actual', 'Estado']],
        body: [
          ...analisis.agotados.map((i) => [nombreProducto(productosInfo, i.producto_id), `${i.stock_actual}`, 'AGOTADO']),
          ...analisis.bajoStock.map((i) => [nombreProducto(productosInfo, i.producto_id), `${i.stock_actual}`, 'Bajo mínimo']),
        ],
        styles: { fontSize: 9, cellPadding: 2.5 },
        headStyles: { fillColor: [244, 63, 94] },
        margin: { left: margenX, right: margenX },
      });
    }

    doc.save(`informe-ejecutivo-${rangoSlug}-${new Date().toISOString().slice(0, 10)}.pdf`);
  }

  function exportarExcel() {
    const wb = XLSX.utils.book_new();

    const wsResumen = XLSX.utils.aoa_to_sheet([
      ['Informe Ejecutivo — Tienda Mérida'],
      [`Periodo: ${rangoLabel}`, `Generado: ${fechaGeneracion}`],
      [],
      ['Métrica', 'Valor'],
      ['Ventas totales', analisis.totalActual.toFixed(2)],
      ['Ticket promedio', analisis.ticketPromedio.toFixed(2)],
      ['Ventas cerradas', analisis.numVentas],
      ['Variación vs. periodo anterior (%)', analisis.variacionPct === null ? 'N/A' : analisis.variacionPct.toFixed(1)],
      ['Productos agotados', analisis.agotados.length],
      ['Productos con stock bajo', analisis.bajoStock.length],
      ['Ventas registradas manualmente (%)', analisis.pctManual.toFixed(0)],
      [],
      ['Áreas de mejora / hallazgos'],
      ...analisis.hallazgos.map((h) => [h.texto]),
    ]);
    wsResumen['!cols'] = [{ wch: 45 }, { wch: 25 }];
    XLSX.utils.book_append_sheet(wb, wsResumen, 'Resumen');

    const wsTop = XLSX.utils.json_to_sheet(
      analisis.masVendidos.map((p) => ({ Producto: p.nombre, Unidades: p.unidades, Ingresos: p.total.toFixed(2) }))
    );
    XLSX.utils.book_append_sheet(wb, wsTop, 'Top productos');

    const wsBajos = XLSX.utils.json_to_sheet(
      analisis.menosVendidos.map((p) => ({ Producto: p.nombre, Unidades: p.unidades, Ingresos: p.total.toFixed(2) }))
    );
    XLSX.utils.book_append_sheet(wb, wsBajos, 'Menos vendidos');

    const wsInventario = XLSX.utils.json_to_sheet(
      inventarioCompleto.map((i) => ({
        Producto: nombreProducto(productosInfo, i.producto_id),
        'Stock actual': i.stock_actual,
        'Stock mínimo': i.stock_minimo,
        Estado: i.stock_actual === 0 ? 'AGOTADO' : i.stock_actual <= i.stock_minimo ? 'Bajo mínimo' : 'Normal',
      }))
    );
    XLSX.utils.book_append_sheet(wb, wsInventario, 'Inventario');

    const wsVentas = XLSX.utils.json_to_sheet(
      ventasFiltradas.map((v) => ({
        Folio: v.folio,
        Fecha: v.created_at ? new Date(v.created_at).toLocaleString('es-MX') : '',
        Total: Number(v.total || 0).toFixed(2),
        'Método de pago': v.metodo_pago || '',
      }))
    );
    XLSX.utils.book_append_sheet(wb, wsVentas, 'Ventas');

    XLSX.writeFile(wb, `informe-ejecutivo-${rangoSlug}-${new Date().toISOString().slice(0, 10)}.xlsx`);
  }

  function imprimir() {
    window.print();
  }

  return (
    <div className="informe-ejecutivo" ref={reporteRef}>
      <div className="informe-header no-print">
        <div>
          <h1>Informe Ejecutivo</h1>
          <p className="informe-subtitle">Lectura para el dueño · {rangoLabel} · generado {fechaGeneracion}</p>
        </div>
        <div className="informe-acciones">
          <button className="btn-informe" onClick={imprimir}>
            <Printer size={16} /> Imprimir
          </button>
          <button className="btn-informe" onClick={exportarExcel}>
            <FileSpreadsheet size={16} /> Exportar Excel
          </button>
          <button className="btn-informe btn-informe-principal" onClick={exportarPDF}>
            <Download size={16} /> Exportar PDF
          </button>
        </div>
      </div>

      <FiltroPeriodo
        className="no-print"
        rango={rango}
        setRango={setRango}
        fechaInicio={fechaInicio}
        fechaFin={fechaFin}
        setFechaInicio={setFechaInicio}
        setFechaFin={setFechaFin}
      />

      <div className="print-only print-title">
        <h1>Informe Ejecutivo — Tienda Mérida</h1>
        <p>Periodo: {rangoLabel} · Generado: {fechaGeneracion}</p>
      </div>

      {/* --- KPIs con contexto --- */}
      <div className="informe-kpis">
        <div className="informe-kpi">
          <span className="informe-kpi-label">Ventas totales</span>
          <span className="informe-kpi-valor">${analisis.totalActual.toFixed(2)}</span>
          {analisis.variacionPct !== null && (
            <span className={`informe-kpi-trend ${analisis.variacionPct >= 0 ? 'up' : 'down'}`}>
              {analisis.variacionPct >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
              {Math.abs(analisis.variacionPct).toFixed(1)}% vs. periodo anterior
            </span>
          )}
        </div>
        <div className="informe-kpi">
          <span className="informe-kpi-label">Ticket promedio</span>
          <span className="informe-kpi-valor">${analisis.ticketPromedio.toFixed(2)}</span>
        </div>
        <div className="informe-kpi">
          <span className="informe-kpi-label">Ventas cerradas</span>
          <span className="informe-kpi-valor">{analisis.numVentas}</span>
        </div>
        <div className="informe-kpi">
          <span className="informe-kpi-label">Reconocimiento automático</span>
          <span className="informe-kpi-valor">{(100 - analisis.pctManual).toFixed(0)}%</span>
          <span className="informe-kpi-sub">de los productos vía cámara/código de barras</span>
        </div>
      </div>

      {/* --- Hallazgos / áreas de mejora --- */}
      <div className="informe-seccion">
        <h2>Áreas de mejora</h2>
        <div className="hallazgos-lista">
          {analisis.hallazgos.map((h, idx) => (
            <div className={`hallazgo hallazgo-${h.tipo}`} key={idx}>
              {h.tipo === 'positivo' ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
              <p>{h.texto}</p>
            </div>
          ))}
        </div>
      </div>

      {/* --- Tablas --- */}
      <div className="informe-tablas">
        <div className="informe-tabla-card">
          <h2>Top 5 productos</h2>
          <table>
            <thead>
              <tr><th>Producto</th><th>Unidades</th><th>Ingresos</th></tr>
            </thead>
            <tbody>
              {analisis.masVendidos.map((p) => (
                <tr key={p.nombre}>
                  <td>{p.nombre}</td>
                  <td>{p.unidades}</td>
                  <td>${p.total.toFixed(2)}</td>
                </tr>
              ))}
              {analisis.masVendidos.length === 0 && (
                <tr><td colSpan={3} className="tabla-vacia">Sin ventas en este periodo.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="informe-tabla-card">
          <h2>Ingresos por categoría</h2>
          <table>
            <thead>
              <tr><th>Categoría</th><th>Ingresos</th></tr>
            </thead>
            <tbody>
              {analisis.catRanking.map((c) => (
                <tr key={c.categoria}>
                  <td>{c.categoria}</td>
                  <td>${c.total.toFixed(2)}</td>
                </tr>
              ))}
              {analisis.catRanking.length === 0 && (
                <tr><td colSpan={2} className="tabla-vacia">Sin datos.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="informe-tabla-card">
          <h2>Inventario en riesgo</h2>
          <table>
            <thead>
              <tr><th>Producto</th><th>Stock</th><th>Estado</th></tr>
            </thead>
            <tbody>
              {[...analisis.agotados, ...analisis.bajoStock].map((i) => (
                <tr key={i.id}>
                  <td>{nombreProducto(productosInfo, i.producto_id)}</td>
                  <td>{i.stock_actual}</td>
                  <td>
                    <span className={`estado-pill ${i.stock_actual === 0 ? 'critico' : 'bajo'}`}>
                      {i.stock_actual === 0 ? 'Agotado' : 'Bajo mínimo'}
                    </span>
                  </td>
                </tr>
              ))}
              {analisis.agotados.length === 0 && analisis.bajoStock.length === 0 && (
                <tr><td colSpan={3} className="tabla-vacia">Inventario saludable.</td></tr>
              )}
            </tbody>
          </table>
          {analisis.valorReposicionEstimado > 0 && (
            <p className="tabla-footnote">
              Inversión estimada para reabastecer al mínimo: <strong>${analisis.valorReposicionEstimado.toFixed(2)}</strong>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}