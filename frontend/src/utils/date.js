export function formatDate(value) {
  if (!value) return ''
  const datePart = String(value).slice(0, 10)
  const [y, m, d] = datePart.split('-')
  if (!y || !m || !d) return value
  return `${d}/${m}/${y}`
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

export function formatWeekday(value) {
  if (!value) return ''
  const [y, m, d] = String(value).slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return ''
  return WEEKDAYS[new Date(y, m - 1, d).getDay()]
}

export function formatDateRange(start, end) {
  return `${formatDate(start)} – ${formatDate(end)}`
}

export function formatDateTime(value) {
  if (!value) return ''
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return ''
  const d = String(dt.getDate()).padStart(2, '0')
  const m = String(dt.getMonth() + 1).padStart(2, '0')
  const y = dt.getFullYear()
  const time = dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return `${d}/${m}/${y}, ${time}`
}
