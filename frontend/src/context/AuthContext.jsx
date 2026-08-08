import { useEffect, useState } from 'react'
import { login as apiLogin, logout as apiLogout } from '../api/client'
import { AuthContext } from './auth-context-object'

const STORAGE_KEY = 'attendance_auth'

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored ? JSON.parse(stored) : null
  })

  useEffect(() => {
    if (auth) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(auth))
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  }, [auth])

  async function login(username, password) {
    const data = await apiLogin(username, password)
    setAuth(data)
    return data
  }

  async function logout() {
    if (auth?.token) {
      try {
        await apiLogout(auth.token)
      } catch {
        // token may already be invalid server-side — clear local state anyway
      }
    }
    setAuth(null)
  }

  // Swaps in a freshly-rotated token (see ChangePasswordView) without a full
  // re-login — the backend deletes the old token as part of changing the
  // password, so the copy already in localStorage would otherwise start
  // failing every request right after a successful change.
  function updateToken(token) {
    setAuth((prev) => (prev ? { ...prev, token } : prev))
  }

  return (
    <AuthContext.Provider value={{ auth, login, logout, updateToken }}>
      {children}
    </AuthContext.Provider>
  )
}
