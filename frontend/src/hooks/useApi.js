import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, apiRequest } from '../api/client'
import { useAuth } from './useAuth'

export function useApi() {
  const { auth, logout } = useAuth()
  const navigate = useNavigate()

  return useCallback(
    async (path, options = {}) => {
      try {
        return await apiRequest(path, { ...options, token: auth?.token })
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          await logout()
          navigate('/login')
        }
        throw err
      }
    },
    [auth, logout, navigate],
  )
}
