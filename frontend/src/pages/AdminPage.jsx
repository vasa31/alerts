import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../AuthContext'
import AppShell from '../components/AppShell'
import EventsPanel from '../components/EventsPanel'
import SensorPanels from '../components/SensorPanels'
import StatsCards from '../components/StatsCards'
import WarehouseMap, { WatchInfo } from '../components/WarehouseMap'

export default function AdminPage() {
  const { token } = useAuth()
  const [map, setMap] = useState(null)
  const [stats, setStats] = useState(null)
  const [events, setEvents] = useState([])
  const [notes, setNotes] = useState([])
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [m, s, e, n] = await Promise.all([
        api.map(token),
        api.stats(token),
        api.events(token),
        api.notifications(token, 'fire_dept'),
      ])
      setMap(m)
      setStats(s)
      setEvents(e)
      setNotes(n)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [token])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 4000)
    return () => clearInterval(id)
  }, [refresh])

  return (
    <AppShell
      title="Кабинет администратора"
      subtitle="Обзор складов, датчиков и статистики ложных срабатываний"
      actions={
        <button type="button" className="btn btn-ghost btn-sm" onClick={refresh}>
          Обновить
        </button>
      }
    >
      {error ? <div className="error-box" style={{ marginBottom: 14 }}>{error}</div> : null}
      <WatchInfo data={map} />

      <div className="panel" style={{ marginBottom: 18 }}>
        <h2>Эффективность протокола</h2>
        <StatsCards stats={stats} />
      </div>

      <div className="grid-2">
        <div className="panel">
          <h2>Карта</h2>
          <WarehouseMap data={map} />
        </div>
        <div className="panel">
          <h2>Показания датчиков</h2>
          <p className="muted" style={{ marginTop: 0, marginBottom: 12, fontSize: '0.85rem' }}>
            Только просмотр. Управление имитацией — у дежурного.
          </p>
          <SensorPanels data={map} readOnly />
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 18 }}>
        <div className="panel">
          <h2>Вызовы в пожарную</h2>
          {notes.length === 0 ? (
            <div className="empty">Пока нет вызовов</div>
          ) : (
            <div className="list">
              {notes.map((n) => (
                <div className="list-item" key={n.id}>
                  <div className="title">{n.title}</div>
                  <div className="body">{n.body}</div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="panel">
          <h2>Журнал событий</h2>
          <EventsPanel items={events} />
        </div>
      </div>
    </AppShell>
  )
}
