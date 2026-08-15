import { useEffect, useState } from 'react'
import { Card, StatCard } from '../../components/Card'
import { TrendChart } from '../../components/TrendChart'
import { useApi } from '../../hooks/useApi'
import { formatDate, formatDateRange } from '../../utils/date'

export default function ClientDashboard() {
  const api = useApi()
  const [profile, setProfile] = useState(null)
  const [currentCycle, setCurrentCycle] = useState(null)
  const [history, setHistory] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    Promise.all([
      api('/api/my-client-profile/'),
      api('/api/my-client-billing/current/'),
      api('/api/my-client-billing/history/?limit=12'),
    ])
      .then(([p, c, h]) => {
        if (cancelled) return
        setProfile(p)
        setCurrentCycle(c)
        setHistory(h)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [api])

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">Dashboard</h1>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard label="Active students" value={profile ? profile.active_student_count : '…'} accentClass="text-navy" />
        <StatCard label="Overdue invoices" value={profile ? profile.overdue_invoice_count : '…'} accentClass="text-error" />
        <StatCard label="Pending amount" value={profile ? `₹${profile.pending_amount}` : '…'} accentClass="text-warning" />
        <StatCard
          label="Current cycle classes"
          value={currentCycle ? currentCycle.current_classes : '…'}
          accentClass="text-client"
        />
      </div>

      {currentCycle && (
        <Card>
          <h2 className="text-sm font-semibold text-navy mb-3">Current billing cycle</h2>
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div>
              <dt className="text-text-secondary">Cycle</dt>
              <dd>{formatDateRange(currentCycle.cycle_start, currentCycle.cycle_end)}</dd>
            </div>
            <div>
              <dt className="text-text-secondary">Classes so far</dt>
              <dd className="tabular-nums">{currentCycle.current_classes}</dd>
            </div>
            <div>
              <dt className="text-text-secondary">Billed so far</dt>
              <dd className="tabular-nums">
                ₹{currentCycle.current_cycle_billed}
                {currentCycle.carried_forward_count > 0 && (
                  <div className="text-xs text-warning">
                    incl. ₹{currentCycle.carried_forward_amount} from {currentCycle.carried_forward_count} late-approved class{currentCycle.carried_forward_count === 1 ? '' : 'es'}
                  </div>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-text-secondary">Total owed (incl. pending invoices)</dt>
              <dd className="tabular-nums font-semibold text-navy">₹{currentCycle.billed_to_client}</dd>
            </div>
          </dl>
        </Card>
      )}

      {history.length > 1 && (
        <>
          <h2 className="text-lg font-semibold text-navy mb-3 mt-8">Billing trend</h2>
          <Card>
            <TrendChart
              xLabels={history.map((h) => formatDate(h.cycle_start).slice(0, 5))}
              series={[
                { label: 'Classes', color: '#4338CA', values: history.map((h) => Number(h.total_classes)) },
                { label: 'Billed', color: '#176B41', values: history.map((h) => Number(h.total_revenue)), prefix: '₹' },
              ]}
            />
          </Card>
        </>
      )}
    </div>
  )
}
