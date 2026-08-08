import { useEffect, useState } from 'react'
import { Badge } from '../../components/Badge'
import { Card, StatCard } from '../../components/Card'
import { useApi } from '../../hooks/useApi'
import { formatDate, formatDateRange } from '../../utils/date'

// Deliberately one restrained hero color, not a rainbow of accents per
// tile — the old blue/green/violet/green mix per card had no semantic
// meaning (none of these are a status), so it read as decoration rather
// than information. Every headline figure is navy; color is reserved for
// the one genuinely semantic detail (the carried-forward caveat, amber)
// and the interactive "view classes" card's hover/focus affordance.
const HERO_VALUE_CLASS = 'text-navy'

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

  // "Last cycle" always means the most recent formally-closed cycle — so this keeps
  // excluding whatever matches the live current cycle's dates, even if that current
  // cycle has since been settled early into a real Payout (see currentCycleAlreadySettled
  // below): a just-settled current cycle isn't "last cycle," it's still this one.
  const history = payouts.filter((p) => !current || p.cycle_start !== current.cycle_start || p.cycle_end !== current.cycle_end)
  const lastCycle = history[0]

  // Normally a cycle is either the live "still open" row or a real Payout row, never
  // both — Payout rows only exist for cycles that have formally closed. But an admin
  // can settle just one trainer's current cycle early (e.g. while resolving unpaid
  // earnings before an archive), without closing the cycle for anyone else — so a
  // real, possibly already-paid Payout can exist for a cycle that's still "open".
  // Once that's happened, the Payout History table below shows that real row (with
  // its real status) instead of a stale "open" live figure.
  //
  // But that settled Payout is a snapshot — the API keeps recomputing `current` live
  // off attendance/adjustments, so if more classes get taught (or a late request gets
  // approved) in this same still-open cycle after settling, the live total moves past
  // what the Payout recorded. Comparing amounts (not just existence) catches that;
  // currentCycleAdditional then surfaces the newly-accrued delta instead of silently
  // hiding it behind the settled row's stale figure.
  const currentCyclePayout = current && payouts.find(
    (p) => p.cycle_start === current.cycle_start && p.cycle_end === current.cycle_end,
  )
  const currentCycleFullySettled = currentCyclePayout && Number(currentCyclePayout.total_amount) === Number(current.total_amount)
  const currentCycleAdditional = currentCyclePayout && !currentCycleFullySettled
    ? {
      classes: current.total_classes - currentCyclePayout.total_classes,
      amount: (Number(current.total_amount) - Number(currentCyclePayout.total_amount)).toFixed(2),
    }
    : null

  const lastCycleClasses = lastCycle
    ? attendance
        .filter((a) => a.date >= lastCycle.cycle_start && a.date <= lastCycle.cycle_end)
        .sort((a, b) => a.date.localeCompare(b.date))
    : []

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">My Earnings</h1>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
        <StatCard
          label={current ? `Current cycle (${formatDateRange(current.cycle_start, current.cycle_end)})` : 'Current cycle'}
          value={
            current
              ? current.carried_forward_count > 0
                ? (
                  <>
                    ₹{current.total_amount}{' '}
                    <span className="text-xs text-warning font-normal">
                      incl. ₹{current.carried_forward_amount} from {current.carried_forward_count} late-approved class{current.carried_forward_count === 1 ? '' : 'es'}
                    </span>
                  </>
                )
                : `₹${current.total_amount}`
              : '—'
          }
          accentClass={HERO_VALUE_CLASS}
        />
        <StatCard
          label="Current cycle classes"
          value={
            current
              ? current.carried_forward_count > 0
                ? (
                  <>
                    {current.total_classes}{' '}
                    <span className="text-xs text-warning font-normal">
                      incl. ₹{current.carried_forward_amount} from {current.carried_forward_count} late-approved class{current.carried_forward_count === 1 ? '' : 'es'}
                    </span>
                  </>
                )
                : current.total_classes
              : '—'
          }
          accentClass={HERO_VALUE_CLASS}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
        <StatCard
          label={lastCycle ? `Last cycle (${formatDateRange(lastCycle.cycle_start, lastCycle.cycle_end)})` : 'Last cycle'}
          value={lastCycle ? `₹${lastCycle.total_amount}` : '—'}
          accentClass={HERO_VALUE_CLASS}
        />
        <button
          type="button"
          disabled={!lastCycle}
          onClick={() => setShowLastCycleClasses((v) => !v)}
          className="text-left disabled:cursor-default rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
        >
          <Card className={lastCycle ? 'hover:border-primary-tint-border hover:shadow-sm transition-[box-shadow,border-color] duration-150 ease-out cursor-pointer' : ''}>
            <div className="text-xs font-medium text-text-secondary">Last cycle classes</div>
            <div className="flex items-center gap-2 mt-1.5">
              <span className="text-[26px] font-bold tracking-tight tabular-nums text-navy">{lastCycle ? lastCycle.total_classes : '—'}</span>
              {lastCycle && (
                <span className="text-xs text-text-secondary">{showLastCycleClasses ? 'Hide classes ▲' : 'View classes ▼'}</span>
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
            <table className="table">
              <thead className="table-head-row">
                <tr>
                  <th className="table-head-cell">Date</th>
                  <th className="table-head-cell">Student</th>
                  <th className="table-head-cell">Course</th>
                  <th className="table-head-cell">Topic</th>
                </tr>
              </thead>
              <tbody>
                {lastCycleClasses.map((a) => (
                  <tr key={a.id} className="table-row">
                    <td className="table-cell">{formatDate(a.date)}</td>
                    <td className="table-cell">{a.student_name}</td>
                    <td className="table-cell">{a.course_name}</td>
                    <td className="table-cell text-text-secondary">{a.topic_covered || '—'}</td>
                  </tr>
                ))}
                {lastCycleClasses.length === 0 && (
                  <tr><td colSpan={4} className="px-4 py-6 text-center text-text-tertiary">No classes found for this cycle.</td></tr>
                )}
              </tbody>
            </table>
          </Card>
        </>
      )}

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
            {current && !currentCyclePayout && (
              <tr className="table-row bg-warning-tint/50">
                <td className="table-cell">{formatDateRange(current.cycle_start, current.cycle_end)}</td>
                <td className="table-cell tabular-nums">{current.total_classes}</td>
                <td className="table-cell tabular-nums">
                  ₹{current.total_amount}
                  {current.carried_forward_count > 0 && (
                    <div className="text-xs text-warning">
                      incl. ₹{current.carried_forward_amount} from {current.carried_forward_count} late-approved class{current.carried_forward_count === 1 ? '' : 'es'}
                    </div>
                  )}
                </td>
                <td className="table-cell"><Badge status="open" /></td>
              </tr>
            )}
            {currentCycleAdditional && (
              <tr className="table-row bg-warning-tint/50">
                <td className="table-cell">{formatDateRange(current.cycle_start, current.cycle_end)}</td>
                <td className="table-cell tabular-nums">+{currentCycleAdditional.classes}</td>
                <td className="table-cell tabular-nums">
                  +₹{currentCycleAdditional.amount}
                  <div className="text-xs text-warning">earned after the payout below was settled</div>
                </td>
                <td className="table-cell"><Badge status="open" /></td>
              </tr>
            )}
            {currentCyclePayout && (
              <tr key={currentCyclePayout.id} className="table-row">
                <td className="table-cell">{formatDateRange(currentCyclePayout.cycle_start, currentCyclePayout.cycle_end)}</td>
                <td className="table-cell tabular-nums">{currentCyclePayout.total_classes}</td>
                <td className="table-cell tabular-nums">
                  ₹{currentCyclePayout.total_amount}
                  {Number(currentCyclePayout.carried_forward_amount) > 0 && (
                    <div className="text-xs text-text-tertiary">(incl. ₹{currentCyclePayout.carried_forward_amount} carried forward)</div>
                  )}
                </td>
                <td className="table-cell"><Badge status={currentCyclePayout.paid_status} /></td>
              </tr>
            )}
            {history.map((p) => (
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
            {history.length === 0 && !current && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-text-tertiary">No payouts yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
