import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'

export default function Login() {
  const { login, isAuthed, user } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (isAuthed) {
    return <Navigate to={user?.role === 'admin' ? '/admin' : '/duty'} replace />
  }

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const u = await login(username.trim(), password)
      navigate(u.role === 'admin' ? '/admin' : '/duty', { replace: true })
    } catch (err) {
      setError(err.message || 'Не удалось войти')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={onSubmit}>
        <div className="brand-mark" aria-hidden><span /></div>
        <h1>Monitor</h1>
        <p className="lead">
          Единый вход для дежурного и администратора.
          Мониторинг складов и пожарных датчиков.
        </p>

        <div className="field">
          <label htmlFor="username">Логин</label>
          <input
            id="username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="duty или admin"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">Пароль</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••"
            required
          />
        </div>

        <button className="btn btn-primary" type="submit" disabled={loading}>
          {loading ? 'Вход…' : 'Войти'}
        </button>

        {error ? <div className="error-box">{error}</div> : null}

        <div className="login-hint">
          Демо: <code>duty / duty</code> — карта и тревоги ·{' '}
          <code>admin / admin</code> — обзор и статистика
        </div>
      </form>
    </div>
  )
}
