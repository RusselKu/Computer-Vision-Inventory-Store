import './FiltroPeriodo.css';

/**
 * Selector de periodo compartido entre el Panel de Métricas y el Informe Ejecutivo.
 * Controla el mismo estado "rango" ('hoy' | 'semana' | 'mes' | 'todo' | 'personalizado')
 * que vive en App.jsx, más un rango de fechas personalizado (fechaInicio / fechaFin).
 */
export default function FiltroPeriodo({
  rango,
  setRango,
  fechaInicio,
  fechaFin,
  setFechaInicio,
  setFechaFin,
  className = '',
}) {
  const hoyISO = new Date().toISOString().slice(0, 10);

  function aplicarPersonalizado() {
    if (fechaInicio && fechaFin) {
      setRango('personalizado');
    }
  }

  return (
    <div className={`filtro-periodo ${className}`}>
      <div className="filtro-periodo-botones">
        <button className={rango === 'hoy' ? 'activo' : ''} onClick={() => setRango('hoy')}>
          Hoy
        </button>
        <button className={rango === 'semana' ? 'activo' : ''} onClick={() => setRango('semana')}>
          Semana
        </button>
        <button className={rango === 'mes' ? 'activo' : ''} onClick={() => setRango('mes')}>
          Mes
        </button>
        <button className={rango === 'todo' ? 'activo' : ''} onClick={() => setRango('todo')}>
          Todo
        </button>
      </div>

      <div className="filtro-periodo-personalizado">
        <input
          type="date"
          value={fechaInicio}
          max={fechaFin || hoyISO}
          onChange={(e) => setFechaInicio(e.target.value)}
          aria-label="Fecha inicio"
        />
        <span className="filtro-periodo-separador">a</span>
        <input
          type="date"
          value={fechaFin}
          min={fechaInicio || undefined}
          max={hoyISO}
          onChange={(e) => setFechaFin(e.target.value)}
          aria-label="Fecha fin"
        />
        <button
          className={`filtro-periodo-aplicar ${rango === 'personalizado' ? 'activo' : ''}`}
          disabled={!fechaInicio || !fechaFin}
          onClick={aplicarPersonalizado}
        >
          Aplicar
        </button>
      </div>
    </div>
  );
}
