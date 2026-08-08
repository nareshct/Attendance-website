import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArchiveClientModal } from '../../components/ArchiveClientModal'
import { Button } from '../../components/Button'
import { Card, StatCard } from '../../components/Card'
import { Modal } from '../../components/Modal'
import { useApi } from '../../hooks/useApi'

const EMPTY_FORM = { company_name: '', contact_phone: '', contact_email: '', rate_per_class: '' }

export default function ClientsPage() {
  const api = useApi()
  const [clients, setClients] = useState([])
  const [summary, setSummary] = useState(null)
  const [search, setSearch] = useState('')
  const [statusTab, setStatusTab] = useState('active')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const loadClients = useCallback(async () => {
    setClients(await api('/api/clients/'))
  }, [api])

  const loadSummary = useCallback(() => {
    return api('/api/clients/summary/').then(setSummary)
  }, [api])

  useEffect(() => {
    loadClients().catch((err) => setError(err.message))
    loadSummary().catch(() => {})
  }, [loadClients, loadSummary])

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await api('/api/clients/', { method: 'POST', body: form })
      setForm(EMPTY_FORM)
      setShowForm(false)
      await loadClients()
      await loadSummary()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const [archiveTarget, setArchiveTarget] = useState(null)

  function handleArchived() {
    loadClients()
    loadSummary()
  }

  async function handleUnarchive(id) {
    await api(`/api/clients/${id}/unarchive/`, { method: 'POST' })
    await loadClients()
    await loadSummary()
  }

  const filtered = clients.filter((c) => {
    const matchesSearch = c.company_name.toLowerCase().includes(search.toLowerCase())
    const matchesStatus = c.status === statusTab
    return matchesSearch && matchesStatus
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-navy">Clients (B2B)</h1>
        <Button onClick={() => setShowForm(true)}>+ Add client</Button>
      </div>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <StatCard label="Total pending" value={summary ? `₹${summary.total_pending_amount}` : '…'} accentClass="text-warning" />
        <StatCard label="Total earning" value={summary ? `₹${summary.total_earning}` : '…'} accentClass="text-success" />
        <StatCard label="Total classes taken" value={summary ? summary.total_classes : '…'} accentClass="text-navy" />
      </div>

      <Modal open={showForm} onClose={() => setShowForm(false)} title="Add client" maxWidthClass="max-w-2xl">
        <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <input required placeholder="Company name" value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} className="input" />
          <input required placeholder="Contact phone" value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} className="input" />
          <input placeholder="Contact email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} className="input" />
          <input required type="number" step="0.01" placeholder="Rate per class (₹)" value={form.rate_per_class} onChange={(e) => setForm({ ...form, rate_per_class: e.target.value })} className="input" />
          {error && <p className="sm:col-span-3 text-error text-xs">{error}</p>}
          <div className="sm:col-span-3 flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="success" disabled={submitting}>
              {submitting ? 'Saving…' : 'Save client'}
            </Button>
          </div>
        </form>
      </Modal>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <input
          placeholder="Search by company name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input max-w-sm"
        />
        <div className="flex gap-2 shrink-0">
          {['active', 'archived'].map((t) => (
            <Button key={t} variant={statusTab === t ? 'primary' : 'secondary'} className="capitalize" onClick={() => setStatusTab(t)}>
              {t}
            </Button>
          ))}
        </div>
      </div>

      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">Company</th>
              <th className="table-head-cell">Phone</th>
              <th className="table-head-cell">Active students</th>
              <th className="table-head-cell">Payin pending</th>
              <th className="table-head-cell">Overdue invoices</th>
              <th className="table-head-cell"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((c) => (
              <tr key={c.id} className="table-row">
                <td className="table-cell">
                  <Link to={`/admin/clients/${c.id}`} className="font-medium text-primary hover:underline focus-ring">{c.company_name}</Link>
                </td>
                <td className="table-cell">{c.contact_phone}</td>
                <td className="table-cell tabular-nums">{c.active_student_count}</td>
                <td className="table-cell tabular-nums text-warning font-medium">₹{c.pending_amount}</td>
                <td className="table-cell tabular-nums">
                  {c.overdue_invoice_count > 0 ? (
                    <span className="text-error font-medium">{c.overdue_invoice_count}</span>
                  ) : (
                    c.overdue_invoice_count
                  )}
                </td>
                <td className="table-cell text-right">
                  {c.status === 'active' ? (
                    <button onClick={() => setArchiveTarget(c)} className="text-xs text-text-secondary hover:text-error focus-ring">
                      Archive
                    </button>
                  ) : (
                    <button onClick={() => handleUnarchive(c.id)} className="text-xs text-text-secondary hover:text-success focus-ring">
                      Unarchive
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-text-tertiary">No clients found.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <ArchiveClientModal
        open={Boolean(archiveTarget)}
        clientId={archiveTarget?.id}
        clientName={archiveTarget?.company_name}
        onClose={() => setArchiveTarget(null)}
        onArchived={handleArchived}
      />
    </div>
  )
}
