import { useCallback, useEffect, useState } from 'react'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import { useApi } from '../../hooks/useApi'
import { formatDate, formatDateTime } from '../../utils/date'

export default function AttendanceRequestsPage() {
  const api = useApi()
  const [requests, setRequests] = useState([])
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [search, setSearch] = useState('')

  const loadRequests = useCallback(async () => {
    setRequests(await api('/api/attendance-requests/'))
  }, [api])

  useEffect(() => {
    loadRequests().catch((err) => setError(err.message))
  }, [loadRequests])

  async function handleApprove(id) {
    setBusyId(id)
    setError('')
    try {
      await api(`/api/attendance-requests/${id}/approve/`, { method: 'POST' })
      await loadRequests()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  async function handleDeny(id) {
    setBusyId(id)
    setError('')
    try {
      await api(`/api/attendance-requests/${id}/deny/`, { method: 'POST' })
      await loadRequests()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  const pending = requests.filter((r) => r.status === 'pending')
  const reviewed = requests.filter((r) => r.status !== 'pending')

  const filteredPending = pending.filter((r) => {
    const q = search.toLowerCase()
    return (
      r.trainer_name.toLowerCase().includes(q) ||
      r.student_name.toLowerCase().includes(q) ||
      r.course_name.toLowerCase().includes(q)
    )
  })

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">Attendance Requests</h1>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <h2 className="text-lg font-semibold text-navy mb-3">Pending</h2>
      <input
        placeholder="Search by trainer, student, or course…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="input mb-4 max-w-sm"
      />
      <Card className="p-0 overflow-x-auto mb-8">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">Date</th>
              <th className="table-head-cell">Trainer</th>
              <th className="table-head-cell">Student</th>
              <th className="table-head-cell">Course</th>
              <th className="table-head-cell">Topic</th>
              <th className="table-head-cell">Requested</th>
              <th className="table-head-cell"></th>
            </tr>
          </thead>
          <tbody>
            {filteredPending.map((r) => (
              <tr key={r.id} className="table-row">
                <td className="table-cell">{formatDate(r.date)}</td>
                <td className="table-cell">{r.trainer_name}</td>
                <td className="table-cell">{r.student_name}</td>
                <td className="table-cell">{r.course_name}</td>
                <td className="table-cell text-text-secondary">{r.topic_covered || '—'}</td>
                <td className="table-cell text-text-secondary">{formatDateTime(r.created_at)}</td>
                <td className="table-cell whitespace-nowrap text-right space-x-3">
                  <button
                    disabled={busyId === r.id}
                    onClick={() => handleApprove(r.id)}
                    className="text-xs font-medium text-success hover:underline disabled:opacity-60 focus-ring"
                  >
                    Approve
                  </button>
                  <button
                    disabled={busyId === r.id}
                    onClick={() => handleDeny(r.id)}
                    className="text-xs font-medium text-error hover:underline disabled:opacity-60 focus-ring"
                  >
                    Deny
                  </button>
                </td>
              </tr>
            ))}
            {filteredPending.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-text-tertiary">
                {pending.length === 0 ? 'No pending requests.' : 'No pending requests match your search.'}
              </td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <h2 className="text-lg font-semibold text-navy mb-3">Reviewed</h2>
      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">Date</th>
              <th className="table-head-cell">Trainer</th>
              <th className="table-head-cell">Student</th>
              <th className="table-head-cell">Course</th>
              <th className="table-head-cell">Topic</th>
              <th className="table-head-cell">Status</th>
            </tr>
          </thead>
          <tbody>
            {reviewed.map((r) => (
              <tr key={r.id} className="table-row">
                <td className="table-cell">{formatDate(r.date)}</td>
                <td className="table-cell">{r.trainer_name}</td>
                <td className="table-cell">{r.student_name}</td>
                <td className="table-cell">{r.course_name}</td>
                <td className="table-cell text-text-secondary">{r.topic_covered || '—'}</td>
                <td className="table-cell"><Badge status={r.status} /></td>
              </tr>
            ))}
            {reviewed.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-text-tertiary">No reviewed requests yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
