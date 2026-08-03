const STYLES = {
  active: 'bg-green-100 text-brand-green',
  ongoing: 'bg-green-100 text-brand-green',
  present: 'bg-green-100 text-brand-green',
  paid: 'bg-green-100 text-brand-green',
  received: 'bg-green-100 text-brand-green',
  complete: 'bg-green-100 text-brand-green',
  approved: 'bg-green-100 text-brand-green',
  archived: 'bg-gray-100 text-gray-600',
  completed: 'bg-blue-100 text-brand-blue',
  closed: 'bg-blue-100 text-brand-blue',
  absent: 'bg-red-100 text-red-700',
  denied: 'bg-red-100 text-red-700',
  overdue: 'bg-red-100 text-red-700',
  withdrawn: 'bg-red-100 text-red-700',
  cancelled: 'bg-red-100 text-red-700',
  pending: 'bg-amber-100 text-brand-amber',
  incomplete: 'bg-amber-100 text-brand-amber',
  open: 'bg-amber-100 text-brand-amber',
}

export function Badge({ status }) {
  const style = STYLES[status] || 'bg-gray-100 text-gray-600'
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${style}`}>{status}</span>
}
