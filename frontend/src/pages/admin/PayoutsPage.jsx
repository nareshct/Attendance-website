import { Fragment, useCallback, useEffect, useState } from 'react'
import { downloadFile } from '../../api/client'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useAuth } from '../../hooks/useAuth'
import { useApi } from '../../hooks/useApi'
import { usePaginatedList } from '../../hooks/usePaginatedList'
import { formatDate, formatDateRange } from '../../utils/date'

export default function PayoutsPage() {
  const api = useApi()
  const { auth } = useAuth()
  const [cycles, setCycles] = useState([])
  const [currentPayouts, setCurrentPayouts] = useState({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // Which one (cycle, trainer) row's class breakdown is expanded — only one at a time,
  // same accordion approach as the trainer's own My Earnings page's "view classes".
  // Keyed as "cycleId:trainerId" since the same trainer can appear in several cycles.
  const [expandedPayout, setExpandedPayout] = useState(null)
  const [payoutClasses, setPayoutClasses] = useState([])
  const [loadingPayoutClasses, setLoadingPayoutClasses] = useState(false)

  // Same paginated "Load more"/"Load less" pattern as the Students/Trainers/Clients/
  // Enrollments pages — /api/payouts/ is paginated server-side (see DEFAULT_PAGINATION_CLASS
  // in backend/config/settings.py), so an unbounded fetch here would eventually hit
  // unwrapPaginated()'s fail-loud guard once payouts passed one page.
  const {
    items: payouts, count: payoutsCount, hasMore: payoutsHasMore, loadingMore: payoutsLoadingMore,
    reload: loadPayouts, loadMore: loadMorePayouts, loadLess: loadLessPayouts, page: payoutsPage,
  } = usePaginatedList('/api/payouts/')

  const loadCycles = useCallback(async () => {
    const c = await api('/api/billing-cycles/')
    setCycles(c)

    const openCycles = c.filter((cycle) => cycle.status === 'open')
    const previews = await Promise.all(
      openCycles.map((cycle) => api(`/api/billing-cycles/${cycle.id}/current_payouts/`))
    )
    const previewsByCycle = {}
    openCycles.forEach((cycle, i) => {
      previewsByCycle[cycle.id] = previews[i]
    })
    setCurrentPayouts(previewsByCycle)
  }, [api])

  const loadAll = useCallback(
    () => Promise.all([loadCycles(), loadPayouts()]),
    [loadCycles, loadPayouts],
  )

  useEffect(() => {
    loadAll().catch((err) => setError(err.message))
  }, [loadAll])

  async function handleGenerateCurrent() {
    setBusy(true)
    setError('')
    try {
      await api('/api/billing-cycles/generate_current/', { method: 'POST' })
      await loadAll()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const [closeTarget, setCloseTarget] = useState(null)

  async function handleClose() {
    const cycleId = closeTarget
    setBusy(true)
    setError('')
    try {
      await api(`/api/billing-cycles/${cycleId}/close/`, { method: 'POST' })
      setCloseTarget(null)
      await loadAll()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const [reopenTarget, setReopenTarget] = useState(null)
  const [reopenError, setReopenError] = useState('')
  const [reopening, setReopening] = useState(false)

  function openReopen(cycleId) {
    setReopenTarget(cycleId)
    setReopenError('')
  }

  async function handleReopen() {
    const cycleId = reopenTarget
    setReopening(true)
    setReopenError('')
    try {
      await api(`/api/billing-cycles/${cycleId}/reopen/`, { method: 'POST' })
      setReopenTarget(null)
      await loadAll()
    } catch (err) {
      setReopenError(err.message)
    } finally {
      setReopening(false)
    }
  }

  async function handleMarkPaid(payoutId) {
    setBusy(true)
    setError('')
    try {
      await api(`/api/payouts/${payoutId}/mark_paid/`, { method: 'POST' })
      await loadAll()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleCancelPayout(payoutId) {
    setBusy(true)
    setError('')
    try {
      await api(`/api/payouts/${payoutId}/cancel/`, { method: 'POST' })
      await loadAll()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function toggleClasses(cycle, trainerId) {
    const key = `${cycle.id}:${trainerId}`
    if (expandedPayout === key) {
      setExpandedPayout(null)
      return
    }
    setExpandedPayout(key)
    setLoadingPayoutClasses(true)
    setError('')
    try {
      setPayoutClasses(await api(
        `/api/attendance/?trainer=${trainerId}&start=${cycle.cycle_start}&end=${cycle.cycle_end}&carried_forward_cycle=${cycle.id}`
      ))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingPayoutClasses(false)
    }
  }

  async function handleExport() {
    setBusy(true)
    setError('')
    try {
      await downloadFile('/api/reports/payouts/', auth.token)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-navy">Payouts</h1>
        <Button disabled={busy} onClick={handleGenerateCurrent}>Generate current cycle</Button>
      </div>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-navy">Billing cycles &amp; payouts</h2>
        <button disabled={busy} onClick={handleExport} className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring">
          Export CSV
        </button>
      </div>

      {cycles.map((c) => {
        const isOpen = c.status === 'open'
        const cyclePayouts = isOpen ? (currentPayouts[c.id] || []) : payouts.filter((p) => p.cycle === c.id)
        return (
          <Card key={c.id} className="p-0 overflow-hidden mb-6">
            <div className="flex items-center justify-between px-4 py-3 bg-surface-sunken border-b border-gray-100">
              <div className="flex items-center gap-3">
                <span className="font-medium text-navy">{formatDateRange(c.cycle_start, c.cycle_end)}</span>
                <Badge status={c.status} />
                {isOpen && <span className="text-xs text-text-tertiary">Live totals — updates as attendance is marked</span>}
              </div>
              {isOpen && (
                <button disabled={busy} onClick={() => setCloseTarget(c.id)} className="text-xs font-medium text-success hover:underline disabled:opacity-60 focus-ring">
                  Close &amp; calculate payouts
                </button>
              )}
              {!isOpen && (
                <button disabled={busy} onClick={() => openReopen(c.id)} className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring">
                  Reopen cycle
                </button>
              )}
            </div>
            <table className="table">
              <thead className="table-head-row">
                <tr>
                  <th className="table-head-cell">Trainer</th>
                  <th className="table-head-cell">Classes</th>
                  <th className="table-head-cell">Amount</th>
                  <th className="table-head-cell">Status</th>
                  <th className="table-head-cell"></th>
                </tr>
              </thead>
              <tbody>
                {cyclePayouts.map((p) => {
                  const rowKey = `${c.id}:${p.trainer}`
                  const expanded = expandedPayout === rowKey
                  // No date-range filter — the API call already scopes this to exactly
                  // the right set, including any carried-forward classes whose own date
                  // falls outside this cycle's own range (see AttendanceViewSet's
                  // carried_forward_cycle param).
                  const classes = expanded
                    ? [...payoutClasses].sort((a, b) => a.date.localeCompare(b.date))
                    : []
                  return (
                    <Fragment key={rowKey}>
                      <tr className="table-row">
                        <td className="table-cell">{p.trainer_name}</td>
                        <td className="table-cell tabular-nums">
                          <button onClick={() => toggleClasses(c, p.trainer)} className="hover:underline focus-ring">
                            {p.total_classes} {expanded ? '▲' : '▼'}
                          </button>
                        </td>
                        <td className="table-cell tabular-nums">
                          ₹{p.total_amount}
                          {Number(p.carried_forward_amount) > 0 && (
                            <div className="text-xs text-text-tertiary">(incl. ₹{p.carried_forward_amount} carried forward)</div>
                          )}
                        </td>
                        <td className="table-cell">{isOpen ? <Badge status="open" /> : <Badge status={p.paid_status} />}</td>
                        <td className="table-cell text-right">
                          {!isOpen && p.paid_status === 'pending' && (
                            <div className="flex items-center justify-end gap-3">
                              <button disabled={busy} onClick={() => handleMarkPaid(p.id)} className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring">
                                Mark as paid
                              </button>
                              <button disabled={busy} onClick={() => handleCancelPayout(p.id)} className="text-xs font-medium text-error hover:underline disabled:opacity-60 focus-ring">
                                Cancel
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                      {expanded && (
                        <tr className="table-row bg-surface-sunken">
                          <td colSpan={5} className="p-0">
                            <table className="table">
                              <thead className="table-head-row">
                                <tr>
                                  <th className="table-head-cell">Date</th>
                                  <th className="table-head-cell">Student</th>
                                  <th className="table-head-cell">Course</th>
                                  <th className="table-head-cell">Topic</th>
                                  <th className="table-head-cell">Rate</th>
                                </tr>
                              </thead>
                              <tbody>
                                {!loadingPayoutClasses && classes.map((a) => (
                                  <tr key={a.id} className="table-row">
                                    <td className="table-cell">
                                      {formatDate(a.date)}
                                      {(a.date < c.cycle_start || a.date > c.cycle_end) && (
                                        <div className="text-xs text-warning">Carried forward</div>
                                      )}
                                    </td>
                                    <td className="table-cell">{a.student_name}</td>
                                    <td className="table-cell">{a.course_name}</td>
                                    <td className="table-cell text-text-secondary">{a.topic_covered || '—'}</td>
                                    <td className="table-cell tabular-nums">{a.trainer_rate != null ? `₹${a.trainer_rate}` : '—'}</td>
                                  </tr>
                                ))}
                                {loadingPayoutClasses && (
                                  <tr><td colSpan={5} className="px-4 py-4 text-center text-text-tertiary">Loading…</td></tr>
                                )}
                                {!loadingPayoutClasses && classes.length === 0 && (
                                  <tr><td colSpan={5} className="px-4 py-4 text-center text-text-tertiary">No classes found for this cycle.</td></tr>
                                )}
                              </tbody>
                            </table>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
                {cyclePayouts.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">
                    {isOpen ? 'No attendance marked yet in this cycle.' : 'No payouts for this cycle.'}
                  </td></tr>
                )}
              </tbody>
            </table>
          </Card>
        )
      })}
      {cycles.length === 0 && (
        <Card className="p-6 text-center text-text-tertiary">No billing cycles yet.</Card>
      )}

      {payouts.length > 0 && (
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-text-tertiary">
            Showing {payouts.length} of {payoutsCount} payout{payoutsCount === 1 ? '' : 's'} loaded
            {payoutsHasMore && ' — closed cycles further back may not be showing their payouts yet'}
          </p>
          <div className="flex gap-4">
            {payoutsPage > 1 && (
              <button onClick={loadLessPayouts} className="text-xs font-medium text-primary hover:underline focus-ring">
                Load less
              </button>
            )}
            {payoutsHasMore && (
              <button
                disabled={payoutsLoadingMore}
                onClick={loadMorePayouts}
                className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring"
              >
                {payoutsLoadingMore ? 'Loading…' : 'Load more'}
              </button>
            )}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={closeTarget != null}
        onClose={() => setCloseTarget(null)}
        onConfirm={handleClose}
        title="Close billing cycle"
        message={
          closeTarget != null
            ? `Close ${formatDateRange(cycles.find((c) => c.id === closeTarget)?.cycle_start, cycles.find((c) => c.id === closeTarget)?.cycle_end)}? This creates real, payable payouts for every trainer and invoices for every client with activity in this cycle. It can't be undone once anything is marked paid or received — reopen only works before that.`
            : ''
        }
        confirmLabel="Close cycle"
        busyLabel="Closing…"
        busy={busy}
        error={error}
      />

      <ConfirmDialog
        open={reopenTarget != null}
        onClose={() => setReopenTarget(null)}
        onConfirm={handleReopen}
        title="Reopen billing cycle"
        message={
          reopenTarget != null
            ? `Reopen ${formatDateRange(cycles.find((c) => c.id === reopenTarget)?.cycle_start, cycles.find((c) => c.id === reopenTarget)?.cycle_end)}? This deletes the payouts and invoices it generated so they'll be recalculated from scratch the next time it's closed. Only possible while none of them have been marked paid, cancelled, or received yet.`
            : ''
        }
        confirmLabel="Reopen cycle"
        busyLabel="Reopening…"
        busy={reopening}
        error={reopenError}
      />
    </div>
  )
}
