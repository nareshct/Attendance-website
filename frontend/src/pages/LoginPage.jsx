import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { requestPasswordReset } from '../api/client'
import { Button } from '../components/Button'
import { useAuth } from '../hooks/useAuth'

export default function LoginPage() {
  const { auth, login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [showForgot, setShowForgot] = useState(false)
  const [resetUsername, setResetUsername] = useState('')
  const [resetMessage, setResetMessage] = useState('')
  const [resetError, setResetError] = useState('')
  const [resetSubmitting, setResetSubmitting] = useState(false)

  if (auth) {
    return <Navigate to={auth.role === 'admin' ? '/admin' : '/trainer'} replace />
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const data = await login(username, password)
      navigate(data.role === 'admin' ? '/admin' : '/trainer')
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
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="input"
            />
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

        <p className="text-xs text-text-tertiary mt-6 text-center">
          Admins and trainers use the same sign-in — you'll land on the right dashboard automatically.
        </p>
      </div>
    </div>
  )
}
