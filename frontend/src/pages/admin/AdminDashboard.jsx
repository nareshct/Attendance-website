import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { Card, StatCard } from '../../components/Card'
import { useApi } from '../../hooks/useApi'
import { formatDate, formatDateRange } from '../../utils/date'

const ALERT_PREVIEW_COUNT = 4

export default function AdminDashboard() {
  const api = useApi()
  const [stats, setStats] = useState(null)
  const [cycleHistory, setCycleHistory] = useState(null)
  const [alerts, setAlerts] = useState(null)
  const [error, setError] = useState('')
  const [showAllOverdue, setShowAllOverdue] = useState(false)
  const [showAllDue, setShowAllDue] = useState(false)

  const historyTotals = (cycleHistory || []).reduce(
    (acc, c) => ({
      total_classes: acc.total_classes + c.total_classes,
      b2b_revenue: acc.b2b_revenue + Number(c.b2b_revenue),
      b2c_revenue: acc.b2c_revenue + Number(c.b2c_revenue),
      total_revenue: acc.total_revenue + Number(c.total_revenue),
      total_trainer_cost: acc.total_trainer_cost + Number(c.total_trainer_cost),
      total_profit: acc.total_profit + Number(c.total_profit),
    }),
    { total_classes: 0, b2b_revenue: 0, b2c_revenue: 0, total_revenue: 0, total_trainer_cost: 0, total_profit: 0 }
  )

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [students, enrollments, clientSummary, history, alertData] = await Promise.all([
          api('/api/students/'),
          api('/api/enrollments/'),
          api('/api/clients/summary/'),
          api('/api/cycle-revenue/history/'),
          api('/api/alerts/'),
        ])
        if (cancelled) return
        setStats({
          activeStudents: students.filter((s) => s.status === 'active').length,
          ongoingEnrollments: enrollments.filter((e) => e.status === 'ongoing').length,
          totalPending: clientSummary.total_pending_amount,
        })
        setCycleHistory(history)
        setAlerts(alertData)
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

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <StatCard label="Active students" value={stats ? stats.activeStudents : '…'} accentClass="text-brand-blue" />
        <StatCard label="Ongoing enrollments" value={stats ? stats.ongoingEnrollments : '…'} accentClass="text-brand-green" />
        <StatCard label="Total pending" value={stats ? `₹${stats.totalPending}` : '…'} accentClass="text-brand-amber" />
      </div>

      {alerts && (alerts.overdue_invoices.length > 0 || alerts.due_installments.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
          {alerts.overdue_invoices.length > 0 && (
            <Card className="p-0">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
                <h2 className="text-sm font-semibold text-navy">Overdue invoices</h2>
                <span className="text-xs font-medium text-red-600 bg-red-50 rounded-full px-2 py-0.5">
                  {alerts.overdue_invoices.length}
                </span>
              </div>
              <div>
                {(showAllOverdue ? alerts.overdue_invoices : alerts.overdue_invoices.slice(0, ALERT_PREVIEW_COUNT)).map((a) => (
                  <Link
                    key={a.id}
                    to={`/admin/clients/${a.client_id}`}
                    className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-gray-100 first:border-t-0 hover:bg-gray-50 transition-colors"
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-navy truncate">{a.client_name}</div>
                      <div className="text-xs text-red-600">{a.days_overdue}d overdue · {formatDateRange(a.cycle_start, a.cycle_end)}</div>
                    </div>
                    <div className="text-sm font-medium text-navy whitespace-nowrap">₹{a.amount}</div>
                  </Link>
                ))}
              </div>
              {alerts.overdue_invoices.length > ALERT_PREVIEW_COUNT && (
                <button
                  onClick={() => setShowAllOverdue((v) => !v)}
                  className="w-full text-center text-xs text-brand-blue hover:underline py-2 border-t border-gray-100"
                >
                  {showAllOverdue ? 'Show less' : `+ ${alerts.overdue_invoices.length - ALERT_PREVIEW_COUNT} more`}
                </button>
              )}
            </Card>
          )}

          {alerts.due_installments.length > 0 && (
            <Card className="p-0">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
                <h2 className="text-sm font-semibold text-navy">Installments due</h2>
                <span className="text-xs font-medium text-brand-amber bg-amber-50 rounded-full px-2 py-0.5">
                  {alerts.due_installments.length}
                </span>
              </div>
              <div>
                {(showAllDue ? alerts.due_installments : alerts.due_installments.slice(0, ALERT_PREVIEW_COUNT)).map((a) => (
                  <Link
                    key={a.id}
                    to={`/admin/students/${a.student_id}`}
                    className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-gray-100 first:border-t-0 hover:bg-gray-50 transition-colors"
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-navy truncate">{a.student_name}</div>
                      <div className="text-xs text-brand-amber">Installment #{a.sequence} · {a.course_name}</div>
                    </div>
                    <div className="text-sm font-medium text-navy whitespace-nowrap">₹{a.amount}</div>
                  </Link>
                ))}
              </div>
              {alerts.due_installments.length > ALERT_PREVIEW_COUNT && (
                <button
                  onClick={() => setShowAllDue((v) => !v)}
                  className="w-full text-center text-xs text-brand-blue hover:underline py-2 border-t border-gray-100"
                >
                  {showAllDue ? 'Show less' : `+ ${alerts.due_installments.length - ALERT_PREVIEW_COUNT} more`}
                </button>
              )}
            </Card>
          )}
        </div>
      )}

      <h2 className="text-lg font-semibold text-navy mb-3">Revenue by cycle</h2>
      <Card className="p-0">
        <div className="overflow-auto max-h-[28rem]">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left sticky top-0 z-10">
              <tr>
                <th className="px-4 py-3">Cycle</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Classes</th>
                <th className="px-4 py-3 text-right">B2B revenue</th>
                <th className="px-4 py-3 text-right">B2C revenue</th>
                <th className="px-4 py-3 text-right">Total revenue</th>
                <th className="px-4 py-3 text-right">Trainer pay</th>
                <th className="px-4 py-3 text-right">Profit</th>
              </tr>
            </thead>
            <tbody>
              {(cycleHistory || []).map((c) => (
                <tr key={c.cycle_id} className="border-t border-gray-100 bg-white">
                  <td className="px-4 py-3">{formatDate(c.cycle_start)} – {formatDate(c.cycle_end)}</td>
                  <td className="px-4 py-3"><Badge status={c.status} /></td>
                  <td className="px-4 py-3 text-right">{c.total_classes}</td>
                  <td className="px-4 py-3 text-right">₹{c.b2b_revenue}</td>
                  <td className="px-4 py-3 text-right">₹{c.b2c_revenue}</td>
                  <td className="px-4 py-3 text-right font-medium">₹{c.total_revenue}</td>
                  <td className="px-4 py-3 text-right text-gray-500">₹{c.total_trainer_cost}</td>
                  <td className="px-4 py-3 text-right font-medium text-brand-green">₹{c.total_profit}</td>
                </tr>
              ))}
              {cycleHistory && cycleHistory.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-6 text-center text-gray-400">No billing cycles yet.</td></tr>
              )}
              {!cycleHistory && (
                <tr><td colSpan={8} className="px-4 py-6 text-center text-gray-400">Loading…</td></tr>
              )}
            </tbody>
            {cycleHistory && cycleHistory.length > 0 && (
              <tfoot className="sticky bottom-0 z-10">
                <tr className="border-t border-gray-200 bg-gray-50">
                  <td className="px-4 py-3 text-navy font-semibold" colSpan={2}>Total</td>
                  <td className="px-4 py-3 text-right font-semibold">{historyTotals.total_classes}</td>
                  <td className="px-4 py-3 text-right font-semibold">₹{historyTotals.b2b_revenue.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right font-semibold">₹{historyTotals.b2c_revenue.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right font-semibold">₹{historyTotals.total_revenue.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right font-semibold text-gray-500">₹{historyTotals.total_trainer_cost.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right font-semibold text-brand-green">₹{historyTotals.total_profit.toFixed(2)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </Card>
    </div>
  )
}
