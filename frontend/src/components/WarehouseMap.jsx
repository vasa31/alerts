const UNITS = {
  temperature: '°C',
  oxygen: '%',
  smoke: '',
}

function fmt(type, v) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  const u = UNITS[type] || ''
  return `${Number(v).toFixed(1)}${u ? ` ${u}` : ''}`
}

export default function WarehouseMap({ data }) {
  if (!data) return <div className="empty">Загрузка карты…</div>

  const W = data.map_width || 500
  const H = data.map_height || 400

  return (
    <div>
      <div
        className="map-board"
        style={{ aspectRatio: `${W} / ${H}` }}
      >
        {(data.warehouses || []).map((w) => (
          <div
            key={w.id}
            className="wh-box"
            style={{
              left: `${(w.map_x / W) * 100}%`,
              top: `${(w.map_y / H) * 100}%`,
            }}
          >
            {w.name}
          </div>
        ))}
        {(data.sensors || []).map((s) => (
          <div
            key={s.sensor_id}
            className={`sensor-dot ${s.map_color || 'green'}`}
            style={{
              left: `${(s.map_x / W) * 100}%`,
              top: `${(s.map_y / H) * 100}%`,
            }}
            title={s.name}
          >
            <span className="sensor-tip">
              {s.name}: {fmt(s.sensor_type, s.last_value)} [{s.status}]
            </span>
          </div>
        ))}
      </div>
      <div className="map-legend">
        зелёный — ок · серый — offline · красный мигает — тревога
      </div>
    </div>
  )
}

export function WatchInfo({ data }) {
  if (!data?.zones?.length) return null
  const hasFire = data.zones.some((z) => z.state === 'fire')
  const hasWatch = data.zones.some((z) => z.state === 'watch')
  const cls = hasFire ? 'fire' : hasWatch ? 'watch' : ''

  return (
    <div className={`watch-bar ${cls}`}>
      {data.zones.map((z) => {
        let t = `${z.name}: ${z.alarmed_count}/3 · ${z.state}`
        if (z.state === 'watch' && z.watch_remaining_sec != null) {
          t += ` (ещё ${z.watch_remaining_sec} с / ${data.confirm_seconds})`
        }
        return <div key={z.id}>{t}</div>
      })}
    </div>
  )
}
