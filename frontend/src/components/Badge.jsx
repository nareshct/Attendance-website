const STYLES = {
  active: 'bg-success-tint text-success border-success-tint-border',
  ongoing: 'bg-success-tint text-success border-success-tint-border',
  present: 'bg-success-tint text-success border-success-tint-border',
  paid: 'bg-success-tint text-success border-success-tint-border',
  received: 'bg-success-tint text-success border-success-tint-border',
  complete: 'bg-success-tint text-success border-success-tint-border',
  approved: 'bg-success-tint text-success border-success-tint-border',
  completed: 'bg-info-tint text-info border-info-tint-border',
  closed: 'bg-info-tint text-info border-info-tint-border',
  absent: 'bg-error-tint text-error border-error-tint-border',
  denied: 'bg-error-tint text-error border-error-tint-border',
  overdue: 'bg-error-tint text-error border-error-tint-border',
  withdrawn: 'bg-error-tint text-error border-error-tint-border',
  cancelled: 'bg-error-tint text-error border-error-tint-border',
  pending: 'bg-warning-tint text-warning border-warning-tint-border',
  incomplete: 'bg-warning-tint text-warning border-warning-tint-border',
  open: 'bg-warning-tint text-warning border-warning-tint-border',
}

// Statuses with no real "in-progress/health" meaning read better as a
// plain neutral chip than with a colored status dot.
const NEUTRAL = new Set(['archived'])

export function Badge({ status }) {
  const style = STYLES[status] || 'bg-gray-100 text-text-secondary border-gray-200'
  const isNeutral = NEUTRAL.has(status) || !STYLES[status]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${style}`}
    >
      {!isNeutral && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" aria-hidden="true" />}
      {status}
    </span>
  )
}
