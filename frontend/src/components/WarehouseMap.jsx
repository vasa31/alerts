const UNITS = {
  temperature: '°C',
  oxygen: '%',
  smoke: '',
}

/** Два больших склада на карте (доля от ширины/высоты доски). */
const FLOORS = [
  { left: 3, top: 6, width: 45, height: 88 },
  { left: 52, top: 6, width: 45, height: 88 },
]

/** Точки внутри склада (%, относительно пола склада). */
const SLOTS = [
  { x: 28, y: 32 },
  { x: 72, y: 48 },
  { x: 40, y: 72 },
  { x: 65, y: 28 },
  { x: 30, y: 55 },
  { x: 70, y: 75 },
]

function fmt(type, v) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  const u = UNITS[type] || ''
  return `${Number(v).toFixed(1)}${u ? ` ${u}` : ''}`
}

function placeSensorsInFloor(sensors, floor) {
  return sensors.map((s, i) => {
    const slot = SLOTS[i % SLOTS.length]
    return {
      ...s,
      leftPct: floor.left + (slot.x / 100) * floor.width,
      topPct: floor.top + (slot.y / 100) * floor.height,
    }
  })
}

export default function WarehouseMap({ data }) {
  if (!data) return <div className="empty">Загрузка карты…</div>

  const warehouses = data.warehouses || []
  const byWh = {}
  ;(data.sensors || []).forEach((s) => {
    const id = s.warehouse_id
    if (!byWh[id]) byWh[id] = []
    byWh[id].push(s)
  })

  const floors = warehouses.map((w, i) => {
    const floor = FLOORS[i] || FLOORS[FLOORS.length - 1]
    const sensors = placeSensorsInFloor(byWh[w.id] || [], floor)
    return { warehouse: w, floor, sensors }
  })

  return (
    <div>
      <div className="map-board map-board--yards">
        {floors.map(({ warehouse, floor, sensors }) => (
          <div
            key={warehouse.id}
            className="wh-floor"
            style={{
              left: `${floor.left}%`,
              top: `${floor.top}%`,
              width: `${floor.width}%`,
              height: `${floor.height}%`,
            }}
          >
            <div className="wh-floor-title">{warehouse.name}</div>
            {sensors.map((s) => (
              <div
                key={s.sensor_id}
                className={`sensor-dot ${s.map_color || 'green'}`}
                style={{
                  left: `${((s.leftPct - floor.left) / floor.width) * 100}%`,
                  top: `${((s.topPct - floor.top) / floor.height) * 100}%`,
                }}
                title={s.name}
              >
                <span className="sensor-tip">
                  {s.name}: {fmt(s.sensor_type, s.last_value)} [{s.status}]
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="map-legend">
        два склада · датчики внутри · зелёный — ок · серый — offline · красный — тревога
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
