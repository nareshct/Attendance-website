import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, apiRequest } from '../api/client'
import { useAuth } from './useAuth'

// DRF's exact default message when an authenticated request fails a
// permission_classes check (see config/permissions.py's IsAdmin/IsTrainer/
// IsAdminOrTrainer, none of which override BasePermission.message) — this is
// the one signal that actually means "your role/session is stale," e.g. an
// admin's is_staff flag was revoked mid-session. Other 403s in this app are
// business-logic rejections from a still-valid, still-correctly-scoped user
// (e.g. "This class falls in a closed billing cycle," "You can only download
// reports for your own students," "You're not listed as a trainer on this
// batch.") and must NOT log the user out — only this exact message should.
const PERMISSION_DENIED_MESSAGE = 'You do not have permission to perform this action.'

export function useApi() {
  const { auth, logout } = useAuth()
  const navigate = useNavigate()

  return useCallback(
    async (path, options = {}) => {
      try {
        return await apiRequest(path, { ...options, token: auth?.token })
      } catch (err) {
        if (err instanceof ApiError) {
          const isStaleSession = err.status === 401 || (err.status === 403 && err.message === PERMISSION_DENIED_MESSAGE)
          if (isStaleSession) {
            await logout()
            navigate('/login')
          }
        }
        throw err
      }
    },
    [auth, logout, navigate],
  )
}
