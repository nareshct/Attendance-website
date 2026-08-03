export function Card({ children, className = '' }) {
  return <div className={`bg-white rounded-xl shadow-sm border border-gray-200 p-5 ${className}`}>{children}</div>
}

export function StatCard({ label, value, accentClass = 'text-brand-blue', valueClass = 'text-3xl font-semibold' }) {
  return (
    <Card>
      <div className="text-sm text-gray-500">{label}</div>
      <div className={`${valueClass} mt-1 ${accentClass}`}>{value}</div>
    </Card>
  )
}
