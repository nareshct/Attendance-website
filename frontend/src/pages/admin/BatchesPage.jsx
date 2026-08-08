import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { Card, StatCard } from '../../components/Card'
import { Modal } from '../../components/Modal'
import { SearchableSelect } from '../../components/SearchableSelect'
import { useApi } from '../../hooks/useApi'
import { usePaginatedList } from '../../hooks/usePaginatedList'
import { formatDate } from '../../utils/date'
import { DAY_OPTIONS, formatDays, formatTime } from '../../utils/schedule'

const PAYMENT_TYPE_OPTIONS = [
  { value: 'one_time', label: 'One-time payment' },
  { value: 'two_installments', label: 'Two installments' },
  { value: 'three_installments', label: 'Three installments' },
  { value: 'four_installments', label: 'Four installments' },
]

const EMPTY_FORM = {
  name: '', course: '', description: '', total_classes: 24, fee_per_student: '',
  payment_type: 'one_time', start_date: '', class_time: '', class_days: [],
  meet_link: '', trainerNames: [],
}

export default function BatchesPage() {
  const api = useApi()
  const [courses, setCourses] = useState([])
  const [trainers, setTrainers] = useState([])
  const [summary, setSummary] = useState(null)
  const [sourceBreakdown, setSourceBreakdown] = useState(null)
  const [showSourceBreakdown, setShowSourceBreakdown] = useState(false)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [statusTab, setStatusTab] = useState('ongoing')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [trainerNameInput, setTrainerNameInput] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Debounced so rapid typing doesn't fire a request per keystroke — search runs
  // server-side (see BatchViewSet.search_fields), so it always covers every batch
  // regardless of how many pages have been loaded.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  const batchesPath = debouncedSearch ? `/api/batches/?search=${encodeURIComponent(debouncedSearch)}` : '/api/batches/'
  const {
    items: batches, count: batchCount, hasMore, loading, loadingMore, reload: reloadBatches, loadMore, loadLess, page,
  } = usePaginatedList(batchesPath)

  useEffect(() => {
    reloadBatches().catch((err) => setError(err.message))
  }, [reloadBatches])

  const loadSummary = useCallback(() => {
    return api('/api/batches/summary/').then(setSummary)
  }, [api])

  useEffect(() => {
    loadSummary().catch((err) => setError(err.message))
    api('/api/courses/').then(setCourses).catch(() => {})
    // Only used as autocomplete suggestions below — a batch trainer isn't required to be
    // a registered trainer, so this list doesn't restrict what can be typed/added.
    api('/api/trainers/').then((t) => setTrainers(t.filter((x) => x.status === 'active'))).catch(() => {})
  }, [api, loadSummary])

  function loadSourceBreakdown() {
    setShowSourceBreakdown(true)
    if (sourceBreakdown) return
    api('/api/batches/source_breakdown/').then(setSourceBreakdown).catch((err) => setError(err.message))
  }

  function addTrainerName() {
    const name = trainerNameInput.trim()
    if (!name || form.trainerNames.includes(name)) return
    setForm((f) => ({ ...f, trainerNames: [...f.trainerNames, name] }))
    setTrainerNameInput('')
  }

  function removeTrainerName(name) {
    setForm((f) => ({ ...f, trainerNames: f.trainerNames.filter((n) => n !== name) }))
  }

  function toggleDay(code) {
    setForm((f) => ({
      ...f,
      class_days: f.class_days.includes(code) ? f.class_days.filter((d) => d !== code) : [...f.class_days, code],
    }))
  }

  // Search is already applied server-side (see batchesPath above) — this only layers
  // the status tab on top of the already-matching results.
  const filtered = batches.filter((b) => b.status === statusTab)

  async function handleSubmit(e) {
    e.preventDefault()
    if (form.class_days.length === 0) {
      setError('Select at least one class day.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await api('/api/batches/', {
        method: 'POST',
        body: {
          name: form.name,
          course: Number(form.course),
          description: form.description,
          total_classes: Number(form.total_classes),
          fee_per_student: form.fee_per_student,
          payment_type: form.payment_type,
          start_date: form.start_date,
          class_time: form.class_time,
          class_days: form.class_days.join(','),
          meet_link: form.meet_link,
          trainer_names: form.trainerNames.join(', '),
        },
      })
      setForm(EMPTY_FORM)
      setShowForm(false)
      await reloadBatches()
      await loadSummary()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-navy">Batches</h1>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={loadSourceBreakdown}>Revenue by source</Button>
          <Button onClick={() => setShowForm(true)}>+ New batch</Button>
        </div>
      </div>

      <Modal open={showSourceBreakdown} onClose={() => setShowSourceBreakdown(false)} title="Revenue by source" maxWidthClass="max-w-2xl">
        <p className="text-xs text-text-tertiary mb-3">
          Only covers guest sign-ups (walk-ins added by hand or imported from Excel) — a registered student added
          the normal way doesn't record how they heard about the center.
        </p>
        {sourceBreakdown ? (
          <table className="table-compact">
            <thead>
              <tr>
                <th className="table-compact-head-cell">Source</th>
                <th className="table-compact-head-cell">Enrolled</th>
                <th className="table-compact-head-cell">Collected</th>
                <th className="table-compact-head-cell">Pending</th>
              </tr>
            </thead>
            <tbody>
              {sourceBreakdown.map((row) => (
                <tr key={row.source} className="table-compact-row">
                  <td className="table-compact-cell">{row.source}</td>
                  <td className="table-compact-cell tabular-nums">{row.enrolled_count}</td>
                  <td className="table-compact-cell text-success tabular-nums">₹{row.collected}</td>
                  <td className="table-compact-cell text-warning tabular-nums">₹{row.pending}</td>
                </tr>
              ))}
              {sourceBreakdown.length === 0 && (
                <tr><td colSpan={4} className="table-compact-cell text-text-tertiary">No guest sign-ups yet.</td></tr>
              )}
            </tbody>
          </table>
        ) : <p className="text-sm text-text-tertiary">Loading…</p>}
      </Modal>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-6">
        <StatCard label="Batches" value={summary ? summary.batch_count : '…'} accentClass="text-navy" />
        <StatCard label="Students enrolled" value={summary ? summary.total_students : '…'} accentClass="text-navy" />
        <StatCard label="Collected" value={summary ? `₹${summary.total_collected}` : '…'} accentClass="text-success" />
        <StatCard label="Pending" value={summary ? `₹${summary.total_pending}` : '…'} accentClass="text-warning" />
      </div>

      <Modal open={showForm} onClose={() => setShowForm(false)} title="New batch" maxWidthClass="max-w-2xl">
        <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input required placeholder="Batch name (e.g. Scratch — July 2026)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="input sm:col-span-2" />
          <SearchableSelect
            required
            placeholder="Search course…"
            value={form.course}
            onChange={(v) => setForm({ ...form, course: v })}
            options={courses.map((c) => ({ value: c.id, label: c.name }))}
          />
          <input required type="number" min="1" placeholder="Total classes" value={form.total_classes} onChange={(e) => setForm({ ...form, total_classes: e.target.value })} className="input" />
          <input required type="number" step="0.01" min="0" placeholder="Fee per student (₹)" value={form.fee_per_student} onChange={(e) => setForm({ ...form, fee_per_student: e.target.value })} className="input" />
          <select value={form.payment_type} onChange={(e) => setForm({ ...form, payment_type: e.target.value })} className="input">
            {PAYMENT_TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <input required type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} className="input" />
          <input required type="time" value={form.class_time} onChange={(e) => setForm({ ...form, class_time: e.target.value })} className="input" />
          <div className="sm:col-span-2">
            <p className="text-sm text-text-secondary mb-1">Class days</p>
            <div className="flex flex-wrap gap-2">
              {DAY_OPTIONS.map((d) => (
                <Button
                  key={d.code}
                  type="button"
                  size="sm"
                  variant={form.class_days.includes(d.code) ? 'primary' : 'secondary'}
                  onClick={() => toggleDay(d.code)}
                >
                  {d.label}
                </Button>
              ))}
            </div>
          </div>
          <div className="sm:col-span-2">
            <p className="text-sm text-text-secondary mb-1">
              Trainers (optional — any name, not just registered trainers; any number, for split schedules or co-teaching)
            </p>
            <div className="flex gap-2 mb-2">
              <input
                placeholder="Type a name and add…"
                value={trainerNameInput}
                onChange={(e) => setTrainerNameInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTrainerName() } }}
                list="batch-trainer-suggestions"
                className="input flex-1"
              />
              <datalist id="batch-trainer-suggestions">
                {trainers.map((t) => <option key={t.id} value={t.name} />)}
              </datalist>
              <button type="button" onClick={addTrainerName} disabled={!trainerNameInput.trim()} className="text-sm font-medium text-primary hover:underline disabled:opacity-60 shrink-0 focus-ring">
                + Add
              </button>
            </div>
            {form.trainerNames.length > 0 && (
              <ul className="space-y-1">
                {form.trainerNames.map((name) => (
                  <li key={name} className="flex items-center justify-between text-sm bg-surface-sunken rounded px-3 py-1.5">
                    <span>{name}</span>
                    <button type="button" onClick={() => removeTrainerName(name)} className="text-xs font-medium text-error hover:underline focus-ring">
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <input placeholder="Google Meet link (optional)" value={form.meet_link} onChange={(e) => setForm({ ...form, meet_link: e.target.value })} className="input sm:col-span-2" />
          <textarea placeholder="Description (optional)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="input sm:col-span-2" rows={2} />
          <p className="sm:col-span-2 text-xs text-text-tertiary -mt-1">
            Payouts for whoever runs this batch are added afterward, on the batch's own page — one per person.
          </p>

          {error && <p className="sm:col-span-2 text-error text-xs">{error}</p>}
          <div className="sm:col-span-2 flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="success" disabled={submitting}>
              {submitting ? 'Saving…' : 'Save batch'}
            </Button>
          </div>
        </form>
      </Modal>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <input
          placeholder="Search by batch name or course…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input max-w-sm"
        />
        <div className="flex gap-2 shrink-0">
          {['ongoing', 'completed', 'cancelled'].map((t) => (
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
              <th className="table-head-cell">Batch</th>
              <th className="table-head-cell">Course</th>
              <th className="table-head-cell">Schedule</th>
              <th className="table-head-cell">Trainers</th>
              <th className="table-head-cell">Fee/student</th>
              <th className="table-head-cell">Enrolled</th>
              <th className="table-head-cell">Status</th>
              <th className="table-head-cell">Started</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((b) => (
              <tr key={b.id} className="table-row">
                <td className="table-cell">
                  <Link to={`/admin/batches/${b.id}`} className="font-medium text-primary hover:underline focus-ring">{b.name}</Link>
                </td>
                <td className="table-cell">{b.course_name}</td>
                <td className="table-cell text-text-secondary">
                  {formatDays(b.class_days)}{b.class_time && ` · ${formatTime(b.class_time)}`}
                </td>
                <td className="table-cell text-text-secondary">
                  {b.trainer_names ? b.trainer_names.split(',').filter(Boolean).join(', ') : '—'}
                </td>
                <td className="table-cell tabular-nums">₹{b.fee_per_student}</td>
                <td className="table-cell tabular-nums">{b.enrolled_count}</td>
                <td className="table-cell"><Badge status={b.status} /></td>
                <td className="table-cell">{formatDate(b.start_date)}</td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-6 text-center text-text-tertiary">No batches found.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      {!loading && batches.length > 0 && (
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-text-tertiary">
            Loaded {batches.length} of {batchCount} batches
            {hasMore && ' — search covers everyone; status tab only applies to what\'s loaded'}
          </p>
          <div className="flex gap-4">
            {page > 1 && (
              <button onClick={loadLess} className="text-xs font-medium text-primary hover:underline focus-ring">
                Load less
              </button>
            )}
            {hasMore && (
              <button
                disabled={loadingMore}
                onClick={loadMore}
                className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring"
              >
                {loadingMore ? 'Loading…' : 'Load more'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
