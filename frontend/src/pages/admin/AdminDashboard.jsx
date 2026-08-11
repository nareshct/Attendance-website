import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { Card, StatCard } from '../../components/Card'
import { useApi } from '../../hooks/useApi'
import { formatDate, formatDateRange } from '../../utils/date'

const ALERT_PREVIEW_COUNT = 4
const RECENT_DAYS = 7

function daysAgo(n) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

// The dashboard needs every row to compute accurate counts/totals, unlike list pages
// that page incrementally via usePaginatedList — so walk every page here instead of
// relying on apiRequest's single-page fetch, which throws once a list passes PAGE_SIZE
// (see unwrapPaginated in api/client.js) rather than silently under-counting.
async function fetchAllPages(api, path) {
  const separator = path.includes('?') ? '&' : '?'
  const all = []
  let page = 1
  while (true) {
    const data = await api(`${path}${separator}page=${page}`, { raw: true })
    all.push(...data.results)
    if (!data.next) break
    page += 1
  }
  return all
}

export default function AdminDashboard() {
  const api = useApi()
  const [stats, setStats] = useState(null)
  const [cycleHistory, setCycleHistory] = useState(null)
  const [alerts, setAlerts] = useState(null)
  const [error, setError] = useState('')
  const [showAllOverdue, setShowAllOverdue] = useState(false)
  const [showAllDue, setShowAllDue] = useState(false)
  const [showAllPending, setShowAllPending] = useState(false)
  const [nearingCompletion, setNearingCompletion] = useState(null)
  const [recentlyAdded, setRecentlyAdded] = useState(null)

  const historyTotals = (cycleHistory || []).reduce(
    (acc, c) => ({
      b2b_classes: acc.b2b_classes + c.b2b_classes,
      b2b_revenue: acc.b2b_revenue + Number(c.b2b_revenue),
      b2c_classes: acc.b2c_classes + c.b2c_classes,
      b2c_revenue: acc.b2c_revenue + Number(c.b2c_revenue),
      total_trainer_cost: acc.total_trainer_cost + Number(c.total_trainer_cost),
      total_profit: acc.total_profit + Number(c.total_profit),
    }),
    { b2b_classes: 0, b2b_revenue: 0, b2c_classes: 0, b2c_revenue: 0, total_trainer_cost: 0, total_profit: 0 }
  )

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [students, trainers, enrollments, history, alertData, batches] = await Promise.all([
          fetchAllPages(api, '/api/students/'),
          fetchAllPages(api, '/api/trainers/'),
          fetchAllPages(api, '/api/enrollments/'),
          api('/api/cycle-revenue/history/'),
          api('/api/alerts/'),
          fetchAllPages(api, '/api/batches/'),
        ])
        if (cancelled) return
        const currentCycle = history.find((c) => c.status === 'open')
        setStats({
          activeStudents: students.filter((s) => s.status === 'active').length,
          activeTrainers: trainers.filter((t) => t.status === 'active').length,
          ongoingEnrollments: enrollments.filter((e) => e.status === 'ongoing').length,
          ongoingBatches: batches.filter((b) => b.status === 'ongoing').length,
          currentCycleProfit: currentCycle ? currentCycle.total_profit : null,
        })
        setCycleHistory(history)
        setAlerts(alertData)

        // Students created, or (existing students') enrollments started, in the last
        // week — a quick pulse on sign-up momentum. A brand-new student's first
        // enrollment can legitimately show up as both rows; that's two real events
        // (signed up, and started a course), not a duplicate.
        const cutoff = daysAgo(RECENT_DAYS)
        const recentStudents = students
          .filter((s) => s.created_at.slice(0, 10) >= cutoff)
          .map((s) => ({
            id: `student-${s.id}`,
            linkTo: `/admin/students/${s.id}`,
            title: s.name,
            subtitle: `New ${s.source_type} student`,
            date: s.created_at.slice(0, 10),
          }))
        const recentEnrollments = enrollments
          .filter((e) => e.start_date >= cutoff)
          .map((e) => ({
            id: `enrollment-${e.id}`,
            linkTo: `/admin/students/${e.student}`,
            title: e.student_name,
            subtitle: `Enrolled in ${e.course_name}`,
            date: e.start_date,
          }))
        setRecentlyAdded(
          [...recentStudents, ...recentEnrollments].sort((a, b) => b.date.localeCompare(a.date))
        )

        // Two separate enrollment mechanisms in this app — large-cohort Batch/BatchEnrollment
        // and individually-tracked Enrollment (trainer-led, possibly 1-on-1) — both track
        // classes-completed-vs-total, so both can be "nearing completion." Merge them into
        // one list rather than only surfacing batches, which would silently miss every
        // individually-enrolled student.
        const nearingBatches = batches
          .filter((b) => b.status === 'ongoing' && b.total_classes - b.session_count <= 2)
          .map((b) => ({
            id: `batch-${b.id}`,
            linkTo: `/admin/batches/${b.id}`,
            title: b.name,
            subtitle: b.course_name,
            remaining: Math.max(b.total_classes - b.session_count, 0),
          }))
        const nearingEnrollments = enrollments
          .filter((e) => e.status === 'ongoing' && e.classes_total - e.classes_completed <= 2)
          .map((e) => ({
            id: `enrollment-${e.id}`,
            linkTo: `/admin/students/${e.student}`,
            title: e.student_name,
            subtitle: e.course_name,
            remaining: Math.max(e.classes_total - e.classes_completed, 0),
          }))
        setNearingCompletion(
          [...nearingBatches, ...nearingEnrollments].sort((a, b) => a.remaining - b.remaining)
        )
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [api])

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">Dashboard</h1>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        <StatCard label="Active students" value={stats ? stats.activeStudents : '…'} accentClass="text-navy" />
        <StatCard label="Active trainers" value={stats ? stats.activeTrainers : '…'} accentClass="text-brand-violet" />
        <StatCard label="Ongoing enrollments" value={stats ? stats.ongoingEnrollments : '…'} accentClass="text-success" />
        <StatCard label="Ongoing batches" value={stats ? stats.ongoingBatches : '…'} accentClass="text-brand-blue" />
        <StatCard
          label="Current cycle profit"
          value={stats && stats.currentCycleProfit != null ? `₹${stats.currentCycleProfit}` : '…'}
          accentClass="text-success"
        />
      </div>

      {alerts && (alerts.overdue_invoices.length > 0 || alerts.due_installments.length > 0 || alerts.pending_payouts.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          {alerts.overdue_invoices.length > 0 && (
            <Card className="p-0">
              <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-gray-100">
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-semibold text-navy">Overdue invoices</h2>
                  <span className="text-xs font-medium text-error bg-error-tint rounded-full px-2 py-0.5">
                    {alerts.overdue_invoices.length}
                  </span>
                </div>
                <span className="text-sm font-semibold text-error tabular-nums">
                  ₹{alerts.overdue_invoices.reduce((sum, a) => sum + Number(a.amount), 0).toFixed(2)}
                </span>
              </div>
              <div>
                {(showAllOverdue ? alerts.overdue_invoices : alerts.overdue_invoices.slice(0, ALERT_PREVIEW_COUNT)).map((a) => (
                  <Link
                    key={a.id}
                    to={`/admin/clients/${a.client_id}`}
                    className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-gray-100 first:border-t-0 hover:bg-surface-sunken transition-colors duration-150 ease-out"
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-navy truncate">{a.client_name}</div>
                      <div className="text-xs text-error">{a.days_overdue}d overdue · {formatDateRange(a.cycle_start, a.cycle_end)}</div>
                    </div>
                    <div className="text-sm font-medium text-navy whitespace-nowrap tabular-nums">₹{a.amount}</div>
                  </Link>
                ))}
              </div>
              {alerts.overdue_invoices.length > ALERT_PREVIEW_COUNT && (
                <button
                  onClick={() => setShowAllOverdue((v) => !v)}
                  className="w-full text-center text-xs font-medium text-primary hover:underline py-2 border-t border-gray-100 transition-colors duration-150 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-inset"
                >
                  {showAllOverdue ? 'Show less' : `+ ${alerts.overdue_invoices.length - ALERT_PREVIEW_COUNT} more`}
                </button>
              )}
            </Card>
          )}

          {alerts.due_installments.length > 0 && (
            <Card className="p-0">
              <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-gray-100">
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-semibold text-navy">Installments due</h2>
                  <span className="text-xs font-medium text-warning bg-warning-tint rounded-full px-2 py-0.5">
                    {alerts.due_installments.length}
                  </span>
                </div>
                <span className="text-sm font-semibold text-warning tabular-nums">
                  ₹{alerts.due_installments.reduce((sum, a) => sum + Number(a.amount), 0).toFixed(2)}
                </span>
              </div>
              <div>
                {(showAllDue ? alerts.due_installments : alerts.due_installments.slice(0, ALERT_PREVIEW_COUNT)).map((a) => (
                  <Link
                    key={a.id}
                    to={`/admin/students/${a.student_id}`}
                    className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-gray-100 first:border-t-0 hover:bg-surface-sunken transition-colors duration-150 ease-out"
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-navy truncate">{a.student_name}</div>
                      <div className="text-xs text-warning">Installment #{a.sequence} · {a.course_name}</div>
                    </div>
                    <div className="text-sm font-medium text-navy whitespace-nowrap tabular-nums">₹{a.amount}</div>
                  </Link>
                ))}
              </div>
              {alerts.due_installments.length > ALERT_PREVIEW_COUNT && (
                <button
                  onClick={() => setShowAllDue((v) => !v)}
                  className="w-full text-center text-xs font-medium text-primary hover:underline py-2 border-t border-gray-100 transition-colors duration-150 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-inset"
                >
                  {showAllDue ? 'Show less' : `+ ${alerts.due_installments.length - ALERT_PREVIEW_COUNT} more`}
                </button>
              )}
            </Card>
          )}

          {alerts.pending_payouts.length > 0 && (
            <Card className="p-0">
              <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-gray-100">
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-semibold text-navy">Payouts pending</h2>
                  <span className="text-xs font-medium text-warning bg-warning-tint rounded-full px-2 py-0.5">
                    {alerts.pending_payouts.length}
                  </span>
                </div>
                <span className="text-sm font-semibold text-warning tabular-nums">
                  ₹{alerts.pending_payouts.reduce((sum, a) => sum + Number(a.amount), 0).toFixed(2)}
                </span>
              </div>
              <div>
                {(showAllPending ? alerts.pending_payouts : alerts.pending_payouts.slice(0, ALERT_PREVIEW_COUNT)).map((a) => (
                  <Link
                    key={a.id}
                    to={`/admin/trainers/${a.trainer_id}`}
                    className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-gray-100 first:border-t-0 hover:bg-surface-sunken transition-colors duration-150 ease-out"
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-navy truncate">{a.trainer_name}</div>
                      <div className="text-xs text-warning">{formatDateRange(a.cycle_start, a.cycle_end)}</div>
                    </div>
                    <div className="text-sm font-medium text-navy whitespace-nowrap tabular-nums">₹{a.amount}</div>
                  </Link>
                ))}
              </div>
              {alerts.pending_payouts.length > ALERT_PREVIEW_COUNT && (
                <button
                  onClick={() => setShowAllPending((v) => !v)}
                  className="w-full text-center text-xs font-medium text-primary hover:underline py-2 border-t border-gray-100 transition-colors duration-150 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-inset"
                >
                  {showAllPending ? 'Show less' : `+ ${alerts.pending_payouts.length - ALERT_PREVIEW_COUNT} more`}
                </button>
              )}
            </Card>
          )}
        </div>
      )}

      {nearingCompletion && nearingCompletion.length > 0 && (
        <Card className="p-0 mb-8">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-navy">Nearing completion</h2>
            <span className="text-xs font-medium text-navy bg-surface-sunken rounded-full px-2 py-0.5">
              {nearingCompletion.length}
            </span>
          </div>
          <div className="max-h-72 overflow-y-auto">
            {nearingCompletion.map((b) => (
              <Link
                key={b.id}
                to={b.linkTo}
                className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-gray-100 first:border-t-0 hover:bg-surface-sunken transition-colors duration-150 ease-out"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium text-navy truncate">{b.title}</div>
                  <div className="text-xs text-text-secondary">{b.subtitle}</div>
                </div>
                <div className="text-sm font-medium text-navy whitespace-nowrap tabular-nums">
                  {b.remaining === 0 ? 'Last class logged' : `${b.remaining} class${b.remaining === 1 ? '' : 'es'} left`}
                </div>
              </Link>
            ))}
          </div>
        </Card>
      )}

      {recentlyAdded && recentlyAdded.length > 0 && (
        <Card className="p-0 mb-8">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-navy">Recently added</h2>
            <span className="text-xs font-medium text-navy bg-surface-sunken rounded-full px-2 py-0.5">
              {recentlyAdded.length}
            </span>
          </div>
          <div className="max-h-72 overflow-y-auto">
            {recentlyAdded.map((r) => (
              <Link
                key={r.id}
                to={r.linkTo}
                className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-gray-100 first:border-t-0 hover:bg-surface-sunken transition-colors duration-150 ease-out"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium text-navy truncate">{r.title}</div>
                  <div className="text-xs text-text-secondary">{r.subtitle}</div>
                </div>
                <div className="text-sm text-text-secondary whitespace-nowrap tabular-nums">{formatDate(r.date)}</div>
              </Link>
            ))}
          </div>
        </Card>
      )}

      <h2 className="text-lg font-semibold text-navy mb-3">Revenue by cycle</h2>
      <Card className="p-0">
        <div className="overflow-auto max-h-[28rem]">
          <table className="table">
            <thead className="table-head-row sticky top-0 z-10">
              <tr>
                <th className="table-head-cell">Cycle</th>
                <th className="table-head-cell">Status</th>
                <th className="table-head-cell">B2B class count</th>
                <th className="table-head-cell">B2B revenue</th>
                <th className="table-head-cell">B2C class count</th>
                <th className="table-head-cell">B2C revenue</th>
                <th className="table-head-cell">Trainer pay</th>
                <th className="table-head-cell">Profit</th>
              </tr>
            </thead>
            <tbody>
              {(cycleHistory || []).map((c) => (
                <tr key={c.cycle_id} className="table-row bg-white">
                  <td className="table-cell">{formatDate(c.cycle_start)} – {formatDate(c.cycle_end)}</td>
                  <td className="table-cell"><Badge status={c.status} /></td>
                  <td className="table-cell tabular-nums">{c.b2b_classes}</td>
                  <td className="table-cell tabular-nums">₹{c.b2b_revenue}</td>
                  <td className="table-cell tabular-nums">{c.b2c_classes}</td>
                  <td className="table-cell tabular-nums">₹{c.b2c_revenue}</td>
                  <td className="table-cell tabular-nums">₹{c.total_trainer_cost}</td>
                  <td className="table-cell font-medium text-success tabular-nums">₹{c.total_profit}</td>
                </tr>
              ))}
              {cycleHistory && cycleHistory.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-6 text-center text-text-tertiary">No billing cycles yet.</td></tr>
              )}
              {!cycleHistory && (
                <tr><td colSpan={8} className="px-4 py-6 text-center text-text-tertiary">Loading…</td></tr>
              )}
            </tbody>
            {cycleHistory && cycleHistory.length > 0 && (
              <tfoot className="sticky bottom-0 z-10">
                <tr className="table-row bg-surface-sunken font-semibold">
                  <td className="table-cell text-navy" colSpan={2}>Total</td>
                  <td className="table-cell tabular-nums">{historyTotals.b2b_classes}</td>
                  <td className="table-cell tabular-nums">₹{historyTotals.b2b_revenue.toFixed(2)}</td>
                  <td className="table-cell tabular-nums">{historyTotals.b2c_classes}</td>
                  <td className="table-cell tabular-nums">₹{historyTotals.b2c_revenue.toFixed(2)}</td>
                  <td className="table-cell tabular-nums">₹{historyTotals.total_trainer_cost.toFixed(2)}</td>
                  <td className="table-cell text-success tabular-nums">₹{historyTotals.total_profit.toFixed(2)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </Card>
    </div>
  )
}
