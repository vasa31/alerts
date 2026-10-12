import { useAuth } from '../AuthContext'

export default function AppShell({ title, subtitle, children, actions }) {
  const { user, logout } = useAuth()
  const role = user?.role || ''

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-brand">
          <div className="mark" aria-hidden><i /></div>
          <div>
            <strong>Monitor</strong>
            <div className="muted" style={{ fontSize: '0.78rem' }}>
              {user?.username}
              {' · '}
              <span className={`role-pill ${role}`}>
                {role === 'duty' ? 'дежурный' : 'администратор'}
              </span>
            </div>
          </div>
        </div>
        <div className="topbar-actions">
          {actions}
          <button type="button" className="btn btn-ghost btn-sm" onClick={logout}>
            Выйти
          </button>
        </div>
      </header>
      <main className="content">
        <div className="page-head">
          <div>
            <h1>{title}</h1>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
        </div>
        {children}
      </main>
    </div>
  )
}
