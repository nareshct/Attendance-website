import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { requestPasswordReset } from '../api/client'
import { Button } from '../components/Button'
import { useAuth } from '../hooks/useAuth'
import { roleHome } from '../utils/roleHome'

export default function LoginPage() {
  const { auth, login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [showForgot, setShowForgot] = useState(false)
  const [resetUsername, setResetUsername] = useState('')
  const [resetMessage, setResetMessage] = useState('')
  const [resetError, setResetError] = useState('')
  const [resetSubmitting, setResetSubmitting] = useState(false)

  if (auth) {
    return <Navigate to={roleHome(auth.role)} replace />
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const data = await login(username, password)
      navigate(roleHome(data.role))
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleForgotSubmit(event) {
    event.preventDefault()
    setResetError('')
    setResetMessage('')
    setResetSubmitting(true)
    try {
      const result = await requestPasswordReset(resetUsername)
      setResetMessage(result.detail)
    } catch (err) {
      setResetError(err.message || 'Something went wrong. Try again.')
    } finally {
      setResetSubmitting(false)
    }
  }

  if (showForgot) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-navy px-4">
        <div className="w-full max-w-sm bg-white rounded-xl shadow-xl p-8">
          <h1 className="text-2xl font-semibold text-navy mb-1">Reset your password</h1>
          <p className="text-sm text-text-secondary mb-6">
            Enter your username and, if there's an email on file for it, we'll send a reset link.
          </p>

          <form onSubmit={handleForgotSubmit} className="space-y-4">
            <div>
              <label htmlFor="reset-username" className="block text-sm font-medium text-gray-700 mb-1">
                Username
              </label>
              <input
                id="reset-username"
                type="text"
                autoComplete="username"
                value={resetUsername}
                onChange={(e) => setResetUsername(e.target.value)}
                required
                className="input"
              />
            </div>

            {resetError && <p className="text-sm text-error">{resetError}</p>}
            {resetMessage && <p className="text-sm text-success">{resetMessage}</p>}

            <Button type="submit" disabled={resetSubmitting} className="w-full">
              {resetSubmitting ? 'Sending…' : 'Send reset link'}
            </Button>
          </form>

          <button
            type="button"
            onClick={() => {
              setShowForgot(false)
              setResetError('')
              setResetMessage('')
            }}
            className="text-xs text-text-secondary hover:text-primary mt-6 block mx-auto px-1 py-0.5 focus-ring"
          >
            &larr; Back to sign in
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-navy px-4">
      <div className="w-full max-w-sm bg-white rounded-xl shadow-xl p-8">
        <h1 className="text-2xl font-semibold text-navy mb-1">Apex Binary</h1>
        <p className="text-sm text-text-secondary mb-6">Sign in to manage attendance and payouts</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-1">
              Username
            </label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              className="input"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="input pr-10"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                className="absolute inset-y-0 right-0 flex items-center px-3 text-text-tertiary hover:text-navy focus-ring"
              >
                {showPassword ? (
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 0 0 1.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0 1 12 4.5c4.756 0 8.774 3.162 10.065 7.498a10.523 10.523 0 0 1-4.293 5.774M6.228 6.228 3 3m3.228 3.228 3.65 3.65m7.894 7.894L21 21m-3.228-3.228-3.65-3.65m0 0a3 3 0 1 0-4.243-4.243m4.242 4.242L9.88 9.88" />
                  </svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                  </svg>
                )}
              </button>
            </div>
            <button
              type="button"
              onClick={() => setShowForgot(true)}
              className="text-xs font-medium text-primary hover:underline mt-1.5 px-1 py-0.5 focus-ring"
            >
              Forgot password?
            </button>
          </div>

          {error && <p className="text-sm text-error">{error}</p>}

          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

      </div>
    </div>
  )
}
