export function Card({ children, className = '' }) {
  return <div className={`bg-white rounded-xl shadow-xs border border-gray-200 p-6 ${className}`}>{children}</div>
}

export function StatCard({ label, value, accentClass = 'text-primary', valueClass = 'text-[26px] font-bold tracking-tight' }) {
  return (
    <Card>
      <div className="text-xs font-medium text-text-secondary">{label}</div>
      <div className={`${valueClass} mt-1.5 tabular-nums ${accentClass}`}>{value}</div>
    </Card>
  )
}
