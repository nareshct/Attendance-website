import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import { Modal } from '../../components/Modal'
import { useApi } from '../../hooks/useApi'

const EMPTY_FORM = { name: '', phone_number: '', place: '', username: '', password: '', default_rate_per_class: '' }

export default function TrainersPage() {
  const api = useApi()
  const [trainers, setTrainers] = useState([])
  const [courses, setCourses] = useState([])
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [statusTab, setStatusTab] = useState('active')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [rates, setRates] = useState([])
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const loadTrainers = useCallback(async () => {
    const path = debouncedSearch ? `/api/trainers/?search=${encodeURIComponent(debouncedSearch)}` : '/api/trainers/'
    setTrainers(await api(path))
  }, [api, debouncedSearch])

  // Debounced so rapid typing doesn't fire a request per keystroke — the actual search
  // runs server-side (see TrainerViewSet.search_fields), so it always covers every
  // trainer regardless of how many pages have been loaded.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    loadTrainers().catch((err) => setError(err.message))
  }, [loadTrainers])

  useEffect(() => {
    api('/api/courses/').then(setCourses).catch(() => {})
  }, [api])

  // Search is already applied server-side (see loadTrainers above) — this only layers
  // the status tab on top of the already-matching results.
  const filtered = trainers.filter((t) => t.status === statusTab)

  function updateRate(index, field, value) {
    setRates((rs) => rs.map((r, i) => (i === index ? { ...r, [field]: value } : r)))
  }

  function removeRate(index) {
    setRates((rs) => rs.filter((_, i) => i !== index))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const validRates = rates
        .filter((r) => r.course && r.rate_per_class)
        .map((r) => ({ course: Number(r.course), rate_per_class: r.rate_per_class }))
      await api('/api/trainers/', { method: 'POST', body: { ...form, rates: validRates } })
      setForm(EMPTY_FORM)
      setRates([])
      setShowForm(false)
      await loadTrainers()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleArchive(id) {
    await api(`/api/trainers/${id}/archive/`, { method: 'POST' })
    await loadTrainers()
  }

  async function handleUnarchive(id) {
    await api(`/api/trainers/${id}/unarchive/`, { method: 'POST' })
    await loadTrainers()
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-navy">Trainers</h1>
        <button onClick={() => setShowForm(true)} className="text-sm rounded-lg bg-brand-blue text-white px-4 py-2 hover:bg-blue-800">
          + Onboard trainer
        </button>
      </div>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <Modal open={showForm} onClose={() => setShowForm(false)} title="Onboard trainer" maxWidthClass="max-w-2xl">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input required placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="input" />
            <input required placeholder="Phone number" value={form.phone_number} onChange={(e) => setForm({ ...form, phone_number: e.target.value })} className="input" />
            <input required placeholder="Place" value={form.place} onChange={(e) => setForm({ ...form, place: e.target.value })} className="input" />
            <div />
            <input required placeholder="Login username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="input" />
            <input required type="password" placeholder="Login password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="input" />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Default rate per class (₹)</label>
            <p className="text-xs text-gray-500 mb-2">Applies to every course this trainer teaches, unless overridden below.</p>
            <input
              required
              placeholder="e.g. 100"
              type="number"
              step="0.01"
              value={form.default_rate_per_class}
              onChange={(e) => setForm({ ...form, default_rate_per_class: e.target.value })}
              className="input max-w-xs"
            />
          </div>

          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Course-specific overrides (optional)</p>
            <p className="text-xs text-gray-500 mb-2">Only add a line here if a course should pay a different rate than the default.</p>
            <div className="space-y-2">
              {rates.map((r, i) => (
                <div key={i} className="flex gap-2">
                  <select value={r.course} onChange={(e) => updateRate(i, 'course', e.target.value)} className="input">
                    <option value="">Select course…</option>
                    {courses.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                  <input
                    placeholder="Rate per class (₹)"
                    type="number"
                    step="0.01"
                    value={r.rate_per_class}
                    onChange={(e) => updateRate(i, 'rate_per_class', e.target.value)}
                    className="input"
                  />
                  <button type="button" onClick={() => removeRate(i)} className="text-xs text-red-600 hover:underline shrink-0">
                    Remove
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setRates((rs) => [...rs, { course: '', rate_per_class: '' }])}
              className="text-xs text-brand-blue hover:underline mt-2"
            >
              + Add course override
            </button>
          </div>

          {error && <p className="text-red-600 text-xs">{error}</p>}
          <div className="flex justify-end gap-3">
            <button type="button" onClick={() => setShowForm(false)} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button disabled={submitting} type="submit" className="rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800 disabled:opacity-60">
              {submitting ? 'Saving…' : 'Save trainer'}
            </button>
          </div>
        </form>
      </Modal>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <input
          placeholder="Search by name, trainer ID, or place…"
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
              <th className="px-4 py-3">#</th>
              <th className="px-4 py-3">Trainer ID</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Phone</th>
              <th className="px-4 py-3">Place</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t, i) => (
              <tr key={t.id} className="border-t border-gray-100">
                <td className="px-4 py-3 text-gray-400">{i + 1}</td>
                <td className="px-4 py-3 font-mono text-xs">{t.trainer_id}</td>
                <td className="px-4 py-3">
                  <Link to={`/admin/trainers/${t.id}`} className="text-brand-blue hover:underline">{t.name}</Link>
                </td>
                <td className="px-4 py-3">{t.phone_number}</td>
                <td className="px-4 py-3">{t.place}</td>
                <td className="px-4 py-3"><Badge status={t.status} /></td>
                <td className="px-4 py-3 text-right">
                  {t.status === 'active' ? (
                    <button onClick={() => handleArchive(t.id)} className="text-xs text-gray-500 hover:text-red-600">
                      Archive
                    </button>
                  ) : (
                    <button onClick={() => handleUnarchive(t.id)} className="text-xs text-gray-500 hover:text-brand-green">
                      Unarchive
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-gray-400">No trainers found.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
