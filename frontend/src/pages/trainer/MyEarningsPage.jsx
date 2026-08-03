import { useEffect, useState } from 'react'
import { Badge } from '../../components/Badge'
import { Card, StatCard } from '../../components/Card'
import { useApi } from '../../hooks/useApi'
import { formatDate, formatDateRange } from '../../utils/date'

export default function MyEarningsPage() {
  const api = useApi()
  const [payouts, setPayouts] = useState([])
  const [current, setCurrent] = useState(null)
  const [attendance, setAttendance] = useState([])
  const [showLastCycleClasses, setShowLastCycleClasses] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/api/my-earnings/').then(setPayouts).catch((err) => setError(err.message))
    api('/api/my-earnings/current/').then(setCurrent).catch((err) => setError(err.message))
    api('/api/attendance/').then(setAttendance).catch((err) => setError(err.message))
  }, [api])

  const history = payouts.filter((p) => !current || p.cycle_start !== current.cycle_start || p.cycle_end !== current.cycle_end)
  const lastCycle = history[0]

  const lastCycleClasses = lastCycle
    ? attendance
        .filter((a) => a.date >= lastCycle.cycle_start && a.date <= lastCycle.cycle_end)
        .sort((a, b) => a.date.localeCompare(b.date))
    : []

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">My Earnings</h1>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
        <StatCard
          label={current ? `Current cycle (${formatDateRange(current.cycle_start, current.cycle_end)})` : 'Current cycle'}
          value={
            current
              ? current.carried_forward_count > 0
                ? (
                  <>
                    ₹{current.total_amount}{' '}
                    <span className="text-xs text-brand-amber font-normal">
                      incl. ₹{current.carried_forward_amount} from {current.carried_forward_count} late-approved class{current.carried_forward_count === 1 ? '' : 'es'}
                    </span>
                  </>
                )
                : `₹${current.total_amount}`
              : '—'
          }
          accentClass="text-brand-blue"
        />
        <StatCard
          label="Current cycle classes"
          value={
            current
              ? current.carried_forward_count > 0
                ? (
                  <>
                    {current.total_classes}{' '}
                    <span className="text-xs text-brand-amber font-normal">
                      incl. ₹{current.carried_forward_amount} from {current.carried_forward_count} late-approved class{current.carried_forward_count === 1 ? '' : 'es'}
                    </span>
                  </>
                )
                : current.total_classes
              : '—'
          }
          accentClass="text-brand-green"
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
        <StatCard
          label={lastCycle ? `Last cycle (${formatDateRange(lastCycle.cycle_start, lastCycle.cycle_end)})` : 'Last cycle'}
          value={lastCycle ? `₹${lastCycle.total_amount}` : '—'}
          accentClass="text-brand-violet"
        />
        <button
          type="button"
          disabled={!lastCycle}
          onClick={() => setShowLastCycleClasses((v) => !v)}
          className="text-left disabled:cursor-default"
        >
          <Card className={lastCycle ? 'hover:border-brand-green transition-colors cursor-pointer' : ''}>
            <div className="text-sm text-gray-500">Last cycle classes</div>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-3xl font-semibold text-brand-green">{lastCycle ? lastCycle.total_classes : '—'}</span>
              {lastCycle && (
                <span className="text-xs text-gray-400">{showLastCycleClasses ? 'Hide classes ▲' : 'View classes ▼'}</span>
              )}
            </div>
          </Card>
        </button>
      </div>

      {showLastCycleClasses && lastCycle && (
        <>
          <h2 className="text-lg font-semibold text-navy mb-3">
            Classes taken ({formatDateRange(lastCycle.cycle_start, lastCycle.cycle_end)})
          </h2>
          <Card className="p-0 overflow-x-auto mb-8">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-left">
                <tr>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Student</th>
                  <th className="px-4 py-3">Course</th>
                  <th className="px-4 py-3">Topic</th>
                </tr>
              </thead>
              <tbody>
                {lastCycleClasses.map((a) => (
                  <tr key={a.id} className="border-t border-gray-100">
                    <td className="px-4 py-3">{formatDate(a.date)}</td>
                    <td className="px-4 py-3">{a.student_name}</td>
                    <td className="px-4 py-3">{a.course_name}</td>
                    <td className="px-4 py-3 text-gray-500">{a.topic_covered || '—'}</td>
                  </tr>
                ))}
                {lastCycleClasses.length === 0 && (
                  <tr><td colSpan={4} className="px-4 py-6 text-center text-gray-400">No classes found for this cycle.</td></tr>
                )}
              </tbody>
            </table>
          </Card>
        </>
      )}

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
            {current && (
              <tr className="border-t border-gray-100 bg-gray-50/50">
                <td className="px-4 py-3">{formatDateRange(current.cycle_start, current.cycle_end)}</td>
                <td className="px-4 py-3">{current.total_classes}</td>
                <td className="px-4 py-3">
                  ₹{current.total_amount}
                  {current.carried_forward_count > 0 && (
                    <div className="text-xs text-brand-amber">
                      incl. ₹{current.carried_forward_amount} from {current.carried_forward_count} late-approved class{current.carried_forward_count === 1 ? '' : 'es'}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3"><Badge status="open" /></td>
              </tr>
            )}
            {history.map((p) => (
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
            {history.length === 0 && !current && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-gray-400">No payouts yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
