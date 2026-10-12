import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

const RANGES = {
  temperature: { min: 0, max: 120, step: 0.5, unit: '°C', def: 24 },
  oxygen: { min: 10, max: 25, step: 0.1, unit: '%', def: 20.9 },
  smoke: { min: 0, max: 100, step: 0.5, unit: '', def: 5 },
}

function fmt(type, v) {
  const u = (RANGES[type] || RANGES.temperature).unit
  if (v == null || Number.isNaN(Number(v))) return '—'
  return `${Number(v).toFixed(1)}${u ? ` ${u}` : ''}`
}

function hint(type, threshold) {
  return type === 'oxygen'
    ? `тревога если < ${threshold}`
    : `тревога если > ${threshold}`
}

function groupByWarehouse(data) {
  const groups = {}
  ;(data.warehouses || []).forEach((w) => {
    groups[w.id] = { warehouse: w, sensors: [] }
  })
  ;(data.sensors || []).forEach((s) => {
    if (!groups[s.warehouse_id]) {
      groups[s.warehouse_id] = {
        warehouse: { id: s.warehouse_id, name: s.warehouse_name },
        sensors: [],
      }
    }
    groups[s.warehouse_id].sensors.push(s)
  })
  return Object.values(groups)
}

export default function SensorPanels({ data, onChanged, readOnly = false }) {
  const [local, setLocal] = useState({})
  const dragging = useRef({})
  const timers = useRef({})

  useEffect(() => {
    if (!data?.sensors) return
    setLocal((prev) => {
      const next = { ...prev }
      data.sensors.forEach((s) => {
        if (dragging.current[s.ip]) return
        const range = RANGES[s.sensor_type] || RANGES.temperature
        next[s.ip] = {
          value: s.last_value != null ? s.last_value : range.def,
          online: s.status !== 'offline',
        }
      })
      return next
    })
  }, [data])

  if (!data) return null

  const send = (ip, value, online) => {
    if (timers.current[ip]) clearTimeout(timers.current[ip])
    timers.current[ip] = setTimeout(async () => {
      try {
        await api.ingest(ip, value, online)
        onChanged?.()
      } catch (e) {
        console.error(e)
      }
    }, 100)
  }

  const groups = groupByWarehouse(data)

  return (
    <div>
      {groups.map((g) => (
        <div className="wh-panel" key={g.warehouse.id}>
          <h3>{g.warehouse.name}</h3>
          {g.sensors.map((s) => {
            const range = RANGES[s.sensor_type] || RANGES.temperature
            const state = local[s.ip] || {
              value: range.def,
              online: true,
            }
            const statusClass =
              s.status === 'alarm' ? 'alarm' : s.status === 'offline' ? 'offline' : 'ok'

            return (
              <div className="sensor-row" key={s.sensor_id}>
                <div className="sensor-head">
                  <span className="name">{s.name}</span>
                  <span className={`badge ${statusClass}`}>{s.status}</span>
                </div>
                <div className="sensor-meta">
                  {s.sensor_type} · {hint(s.sensor_type, s.threshold)}
                </div>
                {!readOnly && (
                  <div className="slider-line">
                    <input
                      type="range"
                      min={range.min}
                      max={range.max}
                      step={range.step}
                      value={state.value}
                      disabled={!state.online}
                      onMouseDown={() => { dragging.current[s.ip] = true; }}
                      onTouchStart={() => { dragging.current[s.ip] = true; }}
                      onMouseUp={() => { dragging.current[s.ip] = false; }}
                      onTouchEnd={() => { dragging.current[s.ip] = false; }}
                      onChange={(e) => {
                        const value = Number(e.target.value)
                        setLocal((prev) => ({
                          ...prev,
                          [s.ip]: { ...state, value },
                        }))
                        send(s.ip, value, true)
                      }}
                    />
                    <span className="val-box">{fmt(s.sensor_type, state.value)}</span>
                    <label className="offline-label">
                      <input
                        type="checkbox"
                        checked={!state.online}
                        onChange={(e) => {
                          const online = !e.target.checked
                          setLocal((prev) => ({
                            ...prev,
                            [s.ip]: { ...state, online },
                          }))
                          send(s.ip, state.value, online)
                        }}
                      />
                      offline
                    </label>
                  </div>
                )}
                {readOnly && (
                  <div className="val-box" style={{ textAlign: 'left' }}>
                    {fmt(s.sensor_type, s.last_value)}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
