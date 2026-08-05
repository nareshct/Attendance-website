import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../components/Button'
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
        <Button onClick={() => setShowForm(true)}>+ Onboard trainer</Button>
      </div>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

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
            <p className="text-xs text-text-secondary mb-2">Applies to every course this trainer teaches, unless overridden below.</p>
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
            <p className="text-xs text-text-secondary mb-2">Only add a line here if a course should pay a different rate than the default.</p>
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
                  <button type="button" onClick={() => removeRate(i)} className="text-xs font-medium text-error hover:underline shrink-0 focus-ring">
                    Remove
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setRates((rs) => [...rs, { course: '', rate_per_class: '' }])}
              className="text-xs font-medium text-primary hover:underline mt-2 focus-ring"
            >
              + Add course override
            </button>
          </div>

          {error && <p className="text-error text-xs">{error}</p>}
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="success" disabled={submitting}>
              {submitting ? 'Saving…' : 'Save trainer'}
            </Button>
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
              <th className="table-head-cell">#</th>
              <th className="table-head-cell">Trainer ID</th>
              <th className="table-head-cell">Name</th>
              <th className="table-head-cell">Phone</th>
              <th className="table-head-cell">Place</th>
              <th className="table-head-cell">Active students</th>
              <th className="table-head-cell">Payout pending</th>
              <th className="table-head-cell"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t, i) => (
              <tr key={t.id} className="table-row">
                <td className="table-cell text-text-tertiary">{i + 1}</td>
                <td className="table-cell font-mono text-xs">{t.trainer_id}</td>
                <td className="table-cell">
                  <Link to={`/admin/trainers/${t.id}`} className="font-medium text-primary hover:underline focus-ring">{t.name}</Link>
                </td>
                <td className="table-cell">{t.phone_number}</td>
                <td className="table-cell">{t.place}</td>
                <td className="table-cell">{t.active_student_count}</td>
                <td className="table-cell tabular-nums text-warning font-medium">₹{t.payout_pending}</td>
                <td className="table-cell text-right">
                  {t.status === 'active' ? (
                    <button onClick={() => handleArchive(t.id)} className="text-xs text-text-secondary hover:text-error focus-ring">
                      Archive
                    </button>
                  ) : (
                    <button onClick={() => handleUnarchive(t.id)} className="text-xs text-text-secondary hover:text-success focus-ring">
                      Unarchive
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-6 text-center text-text-tertiary">No trainers found.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
