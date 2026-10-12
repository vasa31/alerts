export default function NotificationsPanel({ items = [] }) {
  if (!items.length) return <div className="empty">Нет уведомлений</div>

  return (
    <div className="list">
      {items.map((n) => (
        <div className="list-item" key={n.id}>
          <div className="title">
            {n.title}
            <span className="muted" style={{ fontWeight: 500, marginLeft: 8 }}>
              {n.target} · {n.sound}
            </span>
          </div>
          <div className="body">{n.body}</div>
        </div>
      ))}
    </div>
  )
}
