import { DAY_OPTIONS, formatTime } from '../utils/schedule'

const SCHEDULE_DAYS = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
  .map((code) => DAY_OPTIONS.find((d) => d.code === code))

// Full 24-hour range (7 AM through 11 PM, then wrapping to 12 AM - 6 AM), in display order.
const ALL_HOURS = [...Array.from({ length: 17 }, (_, i) => i + 7), ...Array.from({ length: 7 }, (_, i) => i)]
// Default visible range — no coaching center runs classes at 2 AM, so the middle-of-the-night
// rows are only shown if a class is actually scheduled there (see hours below).
const BUSINESS_HOURS = new Set(Array.from({ length: 15 }, (_, i) => i + 7)) // 7 AM - 9 PM

function buildScheduleGrid(enrollments) {
  const grid = {}
  DAY_OPTIONS.forEach((d) => { grid[d.code] = {} })
  enrollments
    .filter((e) => e.status === 'ongoing' && e.class_time && e.class_days)
    .forEach((e) => {
      const hour = Number(e.class_time.split(':')[0])
      e.class_days.split(',').forEach((day) => {
        if (!grid[day]) return
        if (!grid[day][hour]) grid[day][hour] = []
        grid[day][hour].push(e)
      })
    })
  return grid
}

export function WeeklyScheduleGrid({ enrollments }) {
  const scheduleGrid = buildScheduleGrid(enrollments)
  const hoursWithEntries = new Set()
  Object.values(scheduleGrid).forEach((byHour) => Object.keys(byHour).forEach((h) => hoursWithEntries.add(Number(h))))
  const HOURS = ALL_HOURS.filter((h) => BUSINESS_HOURS.has(h) || hoursWithEntries.has(h))

  return (
    <table className="w-full table-fixed text-xs border-2 border-gray-400 border-collapse">
      <thead>
        <tr>
          <th className="w-20 px-2 py-2 text-center whitespace-nowrap border-2 border-gray-400 font-semibold bg-amber-100 text-amber-800">Time</th>
          {SCHEDULE_DAYS.map((d) => (
            <th key={d.code} className="px-2 py-2 text-center border-2 border-gray-400 font-semibold bg-blue-100 text-blue-800">{d.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {HOURS.map((h) => (
          <tr key={h}>
            <td className="px-2 py-1.5 text-center text-amber-700 bg-amber-50 font-medium whitespace-nowrap border-2 border-gray-400">
              {formatTime(`${String(h).padStart(2, '0')}:00`)}
            </td>
            {SCHEDULE_DAYS.map((d) => {
              const entries = scheduleGrid[d.code]?.[h] || []
              return (
                <td key={d.code} className="px-2 py-1.5 align-top border-2 border-gray-400 text-center">
                  {entries.map((e) => (
                    <div key={e.id} className="rounded bg-emerald-100 text-emerald-700 px-1.5 py-1 mb-1 leading-tight">
                      {e.student_name}
                      <div className="text-[10px] text-emerald-600">{e.course_name}</div>
                    </div>
                  ))}
                </td>
              )
            })}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
