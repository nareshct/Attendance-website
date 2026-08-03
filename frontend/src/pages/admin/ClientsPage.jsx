import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/Badge'
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

  async function loadClients() {
    setClients(await api('/api/clients/'))
  }

  function loadSummary() {
    return api('/api/clients/summary/').then(setSummary)
  }

  useEffect(() => {
    loadClients().catch((err) => setError(err.message))
    loadSummary().catch(() => {})
  }, [api])

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

  async function handleArchive(id) {
    await api(`/api/clients/${id}/archive/`, { method: 'POST' })
    await loadClients()
    await loadSummary()
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
        <button onClick={() => setShowForm(true)} className="text-sm rounded-lg bg-brand-blue text-white px-4 py-2 hover:bg-blue-800">
          + Add client
        </button>
      </div>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <StatCard label="Total pending" value={summary ? `₹${summary.total_pending_amount}` : '…'} accentClass="text-brand-amber" />
        <StatCard label="Total earning" value={summary ? `₹${summary.total_earning}` : '…'} accentClass="text-brand-green" />
        <StatCard label="Total classes taken" value={summary ? summary.total_classes : '…'} accentClass="text-brand-blue" />
      </div>

      <Modal open={showForm} onClose={() => setShowForm(false)} title="Add client" maxWidthClass="max-w-2xl">
        <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <input required placeholder="Company name" value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} className="input" />
          <input required placeholder="Contact phone" value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} className="input" />
          <input placeholder="Contact email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} className="input" />
          <input required type="number" step="0.01" placeholder="Rate per class (₹)" value={form.rate_per_class} onChange={(e) => setForm({ ...form, rate_per_class: e.target.value })} className="input" />
          {error && <p className="sm:col-span-3 text-red-600 text-xs">{error}</p>}
          <div className="sm:col-span-3 flex justify-end gap-3">
            <button type="button" onClick={() => setShowForm(false)} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button disabled={submitting} type="submit" className="rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800 disabled:opacity-60">
              {submitting ? 'Saving…' : 'Save client'}
            </button>
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
            <button
              key={t}
              onClick={() => setStatusTab(t)}
              className={`text-sm rounded-lg px-4 py-2 capitalize ${
                statusTab === t ? 'bg-brand-blue text-white' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <Card className="p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-left">
            <tr>
              <th className="px-4 py-3">Company</th>
              <th className="px-4 py-3">Phone</th>
              <th className="px-4 py-3">Pending amount</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((c) => (
              <tr key={c.id} className="border-t border-gray-100">
                <td className="px-4 py-3">
                  <Link to={`/admin/clients/${c.id}`} className="text-brand-blue hover:underline">{c.company_name}</Link>
                </td>
                <td className="px-4 py-3">{c.contact_phone}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span>₹{c.pending_amount}</span>
                    {c.has_overdue_invoice && <Badge status="overdue" />}
                  </div>
                </td>
                <td className="px-4 py-3 text-right">
                  {c.status === 'active' ? (
                    <button onClick={() => handleArchive(c.id)} className="text-xs text-gray-500 hover:text-red-600">
                      Archive
                    </button>
                  ) : (
                    <button onClick={() => handleUnarchive(c.id)} className="text-xs text-gray-500 hover:text-brand-green">
                      Unarchive
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-gray-400">No clients found.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
