import { useCallback, useEffect, useState } from 'react'
import { Badge } from '../../components/Badge'
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

  const [editingId, setEditingId] = useState(null)
  const [editDate, setEditDate] = useState('')
  const [editTopic, setEditTopic] = useState('')
  const [editError, setEditError] = useState('')
  const [editSaving, setEditSaving] = useState(false)

  const [deletingId, setDeletingId] = useState(null)
  const [deleteError, setDeleteError] = useState('')
  const [deleting, setDeleting] = useState(false)

  const loadHistory = useCallback(async () => {
    setHistory(await api('/api/attendance/'))
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
    loadHistory().catch(() => {})
    loadRequests().catch(() => {})
  }, [api, loadHistory, loadRequests])

  async function handleSubmit(e) {
    e.preventDefault()
    // Mirrors AttendanceSerializer.validate()'s duplicate check — only sees this
    // trainer's own visible history, so a class already marked by someone else
    // covering the same enrollment still falls through to the backend's own check.
    const alreadyMarked = history.some((h) => String(h.enrollment) === String(form.enrollment) && h.date === form.date)
    if (alreadyMarked) {
      setError('Attendance for this class on this date has already been marked.')
      return
    }

    setSubmitting(true)
    setError('')
    setSuccess('')
    try {
      const result = await api('/api/attendance/', {
        method: 'POST',
        body: { ...form, enrollment: Number(form.enrollment), status: 'present' },
      })
      if (result && result.pending_approval) {
        setSuccess('This date falls in a closed billing cycle — a request has been sent to admin for approval.')
        await loadRequests()
      } else {
        setSuccess('Class marked as taken.')
        await loadHistory()
      }
      setForm({ enrollment: '', date: today(), topic_covered: '' })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
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
            onChange={(v) => setForm({ ...form, enrollment: v })}
            options={enrollments.map((en) => ({
              value: en.id,
              label: `${en.student_name} — ${en.course_name} (Batch ${en.batch_number})${en.covering_for ? ` · Covering for ${en.covering_for}` : ''}`,
            }))}
          />

          <input required type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} className="input" />

          <p className="text-xs text-gray-500">
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

          {error && <p className="text-red-600 text-sm">{error}</p>}
          {success && <p className="text-brand-green text-sm">{success}</p>}

          <button disabled={submitting} type="submit" className="rounded-lg bg-brand-violet text-white px-4 py-2 hover:bg-violet-800 disabled:opacity-60">
            {submitting ? 'Saving…' : 'Mark class taken'}
          </button>
        </form>
      </Card>

      {requests.some((r) => r.status === 'pending') && (
        <>
          <h2 className="text-lg font-semibold text-navy mb-3">Approval requests</h2>
          <Card className="p-0 overflow-x-auto mb-8">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-left">
                <tr>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Student</th>
                  <th className="px-4 py-3">Course</th>
                  <th className="px-4 py-3">Topic</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((r) => (
                  <tr key={r.id} className="border-t border-gray-100">
                    <td className="px-4 py-3">{formatDate(r.date)}</td>
                    <td className="px-4 py-3">{r.student_name}</td>
                    <td className="px-4 py-3">{r.course_name}</td>
                    <td className="px-4 py-3 text-gray-500">{r.topic_covered || '—'}</td>
                    <td className="px-4 py-3"><Badge status={r.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}

      <h2 className="text-lg font-semibold text-navy mb-1">Recent attendance</h2>
      <p className="text-xs text-gray-400 mb-3">Showing the current and last billing cycle only.</p>
      <Card className="p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-left">
            <tr>
              <th className="px-4 py-3">#</th>
              <th className="px-4 py-3">Date</th>
              <th className="px-4 py-3">Student</th>
              <th className="px-4 py-3">Course</th>
              <th className="px-4 py-3">Topic</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {combinedHistory.map((h, i) => (
              <tr key={h.id} className={`border-t border-gray-100 align-top ${h.denied ? 'opacity-60' : ''}`}>
                <td className="px-4 py-3 text-gray-400">{i + 1}</td>
                <td className="px-4 py-3">{formatDate(h.date)}</td>
                <td className="px-4 py-3">{h.student_name}</td>
                <td className="px-4 py-3">{h.course_name}</td>
                <td className="px-4 py-3 text-gray-500">{h.topic_covered || '—'}</td>
                <td className="px-4 py-3 whitespace-nowrap">
                  {h.denied ? (
                    <Badge status="denied" />
                  ) : h.in_closed_cycle ? (
                    h.approved_via_request ? (
                      <Badge status="approved" />
                    ) : (
                      <span className="text-xs text-gray-400">Locked</span>
                    )
                  ) : (
                    <div className="space-x-3">
                      <button onClick={() => openEdit(h)} className="text-xs text-brand-blue hover:underline">
                        Edit
                      </button>
                      <button onClick={() => openDelete(h.id)} className="text-xs text-red-600 hover:underline">
                        Delete
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {combinedHistory.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-gray-400">No attendance marked in the current or last billing cycle.</td></tr>
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
          {editError && <p className="text-red-600 text-sm">{editError}</p>}
          <div className="flex justify-end gap-3">
            <button type="button" onClick={closeEdit} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button
              disabled={editSaving}
              onClick={saveEdit}
              className="text-sm rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800 disabled:opacity-60"
            >
              {editSaving ? 'Saving…' : 'Save'}
            </button>
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
