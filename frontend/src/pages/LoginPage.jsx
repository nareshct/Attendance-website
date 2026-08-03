import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { requestPasswordReset } from '../api/client'
import { useAuth } from '../context/AuthContext'

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
          <p className="text-sm text-gray-500 mb-6">
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
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue focus:border-brand-blue"
              />
            </div>

            {resetError && <p className="text-sm text-red-600">{resetError}</p>}
            {resetMessage && <p className="text-sm text-brand-green">{resetMessage}</p>}

            <button
              type="submit"
              disabled={resetSubmitting}
              className="w-full rounded-lg bg-brand-blue text-white font-medium py-2 hover:bg-blue-800 transition-colors disabled:opacity-60"
            >
              {resetSubmitting ? 'Sending…' : 'Send reset link'}
            </button>
          </form>

          <button
            type="button"
            onClick={() => {
              setShowForgot(false)
              setResetError('')
              setResetMessage('')
            }}
            className="text-xs text-gray-400 hover:text-brand-blue mt-6 block mx-auto"
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
        <p className="text-sm text-gray-500 mb-6">Sign in to manage attendance and payouts</p>

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
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue focus:border-brand-blue"
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
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue focus:border-brand-blue"
            />
            <button
              type="button"
              onClick={() => setShowForgot(true)}
              className="text-xs text-brand-blue hover:underline mt-1"
            >
              Forgot password?
            </button>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-brand-blue text-white font-medium py-2 hover:bg-blue-800 transition-colors disabled:opacity-60"
          >
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="text-xs text-gray-400 mt-6 text-center">
          Admins and trainers use the same sign-in — you'll land on the right dashboard automatically.
        </p>
      </div>
    </div>
  )
}
