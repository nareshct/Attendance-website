import { useCallback, useEffect, useState } from 'react'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import { useApi } from '../../hooks/useApi'
import { usePaginatedList } from '../../hooks/usePaginatedList'
import { formatDate, formatDateTime } from '../../utils/date'

export default function AttendanceRequestsPage() {
  const api = useApi()
  // Pending is a small, self-draining queue (admin acts on it promptly) — fetched
  // whole. Reviewed is permanent history that only ever grows, so it's paginated
  // with Load more instead, same pattern as ActivityLogPage/PayoutsPage/etc. Fetching
  // every request ever made in one go (both used to be a single unbounded list) trips
  // the API client's "more than one page fetched" guard once the combined total passes
  // the page size — see TrainerDetailPage.jsx's attendance fetch for the same bug.
  const [pending, setPending] = useState([])
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [search, setSearch] = useState('')

  const {
    items: reviewed, count: reviewedCount, hasMore, loading: reviewedLoading, loadingMore,
    reload: loadReviewed, loadMore, loadLess, page,
  } = usePaginatedList('/api/attendance-requests/?status=approved,denied')

  const loadPending = useCallback(async () => {
    setPending(await api('/api/attendance-requests/?status=pending'))
  }, [api])

  useEffect(() => {
    loadPending().catch((err) => setError(err.message))
    loadReviewed().catch((err) => setError(err.message))
  }, [loadPending, loadReviewed])

  async function handleApprove(id) {
    setBusyId(id)
    setError('')
    try {
      await api(`/api/attendance-requests/${id}/approve/`, { method: 'POST' })
      await Promise.all([loadPending(), loadReviewed()])
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
      await Promise.all([loadPending(), loadReviewed()])
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyId(null)
    }
  }

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
              <th className="table-head-cell">Reason</th>
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
                <td className="table-cell text-text-secondary">
                  {r.request_type === 'duplicate_day' ? 'Second class same day' : 'Late entry'}
                </td>
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
              <tr><td colSpan={8} className="px-4 py-6 text-center text-text-tertiary">
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
              <th className="table-head-cell">Reason</th>
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
                <td className="table-cell text-text-secondary">
                  {r.request_type === 'duplicate_day' ? 'Second class same day' : 'Late entry'}
                </td>
                <td className="table-cell"><Badge status={r.status} /></td>
              </tr>
            ))}
            {!reviewedLoading && reviewed.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-text-tertiary">No reviewed requests yet.</td></tr>
            )}
            {reviewedLoading && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-text-tertiary">Loading…</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      {!reviewedLoading && reviewed.length > 0 && (
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-text-tertiary">Showing {reviewed.length} of {reviewedCount}</p>
          <div className="flex gap-4">
            {page > 1 && (
              <button onClick={loadLess} className="text-xs font-medium text-primary hover:underline focus-ring">
                Load less
              </button>
            )}
            {hasMore && (
              <button
                disabled={loadingMore}
                onClick={loadMore}
                className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring"
              >
                {loadingMore ? 'Loading…' : 'Load more'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
