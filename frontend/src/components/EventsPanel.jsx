export default function EventsPanel({ items = [] }) {
  if (!items.length) return <div className="empty">Нет событий</div>

  return (
    <div className="list">
      {items.map((e) => (
        <div className="list-item" key={e.id}>
          <div className="title">
            #{e.id} · {e.event_type}
            <span className="muted" style={{ fontWeight: 500, marginLeft: 8 }}>
              {e.resolution}
            </span>
          </div>
          <div className="body">{e.message}</div>
        </div>
      ))}
    </div>
  )
}
