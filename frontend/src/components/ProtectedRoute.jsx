import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export function ProtectedRoute({ role, children }) {
  const { auth } = useAuth()

  if (!auth) return <Navigate to="/login" replace />
  if (role && auth.role !== role) {
    return <Navigate to={auth.role === 'admin' ? '/admin' : '/trainer'} replace />
  }
  return children
}
