import { useEffect, useState } from 'react'
import { downloadFile } from '../../api/client'
import { Badge } from '../../components/Badge'
import { Card, StatCard } from '../../components/Card'
import { useAuth } from '../../hooks/useAuth'
import { useApi } from '../../hooks/useApi'
import { usePaginatedList } from '../../hooks/usePaginatedList'
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
  const { auth } = useAuth()
  // Same paginated "Load more"/"Load less" pattern as the admin Payouts page —
  // /api/my-earnings/ is paginated server-side (see DEFAULT_PAGINATION_CLASS in
  // backend/config/settings.py), so an unbounded fetch here would eventually hit
  // unwrapPaginated()'s fail-loud guard once a trainer's payout history passed one page.
  const {
    items: payouts, count: payoutsCount, hasMore: payoutsHasMore, loadingMore: payoutsLoadingMore,
    reload: loadPayouts, loadMore: loadMorePayouts, loadLess: loadLessPayouts, page: payoutsPage,
  } = usePaginatedList('/api/my-earnings/')
  const [current, setCurrent] = useState(null)
  const [attendance, setAttendance] = useState([])
  const [showLastCycleClasses, setShowLastCycleClasses] = useState(false)
  const [loadingLastCycleClasses, setLoadingLastCycleClasses] = useState(false)
  const [currentCycleAttendance, setCurrentCycleAttendance] = useState([])
  const [showCurrentCycleClasses, setShowCurrentCycleClasses] = useState(false)
  const [loadingCurrentCycleClasses, setLoadingCurrentCycleClasses] = useState(false)
  const [downloadingCsvKey, setDownloadingCsvKey] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    loadPayouts().catch((err) => setError(err.message))
    api('/api/my-earnings/current/').then(setCurrent).catch((err) => setError(err.message))
  }, [api, loadPayouts])

  // "Last cycle" always means the most recent formally-closed cycle — so this keeps
  // excluding whatever matches the live current cycle's dates, even if that current
  // cycle has since been settled early into a real Payout (see currentCycleAlreadySettled
  // below): a just-settled current cycle isn't "last cycle," it's still this one.
  const history = payouts.filter((p) => !current || p.cycle_start !== current.cycle_start || p.cycle_end !== current.cycle_end)
  const lastCycle = history[0]

  // Fetched on demand, bounded to just this one cycle's date range, rather than
  // eagerly pulling a trainer's entire attendance history up front — that used to
  // break outright once a trainer's lifetime total passed the API's page size (see
  // api/client.js's unwrapPaginated).
  async function toggleLastCycleClasses() {
    const opening = !showLastCycleClasses
    setShowLastCycleClasses(opening)
    if (!opening || !lastCycle) return
    setLoadingLastCycleClasses(true)
    setError('')
    try {
      setAttendance(await api(
        `/api/attendance/?start=${lastCycle.cycle_start}&end=${lastCycle.cycle_end}&carried_forward_cycle=${lastCycle.cycle}`
      ))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingLastCycleClasses(false)
    }
  }

  // Same on-demand, bounded-fetch approach as toggleLastCycleClasses() — a separate
  // state/fetch rather than reusing `attendance`, since the current and last cycle's
  // date ranges are fetched independently and could otherwise clobber each other if
  // both sections are opened.
  async function toggleCurrentCycleClasses() {
    const opening = !showCurrentCycleClasses
    setShowCurrentCycleClasses(opening)
    if (!opening || !current) return
    setLoadingCurrentCycleClasses(true)
    setError('')
    try {
      setCurrentCycleAttendance(await api(
        `/api/attendance/?start=${current.cycle_start}&end=${current.cycle_end}&carried_forward_cycle=${current.cycle_id}`
      ))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingCurrentCycleClasses(false)
    }
  }

  async function handleDownloadCsv(key, start, end) {
    setDownloadingCsvKey(key)
    setError('')
    try {
      await downloadFile(`/api/reports/my-attendance/?start=${start}&end=${end}`, auth.token)
    } catch (err) {
      setError(err.message)
    } finally {
      setDownloadingCsvKey(null)
    }
  }

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

  // No date-range filter here — the API call above already scopes this to exactly the
  // right set, including any carried-forward classes whose own date falls outside
  // [cycle_start, cycle_end] (see AttendanceViewSet.get_queryset's carried_forward_cycle
  // param). isCarriedForward flags those for the "carried forward" note below.
  const lastCycleClasses = [...attendance].sort((a, b) => a.date.localeCompare(b.date))
  const currentCycleClasses = [...currentCycleAttendance].sort((a, b) => a.date.localeCompare(b.date))

  function isCarriedForward(a, cycle) {
    return a.date < cycle.cycle_start || a.date > cycle.cycle_end
  }

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
        <button
          type="button"
          disabled={!current}
          onClick={toggleCurrentCycleClasses}
          className="text-left disabled:cursor-default rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
        >
          <Card className={current ? 'hover:border-primary-tint-border hover:shadow-sm transition-[box-shadow,border-color] duration-150 ease-out cursor-pointer' : ''}>
            <div className="text-xs font-medium text-text-secondary">Current cycle classes</div>
            <div className="flex items-center gap-2 mt-1.5">
              <span className="text-[26px] font-bold tracking-tight tabular-nums text-navy">{current ? current.total_classes : '—'}</span>
              {current && (
                <span className="text-xs text-text-secondary">{showCurrentCycleClasses ? 'Hide classes ▲' : 'View classes ▼'}</span>
              )}
            </div>
            {current && current.carried_forward_count > 0 && (
              <div className="text-xs text-warning mt-1">
                incl. ₹{current.carried_forward_amount} from {current.carried_forward_count} late-approved class{current.carried_forward_count === 1 ? '' : 'es'}
              </div>
            )}
          </Card>
        </button>
      </div>

      {showCurrentCycleClasses && current && (
        <>
          <h2 className="text-lg font-semibold text-navy mb-3">
            Classes taken ({formatDateRange(current.cycle_start, current.cycle_end)})
          </h2>
          <Card className="p-0 overflow-x-auto mb-8">
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
                {!loadingCurrentCycleClasses && currentCycleClasses.map((a) => (
                  <tr key={a.id} className="table-row">
                    <td className="table-cell">
                      {formatDate(a.date)}
                      {isCarriedForward(a, current) && (
                        <div className="text-xs text-warning">Carried forward</div>
                      )}
                    </td>
                    <td className="table-cell">{a.student_name}</td>
                    <td className="table-cell">{a.course_name}</td>
                    <td className="table-cell text-text-secondary">{a.topic_covered || '—'}</td>
                    <td className="table-cell tabular-nums">{a.trainer_rate != null ? `₹${a.trainer_rate}` : '—'}</td>
                  </tr>
                ))}
                {loadingCurrentCycleClasses && (
                  <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">Loading…</td></tr>
                )}
                {!loadingCurrentCycleClasses && currentCycleClasses.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">No classes found for this cycle.</td></tr>
                )}
              </tbody>
            </table>
          </Card>
        </>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
        <StatCard
          label={lastCycle ? `Last cycle (${formatDateRange(lastCycle.cycle_start, lastCycle.cycle_end)})` : 'Last cycle'}
          value={lastCycle ? `₹${lastCycle.total_amount}` : '—'}
          accentClass={HERO_VALUE_CLASS}
        />
        <button
          type="button"
          disabled={!lastCycle}
          onClick={toggleLastCycleClasses}
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
                  <th className="table-head-cell">Rate</th>
                </tr>
              </thead>
              <tbody>
                {!loadingLastCycleClasses && lastCycleClasses.map((a) => (
                  <tr key={a.id} className="table-row">
                    <td className="table-cell">
                      {formatDate(a.date)}
                      {isCarriedForward(a, lastCycle) && (
                        <div className="text-xs text-warning">Carried forward</div>
                      )}
                    </td>
                    <td className="table-cell">{a.student_name}</td>
                    <td className="table-cell">{a.course_name}</td>
                    <td className="table-cell text-text-secondary">{a.topic_covered || '—'}</td>
                    <td className="table-cell tabular-nums">{a.trainer_rate != null ? `₹${a.trainer_rate}` : '—'}</td>
                  </tr>
                ))}
                {loadingLastCycleClasses && (
                  <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">Loading…</td></tr>
                )}
                {!loadingLastCycleClasses && lastCycleClasses.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">No classes found for this cycle.</td></tr>
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
              <th className="table-head-cell text-center">Download</th>
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
                <td className="table-cell text-center">
                  <button
                    disabled={downloadingCsvKey === 'current'}
                    onClick={() => handleDownloadCsv('current', current.cycle_start, current.cycle_end)}
                    className="text-xs font-medium text-text-secondary hover:text-primary disabled:opacity-60 focus-ring"
                  >
                    {downloadingCsvKey === 'current' ? 'Downloading…' : 'Attendance (CSV)'}
                  </button>
                </td>
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
                <td className="table-cell"></td>
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
                <td className="table-cell text-center">
                  <button
                    disabled={downloadingCsvKey === currentCyclePayout.id}
                    onClick={() => handleDownloadCsv(currentCyclePayout.id, currentCyclePayout.cycle_start, currentCyclePayout.cycle_end)}
                    className="text-xs font-medium text-text-secondary hover:text-primary disabled:opacity-60 focus-ring"
                  >
                    {downloadingCsvKey === currentCyclePayout.id ? 'Downloading…' : 'Attendance (CSV)'}
                  </button>
                </td>
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
                <td className="table-cell text-center">
                  <button
                    disabled={downloadingCsvKey === p.id}
                    onClick={() => handleDownloadCsv(p.id, p.cycle_start, p.cycle_end)}
                    className="text-xs font-medium text-text-secondary hover:text-primary disabled:opacity-60 focus-ring"
                  >
                    {downloadingCsvKey === p.id ? 'Downloading…' : 'Attendance (CSV)'}
                  </button>
                </td>
              </tr>
            ))}
            {history.length === 0 && !current && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">No payouts yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      {payouts.length > 0 && (
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-text-tertiary">
            Showing {payouts.length} of {payoutsCount} payout{payoutsCount === 1 ? '' : 's'} loaded
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
    </div>
  )
}
