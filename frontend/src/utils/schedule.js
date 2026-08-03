export const DAY_OPTIONS = [
  { code: 'MON', label: 'Mon' },
  { code: 'TUE', label: 'Tue' },
  { code: 'WED', label: 'Wed' },
  { code: 'THU', label: 'Thu' },
  { code: 'FRI', label: 'Fri' },
  { code: 'SAT', label: 'Sat' },
  { code: 'SUN', label: 'Sun' },
]

// Indexed by Date#getDay() (0 = Sunday ... 6 = Saturday).
const DAY_CODES_BY_JS_DAY = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']

export function todayDayCode() {
  return DAY_CODES_BY_JS_DAY[new Date().getDay()]
}

export function formatDays(classDays) {
  if (!classDays) return '—'
  const codes = classDays.split(',')
  return DAY_OPTIONS.filter((d) => codes.includes(d.code)).map((d) => d.label).join(', ')
}

export function formatTime(classTime) {
  if (!classTime) return ''
  const [h, m] = classTime.split(':').map(Number)
  const period = h >= 12 ? 'PM' : 'AM'
  const hour12 = h % 12 === 0 ? 12 : h % 12
  return `${hour12}:${String(m).padStart(2, '0')} ${period}`
}
