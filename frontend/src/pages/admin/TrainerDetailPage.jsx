import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { Modal } from '../../components/Modal'
import { WeeklyScheduleGrid } from '../../components/WeeklyScheduleGrid'
import { useApi } from '../../hooks/useApi'
import { formatDate, formatDateRange } from '../../utils/date'

function pad(n) {
  return String(n).padStart(2, '0')
}

function isoDate(y, m, d) {
  return `${y}-${pad(m + 1)}-${pad(d)}`
}

// Mirrors the backend's fixed 1st-15th / 16th-end-of-month billing cycle split.
function cycleBoundsFor(dateObj) {
  const y = dateObj.getFullYear()
  const m = dateObj.getMonth()
  const day = dateObj.getDate()
  if (day <= 15) return { start: isoDate(y, m, 1), end: isoDate(y, m, 15) }
  const lastDay = new Date(y, m + 1, 0).getDate()
  return { start: isoDate(y, m, 16), end: isoDate(y, m, lastDay) }
}

function lastCycleBoundsFor(dateObj) {
  const y = dateObj.getFullYear()
  const m = dateObj.getMonth()
  const day = dateObj.getDate()
  if (day <= 15) return cycleBoundsFor(new Date(y, m, 0)) // last day of previous month
  return { start: isoDate(y, m, 1), end: isoDate(y, m, 15) }
}

