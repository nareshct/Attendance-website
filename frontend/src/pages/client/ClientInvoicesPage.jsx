import { useEffect, useState } from 'react'
import { downloadFile } from '../../api/client'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import { useAuth } from '../../hooks/useAuth'
import { useApi } from '../../hooks/useApi'
import { formatDateRange } from '../../utils/date'

export default function ClientInvoicesPage() {
  const api = useApi()
  const { auth } = useAuth()
  const [invoices, setInvoices] = useState([])
  const [currentCycle, setCurrentCycle] = useState(null)
  const [downloadingId, setDownloadingId] = useState(null)
  const [downloadingCsvKey, setDownloadingCsvKey] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    Promise.all([api('/api/my-client-invoices/'), api('/api/my-client-billing/current/')])
      .then(([inv, cycle]) => {
        if (cancelled) return
        setInvoices(inv)
        setCurrentCycle(cycle)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [api])

  async function handleDownload(invoiceId) {
    setDownloadingId(invoiceId)
    setError('')
    try {
      await downloadFile(`/api/my-client-invoices/${invoiceId}/pdf/`, auth.token)
    } catch (err) {
      setError(err.message)
    } finally {
      setDownloadingId(null)
    }
  }

  async function handleDownloadCsv(key, start, end) {
    setDownloadingCsvKey(key)
    setError('')
    try {
      await downloadFile(`/api/reports/my-client-attendance/?start=${start}&end=${end}`, auth.token)
    } catch (err) {
      setError(err.message)
    } finally {
      setDownloadingCsvKey(null)
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">Invoices</h1>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">Cycle</th>
              <th className="table-head-cell">Classes</th>
              <th className="table-head-cell">Amount</th>
              <th className="table-head-cell">Status</th>
              <th className="table-head-cell text-center">Download</th>
            </tr>
          </thead>
          <tbody>
            {currentCycle && (
              <tr className="table-row bg-warning-tint/50">
                <td className="table-cell">{formatDateRange(currentCycle.cycle_start, currentCycle.cycle_end)}</td>
                <td className="table-cell tabular-nums">{currentCycle.current_classes}</td>
                <td className="table-cell tabular-nums">
                  ₹{currentCycle.current_cycle_billed}
                  {currentCycle.carried_forward_count > 0 && (
                    <div className="text-xs text-warning">
                      incl. ₹{currentCycle.carried_forward_amount} from {currentCycle.carried_forward_count} late-approved class{currentCycle.carried_forward_count === 1 ? '' : 'es'}
                    </div>
                  )}
                </td>
                <td className="table-cell"><Badge status="open" /></td>
                <td className="table-cell text-center">
                  <button
                    disabled={downloadingCsvKey === 'current'}
                    onClick={() => handleDownloadCsv('current', currentCycle.cycle_start, currentCycle.cycle_end)}
                    className="text-xs font-medium text-text-secondary hover:text-primary disabled:opacity-60 focus-ring"
                  >
                    {downloadingCsvKey === 'current' ? 'Downloading…' : 'Attendance (CSV)'}
                  </button>
                </td>
              </tr>
            )}
            {invoices.map((inv) => (
              <tr key={inv.id} className="table-row">
                <td className="table-cell">{formatDateRange(inv.cycle_start, inv.cycle_end)}</td>
                <td className="table-cell tabular-nums">{inv.total_classes}</td>
                <td className="table-cell tabular-nums">
                  ₹{inv.total_amount}
                  {Number(inv.carried_forward_amount) > 0 && (
                    <div className="text-xs text-text-tertiary">(incl. ₹{inv.carried_forward_amount} carried forward)</div>
                  )}
                </td>
                <td className="table-cell">
                  <Badge status={inv.is_overdue ? 'overdue' : inv.status} />
                </td>
                <td className="table-cell text-center whitespace-nowrap">
                  <button
                    disabled={downloadingId === inv.id}
                    onClick={() => handleDownload(inv.id)}
                    className="text-xs font-medium text-text-secondary hover:text-primary disabled:opacity-60 focus-ring"
                  >
                    {downloadingId === inv.id ? 'Downloading…' : 'Invoice (PDF)'}
                  </button>
                  {' · '}
                  <button
                    disabled={downloadingCsvKey === inv.id}
                    onClick={() => handleDownloadCsv(inv.id, inv.cycle_start, inv.cycle_end)}
                    className="text-xs font-medium text-text-secondary hover:text-primary disabled:opacity-60 focus-ring"
                  >
                    {downloadingCsvKey === inv.id ? 'Downloading…' : 'Attendance (CSV)'}
                  </button>
                </td>
              </tr>
            ))}
            {!loading && invoices.length === 0 && !currentCycle && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">No invoices yet.</td></tr>
            )}
            {loading && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">Loading…</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
