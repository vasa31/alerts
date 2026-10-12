export default function StatsCards({ stats }) {
  if (!stats) return <div className="empty">Нет статистики</div>

  const cards = [
    { label: 'Сигналы пожара', value: stats.total_fire_signals },
    { label: 'Подтверждённые', value: stats.confirmed_fires },
    { label: 'Ложные', value: stats.false_alarms },
    { label: 'Доля ложных, %', value: stats.false_alarm_rate },
  ]

  return (
    <div className="stats-grid">
      {cards.map((c) => (
        <div className="stat-card" key={c.label}>
          <div className="label">{c.label}</div>
          <div className="value">{c.value}</div>
        </div>
      ))}
    </div>
  )
}