export default function TrainerDetailPage() {
  const { id } = useParams()
  const location = useLocation()
  const backTo = location.state?.from || '/admin/trainers'
  const backLabel = location.state?.fromLabel || 'Back to trainers'
  const api = useApi()
  const [trainer, setTrainer] = useState(null)
  const [payouts, setPayouts] = useState([])
  const [currentCycle, setCurrentCycle] = useState(null)
  const [courses, setCourses] = useState([])
  const [enrollments, setEnrollments] = useState([])
  const [attendance, setAttendance] = useState([])
  const [error, setError] = useState('')

  const [deletingAttendanceId, setDeletingAttendanceId] = useState(null)
  const [deletingAttendance, setDeletingAttendance] = useState(false)
  const [deleteAttendanceError, setDeleteAttendanceError] = useState('')
  const [showRateForm, setShowRateForm] = useState(false)
  const [rateForm, setRateForm] = useState({ course: '', rate_per_class: '' })
  const [submitting, setSubmitting] = useState(false)
  const [deletingRateId, setDeletingRateId] = useState(null)

  const [showResetForm, setShowResetForm] = useState(false)
  const [resetForm, setResetForm] = useState({ new_password: '', confirm_password: '' })
  const [resetError, setResetError] = useState('')
  const [resetSuccess, setResetSuccess] = useState(false)
  const [resetting, setResetting] = useState(false)

  const [editingProfile, setEditingProfile] = useState(false)
  const [profileForm, setProfileForm] = useState(null)
  const [profileError, setProfileError] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)

  const loadTrainer = useCallback(async () => {
    setTrainer(await api(`/api/trainers/${id}/`))
  }, [api, id])

  const loadCurrentCycle = useCallback(() => {
    return api(`/api/trainers/${id}/current-cycle/`).then(setCurrentCycle)
  }, [api, id])

  const loadAttendance = useCallback(() => {
    return api(`/api/attendance/?trainer=${id}`).then(setAttendance)
  }, [api, id])

  useEffect(() => {
    loadTrainer().catch((err) => setError(err.message))
    api(`/api/payouts/?trainer=${id}`).then(setPayouts).catch(() => {})
    api('/api/courses/').then(setCourses).catch(() => {})
    api(`/api/enrollments/?trainer=${id}`).then(setEnrollments).catch(() => {})
    loadCurrentCycle().catch(() => {})
    loadAttendance().catch(() => {})
  }, [api, id, loadTrainer, loadCurrentCycle, loadAttendance])

  function openDeleteAttendance(attendanceId) {
    setDeletingAttendanceId(attendanceId)
    setDeleteAttendanceError('')
  }

  function closeDeleteAttendance() {
    setDeletingAttendanceId(null)
    setDeleteAttendanceError('')
  }

  async function confirmDeleteAttendance() {
    const attendanceId = deletingAttendanceId
    setDeletingAttendance(true)
    setDeleteAttendanceError('')
    try {
      await api(`/api/attendance/${attendanceId}/`, { method: 'DELETE' })
      setAttendance((prev) => prev.filter((a) => a.id !== attendanceId))
      setDeletingAttendanceId(null)
      await loadCurrentCycle()
    } catch (err) {
      setDeleteAttendanceError(err.message)
    } finally {
      setDeletingAttendance(false)
    }
  }

  async function handleAddRate(e) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await api('/api/trainer-rates/', {
        method: 'POST',
        body: { trainer: Number(id), course: Number(rateForm.course), rate_per_class: rateForm.rate_per_class },
      })
      setRateForm({ course: '', rate_per_class: '' })
      setShowRateForm(false)
      await loadTrainer()
      await loadCurrentCycle()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const [rateDeleteTarget, setRateDeleteTarget] = useState(null)

  async function handleDeleteRate() {
    const rateId = rateDeleteTarget
    setDeletingRateId(rateId)
    setError('')
    try {
      await api(`/api/trainer-rates/${rateId}/`, { method: 'DELETE' })
      setRateDeleteTarget(null)
      await loadTrainer()
      await loadCurrentCycle()
    } catch (err) {
      setError(err.message)
    } finally {
      setDeletingRateId(null)
    }
  }

  function openEditProfile() {
    setProfileForm({
      name: trainer.name,
      phone_number: trainer.phone_number,
      place: trainer.place,
      default_rate_per_class: trainer.default_rate_per_class ?? '',
    })
    setProfileError('')
    setEditingProfile(true)
  }

  function closeEditProfile() {
    setEditingProfile(false)
    setProfileForm(null)
    setProfileError('')
    setShowRateForm(false)
    setRateForm({ course: '', rate_per_class: '' })
  }

  async function handleSaveProfile(e) {
    e.preventDefault()
    setSavingProfile(true)
    setProfileError('')
    try {
      await api(`/api/trainers/${id}/`, { method: 'PATCH', body: profileForm })
      closeEditProfile()
      await loadTrainer()
      await loadCurrentCycle()
    } catch (err) {
      setProfileError(err.message)
    } finally {
      setSavingProfile(false)
    }
  }

  async function handleResetPassword(e) {
    e.preventDefault()
    setResetError('')
    setResetSuccess(false)

    if (resetForm.new_password !== resetForm.confirm_password) {
      setResetError('New password and confirmation do not match.')
      return
    }

    setResetting(true)
    try {
      await api(`/api/trainers/${id}/reset-password/`, {
        method: 'POST',
        body: { new_password: resetForm.new_password },
      })
      setResetForm({ new_password: '', confirm_password: '' })
      setResetSuccess(true)
    } catch (err) {
      setResetError(err.message)
    } finally {
      setResetting(false)
    }
  }

  if (error) return <p className="text-error text-sm">{error}</p>
  if (!trainer) return <p className="text-text-tertiary text-sm">Loading…</p>

  const ratedCourseIds = new Set(trainer.course_rates.map((r) => r.course))
  const availableCourses = courses.filter((c) => !ratedCourseIds.has(c.id))

  const lastCycleStart = lastCycleBoundsFor(new Date()).start
  const visibleAttendance = attendance
    .filter((a) => a.date >= lastCycleStart)
    .sort((a, b) => b.date.localeCompare(a.date))

  return (
    <div>
      <Link to={backTo} className="text-sm font-medium text-primary hover:underline focus-ring">&larr; {backLabel}</Link>

      <div className="flex flex-wrap items-center justify-between gap-3 mt-3 mb-6">
        <h1 className="text-2xl font-semibold text-navy">{trainer.name}</h1>
        <div className="flex flex-wrap items-center gap-3">
          <Badge status={trainer.status} />
          {!editingProfile && <Button variant="success" onClick={openEditProfile}>Edit details</Button>}
        </div>
      </div>

      <Card className="mb-6">
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm mb-4">
          <div><dt className="text-text-secondary">Trainer ID</dt><dd className="font-mono">{trainer.trainer_id}</dd></div>
          <div>
            <dt className="text-text-secondary">Phone</dt>
            <dd>{trainer.phone_number}</dd>
          </div>
          <div><dt className="text-text-secondary">Place</dt><dd>{trainer.place}</dd></div>
          <div>
            <dt className="text-text-secondary">Default rate per class</dt>
            <dd>{trainer.default_rate_per_class != null ? `₹${trainer.default_rate_per_class}` : '—'}</dd>
          </div>
        </dl>

        {trainer.course_rates.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <h3 className="text-sm font-semibold text-navy mb-2">Course-specific overrides</h3>
            <ul className="space-y-2">
              {trainer.course_rates.map((r) => (
                <li key={r.id} className="text-sm">
                  {r.course_name} <span className="text-text-secondary">· ₹{r.rate_per_class}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <button
          onClick={() => {
            setShowResetForm((v) => !v)
            setResetError('')
            setResetSuccess(false)
          }}
          className="mt-4 pt-4 border-t border-gray-100 block text-xs font-medium text-primary hover:underline focus-ring"
        >
          {showResetForm ? 'Cancel' : 'Reset password'}
        </button>

        {showResetForm && (
          <form onSubmit={handleResetPassword} className="mt-3 pt-3 border-t border-gray-100 space-y-3 max-w-xs">
            <input
              required
              type="password"
              placeholder="New password"
              autoComplete="new-password"
              value={resetForm.new_password}
              onChange={(e) => setResetForm({ ...resetForm, new_password: e.target.value })}
              className="input"
            />
            <input
              required
              type="password"
              placeholder="Confirm new password"
              autoComplete="new-password"
              value={resetForm.confirm_password}
              onChange={(e) => setResetForm({ ...resetForm, confirm_password: e.target.value })}
              className="input"
            />
            {resetError && <p className="text-xs text-error">{resetError}</p>}
            {resetSuccess && <p className="text-xs text-success">Password reset successfully.</p>}
            <Button disabled={resetting} type="submit">
              {resetting ? 'Saving…' : 'Save new password'}
            </Button>
          </form>
        )}
      </Card>

      <Modal open={editingProfile} onClose={closeEditProfile} title="Edit trainer details" maxWidthClass="max-w-2xl">
        <form onSubmit={handleSaveProfile} className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4 pb-4 border-b border-gray-100">
          <div>
            <label className="block text-xs text-text-secondary mb-1">Name</label>
            <input required value={profileForm?.name ?? ''} onChange={(e) => setProfileForm({ ...profileForm, name: e.target.value })} className="input" />
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">Phone</label>
            <input required value={profileForm?.phone_number ?? ''} onChange={(e) => setProfileForm({ ...profileForm, phone_number: e.target.value })} className="input" />
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">Place</label>
            <input required value={profileForm?.place ?? ''} onChange={(e) => setProfileForm({ ...profileForm, place: e.target.value })} className="input" />
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">Default rate per class (₹)</label>
            <input
              required
              type="number"
              step="0.01"
              value={profileForm?.default_rate_per_class ?? ''}
              onChange={(e) => setProfileForm({ ...profileForm, default_rate_per_class: e.target.value })}
              className="input"
            />
          </div>
          {profileError && <p className="sm:col-span-3 text-error text-xs">{profileError}</p>}
          <div className="sm:col-span-3 flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={closeEditProfile}>
              Cancel
            </Button>
            <Button type="submit" variant="success" disabled={savingProfile}>
              {savingProfile ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </form>

        <div>
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-semibold text-navy">Course-specific overrides</h3>
            <button type="button" onClick={() => setShowRateForm((v) => !v)} className="text-xs font-medium text-primary hover:underline focus-ring">
              {showRateForm ? 'Cancel' : '+ Add override'}
            </button>
          </div>

          {showRateForm && (
            <form onSubmit={handleAddRate} className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
              <select required value={rateForm.course} onChange={(e) => setRateForm({ ...rateForm, course: e.target.value })} className="input">
                <option value="">Select course…</option>
                {availableCourses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <input required type="number" step="0.01" placeholder="Rate per class (₹)" value={rateForm.rate_per_class} onChange={(e) => setRateForm({ ...rateForm, rate_per_class: e.target.value })} className="input" />
              <Button disabled={submitting} type="submit" variant="success">
                {submitting ? 'Saving…' : 'Save rate'}
              </Button>
            </form>
          )}

          {trainer.course_rates.length > 0 ? (
            <ul className="space-y-2">
              {trainer.course_rates.map((r) => (
                <li key={r.id} className="flex items-center justify-between text-sm">
                  <span>{r.course_name} <span className="text-text-secondary">· ₹{r.rate_per_class}</span></span>
                  <button
                    disabled={deletingRateId === r.id}
                    onClick={() => setRateDeleteTarget(r.id)}
                    className="text-xs font-medium text-error hover:underline disabled:opacity-60 focus-ring"
                  >
                    {deletingRateId === r.id ? 'Deleting…' : 'Delete'}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-text-tertiary">No overrides — every course uses the default rate.</p>
          )}
        </div>
      </Modal>

      <h2 className="text-lg font-semibold text-navy mb-3">Weekly class schedule</h2>
      <Card className="p-0 overflow-x-auto mb-6">
        <WeeklyScheduleGrid enrollments={enrollments} />
      </Card>

      <h2 className="text-lg font-semibold text-navy mb-1">Recent attendance</h2>
      <p className="text-xs text-text-tertiary mb-3">Showing the current and last billing cycle only.</p>
      <Card className="p-0 overflow-x-auto mb-6">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">Date</th>
              <th className="table-head-cell">Student</th>
              <th className="table-head-cell">Course</th>
              <th className="table-head-cell">Topic</th>
              <th className="table-head-cell"></th>
            </tr>
          </thead>
          <tbody>
            {visibleAttendance.map((a) => (
              <tr key={a.id} className="table-row">
                <td className="table-cell">{formatDate(a.date)}</td>
                <td className="table-cell">{a.student_name}</td>
                <td className="table-cell">{a.course_name}</td>
                <td className="table-cell text-text-secondary">{a.topic_covered || '—'}</td>
                <td className="table-cell text-right whitespace-nowrap">
                  {a.in_closed_cycle ? (
                    <span className="text-xs text-text-secondary">Locked</span>
                  ) : (
                    <button onClick={() => openDeleteAttendance(a.id)} className="text-xs font-medium text-error hover:underline focus-ring">
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {visibleAttendance.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">No attendance in the current or last billing cycle.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <h2 className="text-lg font-semibold text-navy mb-3">Payout history</h2>
      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">Cycle</th>
              <th className="table-head-cell">Classes</th>
              <th className="table-head-cell">Amount</th>
              <th className="table-head-cell">Status</th>
            </tr>
          </thead>
          <tbody>
            {currentCycle && (
              <tr className="table-row bg-warning-tint/50">
                <td className="table-cell">{formatDateRange(currentCycle.cycle_start, currentCycle.cycle_end)}</td>
                <td className="table-cell tabular-nums">
                  {currentCycle.total_classes}
                  {currentCycle.carried_forward_count > 0 && (
                    <div className="text-xs text-warning">
                      incl. ₹{currentCycle.carried_forward_amount} from {currentCycle.carried_forward_count} late-approved class{currentCycle.carried_forward_count === 1 ? '' : 'es'}
                    </div>
                  )}
                </td>
                <td className="table-cell tabular-nums">
                  ₹{currentCycle.total_amount}
                  {currentCycle.carried_forward_count > 0 && (
                    <div className="text-xs text-warning">
                      incl. ₹{currentCycle.carried_forward_amount} from {currentCycle.carried_forward_count} late-approved class{currentCycle.carried_forward_count === 1 ? '' : 'es'}
                    </div>
                  )}
                </td>
                <td className="table-cell"><Badge status="open" /></td>
              </tr>
            )}
            {payouts.map((p) => (
              <tr key={p.id} className="table-row">
                <td className="table-cell">{formatDateRange(p.cycle_start, p.cycle_end)}</td>
                <td className="table-cell tabular-nums">{p.total_classes}</td>
                <td className="table-cell tabular-nums">
                  ₹{p.total_amount}
                  {Number(p.carried_forward_amount) > 0 && (
                    <div className="text-xs text-text-tertiary">(incl. ₹{p.carried_forward_amount} carried forward)</div>
                  )}
                </td>
                <td className="table-cell"><Badge status={p.paid_status} /></td>
              </tr>
            ))}
            {payouts.length === 0 && !currentCycle && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-text-tertiary">No payouts yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <ConfirmDialog
        open={deletingAttendanceId != null}
        onClose={closeDeleteAttendance}
        onConfirm={confirmDeleteAttendance}
        title="Delete attendance record"
        message="Delete this attendance record? This cannot be undone."
        confirmLabel="Delete"
        busyLabel="Deleting…"
        danger
        busy={deletingAttendance}
        error={deleteAttendanceError}
      />

      <ConfirmDialog
        open={rateDeleteTarget != null}
        onClose={() => setRateDeleteTarget(null)}
        onConfirm={handleDeleteRate}
        title="Delete rate override"
        message="Delete this course rate override? This trainer will fall back to their default rate for that course."
        confirmLabel="Delete"
        busyLabel="Deleting…"
        danger
        busy={deletingRateId === rateDeleteTarget}
      />
    </div>
  )
}
