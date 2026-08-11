import { useCallback, useEffect, useState } from 'react'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { Modal } from '../../components/Modal'
import { SearchableSelect } from '../../components/SearchableSelect'
import { useApi } from '../../hooks/useApi'
import { formatDate } from '../../utils/date'

const today = () => new Date().toISOString().slice(0, 10)

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

export default function MarkAttendancePage() {
  const api = useApi()
  const [enrollments, setEnrollments] = useState([])
  const [history, setHistory] = useState([])
  const [requests, setRequests] = useState([])
  const [form, setForm] = useState({ enrollment: '', date: today(), topic_covered: '' })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [submitting, setSubmitting] = useState(false)
  // Set when the backend blocks a create with 409 (a class is already marked for this
  // student/date) — offers the trainer a way to say "this is genuinely a second class
  // today" instead of just being stuck. See AttendanceViewSet.create().
  const [duplicateConfirmPending, setDuplicateConfirmPending] = useState(false)

  const [editingId, setEditingId] = useState(null)
  const [editDate, setEditDate] = useState('')
  const [editTopic, setEditTopic] = useState('')
  const [editError, setEditError] = useState('')
  const [editSaving, setEditSaving] = useState(false)

  const [deletingId, setDeletingId] = useState(null)
  const [deleteError, setDeleteError] = useState('')
  const [deleting, setDeleting] = useState(false)

  const loadHistory = useCallback(async () => {
    // Bounded to the current + last billing cycle — this page only ever shows that
    // window anyway (see visibleHistory below). Fetching a trainer's entire history
    // unbounded broke outright once their lifetime total passed the API's page size
    // (see api/client.js's unwrapPaginated) — this can never grow past ~2 cycles' worth.
    const start = lastCycleBoundsFor(new Date()).start
    setHistory(await api(`/api/attendance/?start=${start}`))
  }, [api])

  const lastCycleStart = lastCycleBoundsFor(new Date()).start
  const visibleHistory = history.filter((h) => h.date >= lastCycleStart)

  // Denied requests never become an Attendance row, so they'd otherwise vanish
  // from view entirely once no other request is still pending. Folding them
  // into Recent attendance (by date, alongside real classes) keeps a trainer
  // from assuming a denied class was actually recorded.
  const deniedRecent = requests
    .filter((r) => r.status === 'denied' && r.date >= lastCycleStart)
    .map((r) => ({ id: `denied-${r.id}`, denied: true, date: r.date, student_name: r.student_name, course_name: r.course_name, topic_covered: r.topic_covered }))
  const combinedHistory = [...visibleHistory, ...deniedRecent].sort((a, b) => b.date.localeCompare(a.date))

  const loadRequests = useCallback(async () => {
    setRequests(await api('/api/attendance-requests/'))
  }, [api])

  useEffect(() => {
    api('/api/my-students/').then((e) => setEnrollments(e.filter((x) => x.status === 'ongoing' && !x.payment_blocked))).catch((err) => setError(err.message))
    loadHistory().catch((err) => setError(err.message))
    loadRequests().catch((err) => setError(err.message))
  }, [api, loadHistory, loadRequests])

  async function submitAttendance(confirmDuplicate) {
    setSubmitting(true)
    setError('')
    setSuccess('')
    try {
      const result = await api('/api/attendance/', {
        method: 'POST',
        body: { ...form, enrollment: Number(form.enrollment), status: 'present', confirm_duplicate: confirmDuplicate },
      })
      setDuplicateConfirmPending(false)
      if (result && result.pending_approval) {
        setSuccess(result.detail)
        await loadRequests()
      } else {
        setSuccess('Class marked as taken.')
        await loadHistory()
      }
      setForm({ enrollment: '', date: today(), topic_covered: '' })
    } catch (err) {
      if (err.status === 409) {
        setDuplicateConfirmPending(true)
      } else {
        setDuplicateConfirmPending(false)
      }
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    submitAttendance(false)
  }

  function confirmSecondClass() {
    submitAttendance(true)
  }

  function openEdit(h) {
    setEditingId(h.id)
    setEditDate(h.date)
    setEditTopic(h.topic_covered)
    setEditError('')
  }

  function closeEdit() {
    setEditingId(null)
    setEditDate('')
    setEditTopic('')
    setEditError('')
  }

  async function saveEdit() {
    if (!editTopic.trim()) {
      setEditError('Topic covered is required.')
      return
    }
    setEditSaving(true)
    setEditError('')
    try {
      await api(`/api/attendance/${editingId}/`, { method: 'PATCH', body: { date: editDate, topic_covered: editTopic } })
      closeEdit()
      await loadHistory()
    } catch (err) {
      setEditError(err.message)
    } finally {
      setEditSaving(false)
    }
  }

  function openDelete(id) {
    setDeletingId(id)
    setDeleteError('')
  }

  function closeDelete() {
    setDeletingId(null)
    setDeleteError('')
  }

  async function confirmDelete() {
    setDeleting(true)
    setDeleteError('')
    try {
      await api(`/api/attendance/${deletingId}/`, { method: 'DELETE' })
      setDeletingId(null)
      await loadHistory()
    } catch (err) {
      setDeleteError(err.message)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">Mark Attendance</h1>

      <Card className="mb-8 max-w-xl">
        <form onSubmit={handleSubmit} className="space-y-3">
          <SearchableSelect
            required
            placeholder="Search student…"
            value={form.enrollment}
            onChange={(v) => { setForm({ ...form, enrollment: v }); setDuplicateConfirmPending(false) }}
            options={enrollments.map((en) => ({
              value: en.id,
              label: `${en.student_name} — ${en.course_name} (Batch ${en.batch_number})${en.covering_for ? ` · Covering for ${en.covering_for}` : ''}`,
            }))}
          />

          <input
            required
            type="date"
            value={form.date}
            onChange={(e) => { setForm({ ...form, date: e.target.value }); setDuplicateConfirmPending(false) }}
            className="input"
          />

          <p className="text-xs text-text-secondary">
            Only mark a class if you actually taught it. If a student didn't attend, just don't mark that date — there's no separate "absent" entry to make.
          </p>

          <textarea
            required
            placeholder="Topic covered in this session…"
            value={form.topic_covered}
            onChange={(e) => setForm({ ...form, topic_covered: e.target.value })}
            className="input"
            rows={3}
          />

          {error && <p className="text-error text-sm">{error}</p>}
          {success && <p className="text-success text-sm">{success}</p>}

          {duplicateConfirmPending ? (
            <div className="flex flex-wrap items-center gap-3">
              <Button type="button" variant="ghost" size="lg" disabled={submitting} onClick={confirmSecondClass}>
                {submitting ? 'Sending…' : 'Yes, this is a genuine second class — send to admin'}
              </Button>
              <Button type="submit" size="lg" disabled={submitting}>
                {submitting ? 'Saving…' : 'Mark class taken'}
              </Button>
            </div>
          ) : (
            <Button type="submit" size="lg" disabled={submitting}>
              {submitting ? 'Saving…' : 'Mark class taken'}
            </Button>
          )}
        </form>
      </Card>

      {requests.some((r) => r.status === 'pending') && (
        <>
          <h2 className="text-lg font-semibold text-navy mb-3">Approval requests</h2>
          <Card className="p-0 overflow-x-auto mb-8">
            <table className="table">
              <thead className="table-head-row">
                <tr>
                  <th className="table-head-cell">Date</th>
                  <th className="table-head-cell">Student</th>
                  <th className="table-head-cell">Course</th>
                  <th className="table-head-cell">Topic</th>
                  <th className="table-head-cell">Reason</th>
                  <th className="table-head-cell">Status</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((r) => (
                  <tr key={r.id} className="table-row">
                    <td className="table-cell">{formatDate(r.date)}</td>
                    <td className="table-cell">{r.student_name}</td>
                    <td className="table-cell">{r.course_name}</td>
                    <td className="table-cell text-text-secondary">{r.topic_covered || '—'}</td>
                    <td className="table-cell text-text-secondary">
                      {r.request_type === 'duplicate_day' ? 'Second class same day' : 'Late entry'}
                    </td>
                    <td className="table-cell"><Badge status={r.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}

      <h2 className="text-lg font-semibold text-navy mb-1">Recent attendance</h2>
      <p className="text-xs text-text-tertiary mb-3">Showing the current and last billing cycle only.</p>
      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">#</th>
              <th className="table-head-cell">Date</th>
              <th className="table-head-cell">Student</th>
              <th className="table-head-cell">Course</th>
              <th className="table-head-cell">Topic</th>
              <th className="table-head-cell"></th>
            </tr>
          </thead>
          <tbody>
            {combinedHistory.map((h, i) => (
              <tr key={h.id} className={`table-row align-top ${h.denied ? 'opacity-60' : ''}`}>
                <td className="table-cell text-text-tertiary">{i + 1}</td>
                <td className="table-cell">{formatDate(h.date)}</td>
                <td className="table-cell">{h.student_name}</td>
                <td className="table-cell">{h.course_name}</td>
                <td className="table-cell text-text-secondary">{h.topic_covered || '—'}</td>
                <td className="table-cell whitespace-nowrap">
                  {h.denied ? (
                    <Badge status="denied" />
                  ) : h.in_closed_cycle ? (
                    h.approved_via_request ? (
                      <Badge status="approved" />
                    ) : (
                      <span className="text-xs text-text-secondary">Locked</span>
                    )
                  ) : (
                    <div className="space-x-3">
                      <button
                        onClick={() => openEdit(h)}
                        className="rounded text-xs font-medium text-primary transition-colors duration-150 ease-out hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => openDelete(h.id)}
                        className="rounded text-xs font-medium text-error transition-colors duration-150 ease-out hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-error focus-visible:ring-offset-2"
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {combinedHistory.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-text-tertiary">No attendance marked in the current or last billing cycle.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal open={editingId != null} onClose={closeEdit} title="Edit attendance record">
        <div className="space-y-3">
          <input type="date" value={editDate} onChange={(e) => setEditDate(e.target.value)} className="input" />
          <textarea
            placeholder="Topic covered in this session…"
            value={editTopic}
            onChange={(e) => setEditTopic(e.target.value)}
            className="input"
            rows={3}
          />
          {editError && <p className="text-error text-sm">{editError}</p>}
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={closeEdit}>
              Cancel
            </Button>
            <Button type="button" variant="success" disabled={editSaving} onClick={saveEdit}>
              {editSaving ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={deletingId != null}
        onClose={closeDelete}
        onConfirm={confirmDelete}
        title="Delete attendance record"
        message="Delete this attendance record? This cannot be undone."
        confirmLabel="Delete"
        busyLabel="Deleting…"
        danger
        busy={deleting}
        error={deleteError}
      />
    </div>
  )
}
