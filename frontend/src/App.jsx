import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './AuthContext'
import AdminPage from './pages/AdminPage'
import DutyPage from './pages/DutyPage'
import Login from './pages/Login'

function RequireAuth({ role, children }) {
  const { isAuthed, user } = useAuth()
  if (!isAuthed) return <Navigate to="/login" replace />
  if (role && user?.role !== role) {
    return <Navigate to={user?.role === 'admin' ? '/admin' : '/duty'} replace />
  }
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/duty"
        element={(
          <RequireAuth role="duty">
            <DutyPage />
          </RequireAuth>
        )}
      />
      <Route
        path="/admin"
        element={(
          <RequireAuth role="admin">
            <AdminPage />
          </RequireAuth>
        )}
      />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
