import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { Badge } from '../../components/Badge'
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

  if (error) return <p className="text-red-600 text-sm">{error}</p>
  if (!trainer) return <p className="text-gray-400 text-sm">Loading…</p>

  const ratedCourseIds = new Set(trainer.course_rates.map((r) => r.course))
  const availableCourses = courses.filter((c) => !ratedCourseIds.has(c.id))

  const lastCycleStart = lastCycleBoundsFor(new Date()).start
  const visibleAttendance = attendance
    .filter((a) => a.date >= lastCycleStart)
    .sort((a, b) => b.date.localeCompare(a.date))

  return (
    <div>
      <Link to={backTo} className="text-sm text-brand-blue hover:underline">&larr; {backLabel}</Link>

      <div className="flex flex-wrap items-center justify-between gap-3 mt-3 mb-6">
        <h1 className="text-2xl font-semibold text-navy">{trainer.name}</h1>
        <div className="flex flex-wrap items-center gap-3">
          <Badge status={trainer.status} />
          {!editingProfile && (
            <button onClick={openEditProfile} className="text-sm rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800">
              Edit details
            </button>
          )}
        </div>
      </div>

      <Card className="mb-6">
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm mb-4">
          <div><dt className="text-gray-500">Trainer ID</dt><dd className="font-mono">{trainer.trainer_id}</dd></div>
          <div>
            <dt className="text-gray-500">Phone</dt>
            <dd>{trainer.phone_number}</dd>
          </div>
          <div><dt className="text-gray-500">Place</dt><dd>{trainer.place}</dd></div>
          <div>
            <dt className="text-gray-500">Default rate per class</dt>
            <dd>{trainer.default_rate_per_class != null ? `₹${trainer.default_rate_per_class}` : '—'}</dd>
          </div>
        </dl>

        {trainer.course_rates.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <h3 className="text-sm font-semibold text-navy mb-2">Course-specific overrides</h3>
            <ul className="space-y-2">
              {trainer.course_rates.map((r) => (
                <li key={r.id} className="text-sm">
                  {r.course_name} <span className="text-gray-500">· ₹{r.rate_per_class}</span>
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
          className="mt-4 pt-4 border-t border-gray-100 block text-xs text-brand-blue hover:underline"
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
            {resetError && <p className="text-xs text-red-600">{resetError}</p>}
            {resetSuccess && <p className="text-xs text-brand-green">Password reset successfully.</p>}
            <button
              disabled={resetting}
              type="submit"
              className="rounded-lg bg-brand-blue text-white px-4 py-1.5 text-sm hover:bg-blue-800 disabled:opacity-60"
            >
              {resetting ? 'Saving…' : 'Save new password'}
            </button>
          </form>
        )}
      </Card>

      <Modal open={editingProfile} onClose={closeEditProfile} title="Edit trainer details" maxWidthClass="max-w-2xl">
        <form onSubmit={handleSaveProfile} className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4 pb-4 border-b border-gray-100">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Name</label>
            <input required value={profileForm?.name ?? ''} onChange={(e) => setProfileForm({ ...profileForm, name: e.target.value })} className="input" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Phone</label>
            <input required value={profileForm?.phone_number ?? ''} onChange={(e) => setProfileForm({ ...profileForm, phone_number: e.target.value })} className="input" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Place</label>
            <input required value={profileForm?.place ?? ''} onChange={(e) => setProfileForm({ ...profileForm, place: e.target.value })} className="input" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Default rate per class (₹)</label>
            <input
              required
              type="number"
              step="0.01"
              value={profileForm?.default_rate_per_class ?? ''}
              onChange={(e) => setProfileForm({ ...profileForm, default_rate_per_class: e.target.value })}
              className="input"
            />
          </div>
          {profileError && <p className="sm:col-span-3 text-red-600 text-xs">{profileError}</p>}
          <div className="sm:col-span-3 flex justify-end gap-3">
            <button type="button" onClick={closeEditProfile} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button disabled={savingProfile} type="submit" className="text-sm text-brand-green hover:underline disabled:opacity-60">
              {savingProfile ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>

        <div>
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-semibold text-navy">Course-specific overrides</h3>
            <button type="button" onClick={() => setShowRateForm((v) => !v)} className="text-xs text-brand-blue hover:underline">
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
              <button disabled={submitting} type="submit" className="rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800 disabled:opacity-60">
                {submitting ? 'Saving…' : 'Save rate'}
              </button>
            </form>
          )}

          {trainer.course_rates.length > 0 ? (
            <ul className="space-y-2">
              {trainer.course_rates.map((r) => (
                <li key={r.id} className="flex items-center justify-between text-sm">
                  <span>{r.course_name} <span className="text-gray-500">· ₹{r.rate_per_class}</span></span>
                  <button
                    disabled={deletingRateId === r.id}
                    onClick={() => setRateDeleteTarget(r.id)}
                    className="text-xs text-red-600 hover:underline disabled:opacity-60"
                  >
                    {deletingRateId === r.id ? 'Deleting…' : 'Delete'}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400">No overrides — every course uses the default rate.</p>
          )}
        </div>
      </Modal>

      <h2 className="text-lg font-semibold text-navy mb-3">Weekly class schedule</h2>
      <Card className="p-0 overflow-x-auto mb-6">
        <WeeklyScheduleGrid enrollments={enrollments} />
      </Card>

      <h2 className="text-lg font-semibold text-navy mb-1">Recent attendance</h2>
      <p className="text-xs text-gray-400 mb-3">Showing the current and last billing cycle only.</p>
      <Card className="p-0 overflow-x-auto mb-6">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-left">
            <tr>
              <th className="px-4 py-3">Date</th>
              <th className="px-4 py-3">Student</th>
              <th className="px-4 py-3">Course</th>
              <th className="px-4 py-3">Topic</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {visibleAttendance.map((a) => (
              <tr key={a.id} className="border-t border-gray-100">
                <td className="px-4 py-3">{formatDate(a.date)}</td>
                <td className="px-4 py-3">{a.student_name}</td>
                <td className="px-4 py-3">{a.course_name}</td>
                <td className="px-4 py-3 text-gray-500">{a.topic_covered || '—'}</td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  {a.in_closed_cycle ? (
                    <span className="text-xs text-gray-400">Locked</span>
                  ) : (
                    <button onClick={() => openDeleteAttendance(a.id)} className="text-xs text-red-600 hover:underline">
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {visibleAttendance.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-gray-400">No attendance in the current or last billing cycle.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <h2 className="text-lg font-semibold text-navy mb-3">Payout history</h2>
      <Card className="p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-left">
            <tr>
              <th className="px-4 py-3">Cycle</th>
              <th className="px-4 py-3">Classes</th>
              <th className="px-4 py-3">Amount</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {currentCycle && (
              <tr className="border-t border-gray-100 bg-gray-50/50">
                <td className="px-4 py-3">{formatDateRange(currentCycle.cycle_start, currentCycle.cycle_end)}</td>
                <td className="px-4 py-3">
                  {currentCycle.total_classes}
                  {currentCycle.carried_forward_count > 0 && (
                    <div className="text-xs text-brand-amber">
                      incl. ₹{currentCycle.carried_forward_amount} from {currentCycle.carried_forward_count} late-approved class{currentCycle.carried_forward_count === 1 ? '' : 'es'}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3">
                  ₹{currentCycle.total_amount}
                  {currentCycle.carried_forward_count > 0 && (
                    <div className="text-xs text-brand-amber">
                      incl. ₹{currentCycle.carried_forward_amount} from {currentCycle.carried_forward_count} late-approved class{currentCycle.carried_forward_count === 1 ? '' : 'es'}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3"><Badge status="open" /></td>
              </tr>
            )}
            {payouts.map((p) => (
              <tr key={p.id} className="border-t border-gray-100">
                <td className="px-4 py-3">{formatDateRange(p.cycle_start, p.cycle_end)}</td>
                <td className="px-4 py-3">{p.total_classes}</td>
                <td className="px-4 py-3">
                  ₹{p.total_amount}
                  {Number(p.carried_forward_amount) > 0 && (
                    <div className="text-xs text-gray-400">(incl. ₹{p.carried_forward_amount} carried forward)</div>
                  )}
                </td>
                <td className="px-4 py-3"><Badge status={p.paid_status} /></td>
              </tr>
            ))}
            {payouts.length === 0 && !currentCycle && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-gray-400">No payouts yet.</td></tr>
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
