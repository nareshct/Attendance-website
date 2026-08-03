import { createContext, useContext, useEffect, useState } from 'react'
import { login as apiLogin, logout as apiLogout } from '../api/client'

const AuthContext = createContext(null)
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

  return (
    <AuthContext.Provider value={{ auth, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
