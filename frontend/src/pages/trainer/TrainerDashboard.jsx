import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { Card, StatCard } from '../../components/Card'
import { TrendChart } from '../../components/TrendChart'
import { WeeklyScheduleGrid } from '../../components/WeeklyScheduleGrid'
import { useApi } from '../../hooks/useApi'
import { formatDate } from '../../utils/date'
import { DAY_OPTIONS, formatTime, todayDayCode } from '../../utils/schedule'

const DAY_ORDER = DAY_OPTIONS.map((d) => d.code)

const today = () => new Date().toISOString().slice(0, 10)

// An ongoing enrollment with no logged class in this many days gets flagged as a
// possible check-in — long enough that a once-a-week student isn't flagged every gap
// between classes, short enough to still catch someone who's genuinely gone quiet.
const NO_SESSION_ALERT_DAYS = 14

function daysBetween(dateStr, from) {
  return Math.round((from - new Date(dateStr)) / (1000 * 60 * 60 * 24))
}

export default function TrainerDashboard() {
  const api = useApi()
  const [stats, setStats] = useState(null)
  const [todaysClasses, setTodaysClasses] = useState([])
  const [restOfWeek, setRestOfWeek] = useState([])
  const [enrollments, setEnrollments] = useState([])
  const [earningsHistory, setEarningsHistory] = useState([])
  const [substituteCoverage, setSubstituteCoverage] = useState([])
  const [quietStudents, setQuietStudents] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [students, earnings, current, allMarked, attendanceRequests] = await Promise.all([
          api('/api/my-students/'),
          api('/api/my-earnings/'),
          api('/api/my-earnings/current/'),
          api('/api/attendance/'),
          api('/api/attendance-requests/'),
        ])
        if (cancelled) return

        setEnrollments(students)
        const ongoing = students.filter((s) => s.status === 'ongoing')

        setSubstituteCoverage(
          ongoing
            .filter((s) => s.covering_for)
            .sort((a, b) => (a.covering_until || '').localeCompare(b.covering_until || '')),
        )

        // Last logged class per enrollment, from every attendance record this trainer
        // has ever marked (also doubles as today's marks, below, so one fetch covers
        // both) — flags an ongoing enrollment that's gone quiet after it actually got
        // started (a brand-new enrollment with zero classes yet just hasn't started,
        // which is a different thing, so it's left out).
        const lastClassByEnrollment = {}
        allMarked.forEach((a) => {
          if (!lastClassByEnrollment[a.enrollment] || a.date > lastClassByEnrollment[a.enrollment]) {
            lastClassByEnrollment[a.enrollment] = a.date
          }
        })
        const now = new Date()
        setQuietStudents(
          ongoing
            .filter((s) => lastClassByEnrollment[s.id])
            .map((s) => ({ ...s, lastClassDate: lastClassByEnrollment[s.id], daysSince: daysBetween(lastClassByEnrollment[s.id], now) }))
            .filter((s) => s.daysSince >= NO_SESSION_ALERT_DAYS)
            .sort((a, b) => b.daysSince - a.daysSince),
        )
        const dayCode = todayDayCode()
        const scheduledToday = ongoing.filter((s) => (s.class_days || '').split(',').includes(dayCode))
        const markedEnrollmentIds = new Set(allMarked.filter((a) => a.date === today()).map((a) => a.enrollment))

        setTodaysClasses(
          scheduledToday
            .map((s) => ({ ...s, complete: markedEnrollmentIds.has(s.id) }))
            .sort((a, b) => (a.class_time || '').localeCompare(b.class_time || '')),
        )

        // Every remaining scheduled occurrence from today (if not yet marked) through
        // Sunday — not a count of days, a count of individual classes still to teach.
        const todayIdx = DAY_ORDER.indexOf(dayCode)
        let classesLeftThisWeek = 0
        const upcoming = []
        ongoing.forEach((s) => {
          const days = (s.class_days || '').split(',').filter(Boolean)
          days.forEach((d) => {
            const idx = DAY_ORDER.indexOf(d)
            if (idx === -1) return
            if (idx > todayIdx || (idx === todayIdx && !markedEnrollmentIds.has(s.id))) {
              classesLeftThisWeek += 1
            }
            // Today's occurrences are already shown in the Today's Classes table below —
            // this list is deliberately just the rest of the week, so it doesn't duplicate.
            if (idx > todayIdx) {
              upcoming.push({ ...s, dayCode: d, dayIdx: idx })
            }
          })
        })
        setRestOfWeek(upcoming.sort((a, b) => a.dayIdx - b.dayIdx || (a.class_time || '').localeCompare(b.class_time || '')))

        // Newest-first from the API — reverse the most recent 12 to chronological order
        // for the trend chart (oldest on the left), same convention as the admin
        // dashboard's client earnings trend.
        setEarningsHistory(earnings.slice(0, 12).reverse())

        const lastCycle = earnings.find(
          (p) => p.cycle_start !== current.cycle_start || p.cycle_end !== current.cycle_end,
        )
        setStats({
          ongoing: ongoing.length,
          current,
          lastCycle,
          pendingRequests: attendanceRequests.filter((r) => r.status === 'pending').length,
          approvedRequests: attendanceRequests.filter((r) => r.status === 'approved').length,
          classesLeftThisWeek,
          batchesCompleted: students.filter((s) => s.status === 'completed').length,
        })
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [api])

  const comparison = (() => {
    // Nothing marked yet in the current cycle isn't a "regression" to compare against
    // last cycle's total — it's just a cycle that opened moments ago.
    if (!stats || !stats.lastCycle || stats.current.total_classes === 0) return null
    const currentAmount = Number(stats.current.total_amount)
    const lastAmount = Number(stats.lastCycle.total_amount)
    const diff = currentAmount - lastAmount
    const percent = lastAmount !== 0 ? (diff / lastAmount) * 100 : null
    return { currentAmount, lastAmount, diff, percent }
  })()

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">My Dashboard</h1>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard label="Ongoing enrollments" value={stats ? stats.ongoing : '…'} accentClass="text-brand-violet" />
        <Card>
          <div className="text-sm text-gray-500">Current payout</div>
          <div className="flex items-baseline gap-2 mt-1 flex-wrap">
            <span className="text-3xl font-semibold text-brand-green">{stats ? `₹${stats.current.total_amount}` : '…'}</span>
            {comparison && (
              <span className={`text-sm font-medium ${comparison.diff >= 0 ? 'text-brand-green' : 'text-red-400'}`}>
                vs last payout {comparison.diff >= 0 ? '▲' : '▼'} ₹{Math.abs(comparison.diff)}
                {comparison.percent !== null ? ` (${comparison.diff >= 0 ? '+' : '-'}${Math.abs(comparison.percent).toFixed(0)}%)` : ''}
              </span>
            )}
          </div>
        </Card>
        <StatCard
          label="Classes left this week"
          value={stats ? stats.classesLeftThisWeek : '…'}
          accentClass="text-brand-violet"
        />
        <StatCard
          label="Late requests approved"
          value={stats ? stats.approvedRequests : '…'}
          accentClass="text-brand-blue"
        />
        {stats && stats.pendingRequests > 0 && (
          <Link to="/trainer/mark-attendance" className="block hover:opacity-80 transition-opacity">
            <StatCard label="Pending approval" value={stats.pendingRequests} accentClass="text-brand-amber" />
          </Link>
        )}
        <StatCard
          label="Batches completed"
          value={stats ? stats.batchesCompleted : '…'}
          accentClass="text-brand-green"
        />
      </div>

      {(substituteCoverage.length > 0 || quietStudents.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
          {substituteCoverage.length > 0 && (
            <Card className="p-0">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
                <h2 className="text-sm font-semibold text-navy">Covering for someone</h2>
                <span className="text-xs font-medium text-brand-violet bg-brand-violet/10 rounded-full px-2 py-0.5">
                  {substituteCoverage.length}
                </span>
              </div>
              <div>
                {substituteCoverage.map((s) => (
                  <div key={s.id} className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-gray-100 first:border-t-0">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-navy truncate">{s.student_name}</div>
                      <div className="text-xs text-text-secondary">{s.course_name}</div>
                    </div>
                    <div className="text-xs text-brand-violet whitespace-nowrap text-right">
                      Covering for {s.covering_for}
                      {s.covering_until && <div>until {formatDate(s.covering_until)}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {quietStudents.length > 0 && (
            <Card className="p-0">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
                <h2 className="text-sm font-semibold text-navy">No recent class</h2>
                <span className="text-xs font-medium text-brand-amber bg-brand-amber/10 rounded-full px-2 py-0.5">
                  {quietStudents.length}
                </span>
              </div>
              <div>
                {quietStudents.map((s) => (
                  <Link
                    key={s.id}
                    to={`/trainer/students/${s.student}`}
                    className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-gray-100 first:border-t-0 hover:bg-surface-sunken transition-colors duration-150 ease-out"
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-navy truncate">{s.student_name}</div>
                      <div className="text-xs text-text-secondary">{s.course_name}</div>
                    </div>
                    <div className="text-xs text-brand-amber whitespace-nowrap">
                      Last class {formatDate(s.lastClassDate)} · {s.daysSince}d ago
                    </div>
                  </Link>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {earningsHistory.length > 1 && (
        <>
          <h2 className="text-lg font-semibold text-navy mb-3">Payout trend</h2>
          <Card className="mb-8">
            <TrendChart
              xLabels={earningsHistory.map((h) => formatDate(h.cycle_start).slice(0, 5))}
              series={[
                { label: 'Classes', color: '#4338CA', values: earningsHistory.map((h) => Number(h.total_classes)) },
                { label: 'Payout', color: '#176B41', values: earningsHistory.map((h) => Number(h.total_amount)), prefix: '₹' },
              ]}
            />
          </Card>
        </>
      )}

      <h2 className="text-lg font-semibold text-navy mb-3">Weekly class schedule</h2>
      <Card className="p-0 overflow-x-auto mb-8">
        <WeeklyScheduleGrid enrollments={enrollments} />
      </Card>

      <h2 className="text-lg font-semibold text-navy mb-3">Today's Classes</h2>
      <Card className="p-0 overflow-x-auto mb-8">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">Time</th>
              <th className="table-head-cell">Student</th>
              <th className="table-head-cell">Course</th>
              <th className="table-head-cell">Batch</th>
              <th className="table-head-cell">Status</th>
            </tr>
          </thead>
          <tbody>
            {todaysClasses.map((s) => (
              <tr key={s.id} className="table-row">
                <td className="table-cell font-medium">{formatTime(s.class_time)}</td>
                <td className="table-cell">{s.student_name}</td>
                <td className="table-cell">{s.course_name}</td>
                <td className="table-cell">{s.batch_number}</td>
                <td className="table-cell">{s.complete ? <Badge status="complete" /> : <Badge status="incomplete" />}</td>
              </tr>
            ))}
            {todaysClasses.length === 0 && (
              <tr><td colSpan={5} className="table-cell text-center text-gray-400">No classes scheduled for today.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <h2 className="text-lg font-semibold text-navy mb-3">Rest of this week</h2>
      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">Day</th>
              <th className="table-head-cell">Time</th>
              <th className="table-head-cell">Student</th>
              <th className="table-head-cell">Course</th>
              <th className="table-head-cell">Batch</th>
            </tr>
          </thead>
          <tbody>
            {restOfWeek.map((s) => (
              <tr key={`${s.id}-${s.dayCode}`} className="table-row">
                <td className="table-cell font-medium">{DAY_OPTIONS.find((o) => o.code === s.dayCode)?.label}</td>
                <td className="table-cell">{formatTime(s.class_time)}</td>
                <td className="table-cell">{s.student_name}</td>
                <td className="table-cell">{s.course_name}</td>
                <td className="table-cell">{s.batch_number}</td>
              </tr>
            ))}
            {restOfWeek.length === 0 && (
              <tr><td colSpan={5} className="table-cell text-center text-gray-400">No more classes scheduled this week.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
