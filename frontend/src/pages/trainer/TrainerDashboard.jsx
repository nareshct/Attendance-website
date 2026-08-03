import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { Card, StatCard } from '../../components/Card'
import { WeeklyScheduleGrid } from '../../components/WeeklyScheduleGrid'
import { useApi } from '../../hooks/useApi'
import { DAY_OPTIONS, formatTime, todayDayCode } from '../../utils/schedule'

const DAY_ORDER = DAY_OPTIONS.map((d) => d.code)

const today = () => new Date().toISOString().slice(0, 10)

export default function TrainerDashboard() {
  const api = useApi()
  const [stats, setStats] = useState(null)
  const [todaysClasses, setTodaysClasses] = useState([])
  const [enrollments, setEnrollments] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [students, earnings, current, markedToday, attendanceRequests, materials] = await Promise.all([
          api('/api/my-students/'),
          api('/api/my-earnings/'),
          api('/api/my-earnings/current/'),
          api(`/api/attendance/?date=${today()}`),
          api('/api/attendance-requests/'),
          api('/api/course-materials/'),
        ])
        if (cancelled) return

        setEnrollments(students)
        const ongoing = students.filter((s) => s.status === 'ongoing')
        const dayCode = todayDayCode()
        const scheduledToday = ongoing.filter((s) => (s.class_days || '').split(',').includes(dayCode))
        const markedEnrollmentIds = new Set(markedToday.map((a) => a.enrollment))

        setTodaysClasses(
          scheduledToday
            .map((s) => ({ ...s, complete: markedEnrollmentIds.has(s.id) }))
            .sort((a, b) => (a.class_time || '').localeCompare(b.class_time || '')),
        )

        // Every remaining scheduled occurrence from today (if not yet marked) through
        // Sunday — not a count of days, a count of individual classes still to teach.
        const todayIdx = DAY_ORDER.indexOf(dayCode)
        let classesLeftThisWeek = 0
        ongoing.forEach((s) => {
          const days = (s.class_days || '').split(',').filter(Boolean)
          days.forEach((d) => {
            const idx = DAY_ORDER.indexOf(d)
            if (idx === -1) return
            if (idx > todayIdx || (idx === todayIdx && !markedEnrollmentIds.has(s.id))) {
              classesLeftThisWeek += 1
            }
          })
        })

        const courseIds = new Set(ongoing.map((s) => s.course))
        const materialsForMyCourses = materials.filter((m) => courseIds.has(m.course)).length

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
          materialsForMyCourses,
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
        <Link to="/trainer/course-materials" className="block hover:opacity-80 transition-opacity">
          <StatCard
            label="Materials for your courses"
            value={stats ? stats.materialsForMyCourses : '…'}
            accentClass="text-brand-blue"
          />
        </Link>
      </div>

      <h2 className="text-lg font-semibold text-navy mb-3">Weekly class schedule</h2>
      <Card className="p-0 overflow-x-auto mb-8">
        <WeeklyScheduleGrid enrollments={enrollments} />
      </Card>

      <h2 className="text-lg font-semibold text-navy mb-3">Today's Classes</h2>
      <Card className="p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-left">
            <tr>
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Student</th>
              <th className="px-4 py-3">Course</th>
              <th className="px-4 py-3">Batch</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {todaysClasses.map((s) => (
              <tr key={s.id} className="border-t border-gray-100">
                <td className="px-4 py-3 font-medium">{formatTime(s.class_time)}</td>
                <td className="px-4 py-3">{s.student_name}</td>
                <td className="px-4 py-3">{s.course_name}</td>
                <td className="px-4 py-3">{s.batch_number}</td>
                <td className="px-4 py-3">{s.complete ? <Badge status="complete" /> : <Badge status="incomplete" />}</td>
              </tr>
            ))}
            {todaysClasses.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-gray-400">No classes scheduled for today.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
