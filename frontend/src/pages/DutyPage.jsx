import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../AuthContext'
import AppShell from '../components/AppShell'
import EventsPanel from '../components/EventsPanel'
import NotificationsPanel from '../components/NotificationsPanel'
import SensorPanels from '../components/SensorPanels'
import WarehouseMap, { WatchInfo } from '../components/WarehouseMap'

export default function DutyPage() {
  const { token } = useAuth()
  const [map, setMap] = useState(null)
  const [notes, setNotes] = useState([])
  const [events, setEvents] = useState([])
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [m, n, e] = await Promise.all([
        api.map(token),
        api.notifications(token),
        api.events(token),
      ])
      setMap(m)
      setNotes(n)
      setEvents(e)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [token])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 3000)
    return () => clearInterval(id)
  }, [refresh])

  async function resolve(resolution) {
    try {
      const open = events.find((e) => e.resolution === 'open')
      if (!open) {
        setError('Нет открытых событий')
        return
      }
      await api.resolve(token, open.id, resolution)
      await refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function forceWatch() {
    try {
      await api.watchCheck(token, true)
      await refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <AppShell
      title="Пульт дежурного"
      subtitle="Карта в реальном времени, имитация датчиков и подтверждение событий"
      actions={
        <>
          <button type="button" className="btn btn-ghost btn-sm" onClick={refresh}>
            Обновить
          </button>
          <button type="button" className="btn btn-ok btn-sm" onClick={() => resolve('confirmed_fire')}>
            Пожар был
          </button>
          <button type="button" className="btn btn-danger btn-sm" onClick={() => resolve('confirmed_false')}>
            Ложное
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={forceWatch}>
            Окно прошло
          </button>
        </>
      }
    >
      {error ? <div className="error-box" style={{ marginBottom: 14 }}>{error}</div> : null}
      <WatchInfo data={map} />

      <div className="grid-2">
        <div className="panel">
          <h2>Карта складов</h2>
          <WarehouseMap data={map} />
        </div>
        <div className="panel">
          <h2>Имитация датчиков</h2>
          <p className="muted" style={{ marginTop: 0, marginBottom: 12, fontSize: '0.85rem' }}>
            Ползунки шлют значения на бэкенд — оттуда загораются статусы и срабатывает логика 1/2/3.
          </p>
          <SensorPanels data={map} onChanged={refresh} />
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 18 }}>
        <div className="panel">
          <h2>Уведомления</h2>
          <NotificationsPanel items={notes} />
        </div>
        <div className="panel">
          <h2>События</h2>
          <EventsPanel items={events} />
        </div>
      </div>
    </AppShell>
  )
}
