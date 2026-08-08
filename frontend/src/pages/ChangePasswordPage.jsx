import { useEffect, useState } from 'react'
import { changePassword, getMe, updateEmail } from '../api/client'
import { Card } from '../components/Card'
import { useAuth } from '../hooks/useAuth'

export default function ChangePasswordPage() {
  const { auth, updateToken } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const [email, setEmail] = useState('')
  const [emailError, setEmailError] = useState('')
  const [emailSuccess, setEmailSuccess] = useState(false)
  const [savingEmail, setSavingEmail] = useState(false)

  useEffect(() => {
    getMe(auth.token).then((data) => setEmail(data.email)).catch((err) => setEmailError(err.message))
  }, [auth.token])

  async function handleSaveEmail(e) {
    e.preventDefault()
    setEmailError('')
    setEmailSuccess(false)
    setSavingEmail(true)
    try {
      const result = await updateEmail(auth.token, email)
      setEmail(result.email)
      setEmailSuccess(true)
    } catch (err) {
      setEmailError(err.message)
    } finally {
      setSavingEmail(false)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSuccess(false)

    if (newPassword !== confirmPassword) {
      setError('New password and confirmation do not match.')
      return
    }

    setSubmitting(true)
    try {
      const result = await changePassword(auth.token, currentPassword, newPassword)
      updateToken(result.token)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setSuccess(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">Account Settings</h1>

      <Card className="max-w-sm mb-6">
        <h2 className="text-sm font-semibold text-navy mb-1">Recovery email</h2>
        <p className="text-xs text-gray-500 mb-4">
          Used for "Forgot password?" — set this now so you're never locked out later.
        </p>
        <form onSubmit={handleSaveEmail} className="space-y-3">
          <input
            required
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input"
          />
          {emailError && <p className="text-sm text-red-600">{emailError}</p>}
          {emailSuccess && <p className="text-sm text-brand-green">Email saved.</p>}
          <button
            disabled={savingEmail}
            type="submit"
            className="w-full rounded-lg bg-brand-green text-white font-medium py-2 hover:bg-green-800 disabled:opacity-60"
          >
            {savingEmail ? 'Saving…' : 'Save email'}
          </button>
        </form>
      </Card>

      <h2 className="text-lg font-semibold text-navy mb-3">Change Password</h2>
      <Card className="max-w-sm">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Current password</label>
            <input
              required
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="input"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">New password</label>
            <input
              required
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="input"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Confirm new password</label>
            <input
              required
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="input"
            />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
          {success && <p className="text-sm text-brand-green">Password changed successfully.</p>}

          <button
            disabled={submitting}
            type="submit"
            className="w-full rounded-lg bg-brand-blue text-white font-medium py-2 hover:bg-blue-800 disabled:opacity-60"
          >
            {submitting ? 'Saving…' : 'Change password'}
          </button>
        </form>
      </Card>
    </div>
  )
}
