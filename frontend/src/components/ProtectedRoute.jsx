import { Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { roleHome } from '../utils/roleHome'

export function ProtectedRoute({ role, children }) {
  const { auth } = useAuth()

  if (!auth) return <Navigate to="/login" replace />
  if (role && auth.role !== role) {
    return <Navigate to={roleHome(auth.role)} replace />
  }
  return children
}
