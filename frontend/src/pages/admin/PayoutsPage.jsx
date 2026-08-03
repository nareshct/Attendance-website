import { useEffect, useState } from 'react'
import { downloadFile } from '../../api/client'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import { useAuth } from '../../context/AuthContext'
import { useApi } from '../../hooks/useApi'
import { formatDateRange } from '../../utils/date'

export default function PayoutsPage() {
  const api = useApi()
  const { auth } = useAuth()
  const [cycles, setCycles] = useState([])
  const [payouts, setPayouts] = useState([])
  const [currentPayouts, setCurrentPayouts] = useState({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [showAllCycles, setShowAllCycles] = useState(false)

  async function loadAll() {
    const [c, p] = await Promise.all([api('/api/billing-cycles/'), api('/api/payouts/')])
    setCycles(c)
    setPayouts(p)

    const openCycles = c.filter((cycle) => cycle.status === 'open')
    const previews = await Promise.all(
      openCycles.map((cycle) => api(`/api/billing-cycles/${cycle.id}/current_payouts/`))
    )
    const previewsByCycle = {}
    openCycles.forEach((cycle, i) => {
      previewsByCycle[cycle.id] = previews[i]
    })
    setCurrentPayouts(previewsByCycle)
  }

  useEffect(() => {
    loadAll().catch((err) => setError(err.message))
  }, [api])

  async function handleGenerateCurrent() {
    setBusy(true)
    setError('')
    try {
      await api('/api/billing-cycles/generate_current/', { method: 'POST' })
      await loadAll()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleClose(cycleId) {
    setBusy(true)
    setError('')
    try {
      await api(`/api/billing-cycles/${cycleId}/close/`, { method: 'POST' })
      await loadAll()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleMarkPaid(payoutId) {
    setBusy(true)
    setError('')
    try {
      await api(`/api/payouts/${payoutId}/mark_paid/`, { method: 'POST' })
      await loadAll()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleExport() {
    setBusy(true)
    setError('')
    try {
      await downloadFile('/api/reports/payouts/', auth.token)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-navy">Payouts</h1>
        <button disabled={busy} onClick={handleGenerateCurrent} className="text-sm rounded-lg bg-brand-blue text-white px-4 py-2 hover:bg-blue-800 disabled:opacity-60">
          Generate current cycle
        </button>
      </div>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-navy">Billing cycles &amp; payouts</h2>
        <div className="flex items-center gap-4">
          {cycles.length > 3 && (
            <button onClick={() => setShowAllCycles((v) => !v)} className="text-xs text-brand-blue hover:underline">
              {showAllCycles ? 'Show recent only' : `Show all (${cycles.length})`}
            </button>
          )}
          <button disabled={busy} onClick={handleExport} className="text-xs text-brand-blue hover:underline disabled:opacity-60">
            Export CSV
          </button>
        </div>
      </div>

      {(showAllCycles ? cycles : cycles.slice(0, 3)).map((c) => {
        const isOpen = c.status === 'open'
        const cyclePayouts = isOpen ? (currentPayouts[c.id] || []) : payouts.filter((p) => p.cycle === c.id)
        return (
          <Card key={c.id} className="p-0 overflow-hidden mb-6">
            <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-100">
              <div className="flex items-center gap-3">
                <span className="font-medium text-navy">{formatDateRange(c.cycle_start, c.cycle_end)}</span>
                <Badge status={c.status} />
                {isOpen && <span className="text-xs text-gray-400">Live totals — updates as attendance is marked</span>}
              </div>
              {isOpen && (
                <button disabled={busy} onClick={() => handleClose(c.id)} className="text-xs text-brand-green hover:underline disabled:opacity-60">
                  Close &amp; calculate payouts
                </button>
              )}
            </div>
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-left">
                <tr>
                  <th className="px-4 py-3">Trainer</th>
                  <th className="px-4 py-3">Classes</th>
                  <th className="px-4 py-3">Amount</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {cyclePayouts.map((p) => (
                  <tr key={isOpen ? p.trainer : p.id} className="border-t border-gray-100">
                    <td className="px-4 py-3">{p.trainer_name}</td>
                    <td className="px-4 py-3">{p.total_classes}</td>
                    <td className="px-4 py-3">
                      ₹{p.total_amount}
                      {Number(p.carried_forward_amount) > 0 && (
                        <div className="text-xs text-gray-400">(incl. ₹{p.carried_forward_amount} carried forward)</div>
                      )}
                    </td>
                    <td className="px-4 py-3">{isOpen ? <Badge status="open" /> : <Badge status={p.paid_status} />}</td>
                    <td className="px-4 py-3 text-right">
                      {!isOpen && p.paid_status === 'pending' && (
                        <button disabled={busy} onClick={() => handleMarkPaid(p.id)} className="text-xs text-brand-blue hover:underline disabled:opacity-60">
                          Mark as paid
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {cyclePayouts.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-6 text-center text-gray-400">
                    {isOpen ? 'No attendance marked yet in this cycle.' : 'No payouts for this cycle.'}
                  </td></tr>
                )}
              </tbody>
            </table>
          </Card>
        )
      })}
      {cycles.length === 0 && (
        <Card className="p-6 text-center text-gray-400">No billing cycles yet.</Card>
      )}
    </div>
  )
}
