import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/Badge'
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
    loadSummary().catch(() => {})
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
          <button onClick={loadSourceBreakdown} className="text-sm rounded-lg border border-gray-200 text-gray-600 px-4 py-2 hover:bg-gray-50">
            Revenue by source
          </button>
          <button onClick={() => setShowForm(true)} className="text-sm rounded-lg bg-brand-blue text-white px-4 py-2 hover:bg-blue-800">
            + New batch
          </button>
        </div>
      </div>

      <Modal open={showSourceBreakdown} onClose={() => setShowSourceBreakdown(false)} title="Revenue by source" maxWidthClass="max-w-2xl">
        <p className="text-xs text-gray-400 mb-3">
          Only covers guest sign-ups (walk-ins added by hand or imported from Excel) — a registered student added
          the normal way doesn't record how they heard about the center.
        </p>
        {sourceBreakdown ? (
          <table className="w-full text-sm">
            <thead className="text-gray-500 text-left">
              <tr>
                <th className="py-1.5 pr-4">Source</th>
                <th className="py-1.5 pr-4">Enrolled</th>
                <th className="py-1.5 pr-4">Collected</th>
                <th className="py-1.5">Pending</th>
              </tr>
            </thead>
            <tbody>
              {sourceBreakdown.map((row) => (
                <tr key={row.source} className="border-t border-gray-100">
                  <td className="py-1.5 pr-4">{row.source}</td>
                  <td className="py-1.5 pr-4">{row.enrolled_count}</td>
                  <td className="py-1.5 pr-4 text-brand-green">₹{row.collected}</td>
                  <td className="py-1.5 text-brand-amber">₹{row.pending}</td>
                </tr>
              ))}
              {sourceBreakdown.length === 0 && (
                <tr><td colSpan={4} className="py-6 text-center text-gray-400">No guest sign-ups yet.</td></tr>
              )}
            </tbody>
          </table>
        ) : <p className="text-sm text-gray-400">Loading…</p>}
      </Modal>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-6">
        <StatCard label="Batches" value={summary ? summary.batch_count : '…'} accentClass="text-brand-blue" />
        <StatCard label="Students enrolled" value={summary ? summary.total_students : '…'} accentClass="text-brand-blue" />
        <StatCard label="Collected" value={summary ? `₹${summary.total_collected}` : '…'} accentClass="text-brand-green" />
        <StatCard label="Pending" value={summary ? `₹${summary.total_pending}` : '…'} accentClass="text-brand-amber" />
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
          <input required type="number" step="0.01" placeholder="Fee per student (₹)" value={form.fee_per_student} onChange={(e) => setForm({ ...form, fee_per_student: e.target.value })} className="input" />
          <select value={form.payment_type} onChange={(e) => setForm({ ...form, payment_type: e.target.value })} className="input">
            {PAYMENT_TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <input required type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} className="input" />
          <input required type="time" value={form.class_time} onChange={(e) => setForm({ ...form, class_time: e.target.value })} className="input" />
          <div className="sm:col-span-2">
            <p className="text-sm text-gray-500 mb-1">Class days</p>
            <div className="flex flex-wrap gap-2">
              {DAY_OPTIONS.map((d) => (
                <button
                  key={d.code}
                  type="button"
                  onClick={() => toggleDay(d.code)}
                  className={`px-3 py-1.5 rounded-lg text-sm border ${
                    form.class_days.includes(d.code)
                      ? 'bg-brand-blue text-white border-brand-blue'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-brand-blue'
                  }`}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>
          <div className="sm:col-span-2">
            <p className="text-sm text-gray-500 mb-1">
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
              <button type="button" onClick={addTrainerName} disabled={!trainerNameInput.trim()} className="text-sm text-brand-blue hover:underline disabled:opacity-60 shrink-0">
                + Add
              </button>
            </div>
            {form.trainerNames.length > 0 && (
              <ul className="space-y-1">
                {form.trainerNames.map((name) => (
                  <li key={name} className="flex items-center justify-between text-sm bg-gray-50 rounded px-3 py-1.5">
                    <span>{name}</span>
                    <button type="button" onClick={() => removeTrainerName(name)} className="text-xs text-red-600 hover:underline">
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <input placeholder="Google Meet link (optional)" value={form.meet_link} onChange={(e) => setForm({ ...form, meet_link: e.target.value })} className="input sm:col-span-2" />
          <textarea placeholder="Description (optional)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="input sm:col-span-2" rows={2} />
          <p className="sm:col-span-2 text-xs text-gray-400 -mt-1">
            Payouts for whoever runs this batch are added afterward, on the batch's own page — one per person.
          </p>

          {error && <p className="sm:col-span-2 text-red-600 text-xs">{error}</p>}
          <div className="sm:col-span-2 flex justify-end gap-3">
            <button type="button" onClick={() => setShowForm(false)} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button disabled={submitting} type="submit" className="rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800 disabled:opacity-60">
              {submitting ? 'Saving…' : 'Save batch'}
            </button>
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
              <th className="px-4 py-3">Batch</th>
              <th className="px-4 py-3">Course</th>
              <th className="px-4 py-3">Schedule</th>
              <th className="px-4 py-3">Trainers</th>
              <th className="px-4 py-3">Fee/student</th>
              <th className="px-4 py-3">Enrolled</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Started</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((b) => (
              <tr key={b.id} className="border-t border-gray-100">
                <td className="px-4 py-3">
                  <Link to={`/admin/batches/${b.id}`} className="text-brand-blue hover:underline">{b.name}</Link>
                </td>
                <td className="px-4 py-3">{b.course_name}</td>
                <td className="px-4 py-3 text-gray-500">
                  {formatDays(b.class_days)}{b.class_time && ` · ${formatTime(b.class_time)}`}
                </td>
                <td className="px-4 py-3 text-gray-500">
                  {b.trainer_names ? b.trainer_names.split(',').filter(Boolean).join(', ') : '—'}
                </td>
                <td className="px-4 py-3">₹{b.fee_per_student}</td>
                <td className="px-4 py-3">{b.enrolled_count}</td>
                <td className="px-4 py-3"><Badge status={b.status} /></td>
                <td className="px-4 py-3">{formatDate(b.start_date)}</td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-6 text-center text-gray-400">No batches found.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      {!loading && batches.length > 0 && (
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-gray-400">
            Loaded {batches.length} of {batchCount} batches
            {hasMore && ' — search covers everyone; status tab only applies to what\'s loaded'}
          </p>
          <div className="flex gap-4">
            {page > 1 && (
              <button onClick={loadLess} className="text-xs text-brand-blue hover:underline">
                Load less
              </button>
            )}
            {hasMore && (
              <button
                disabled={loadingMore}
                onClick={loadMore}
                className="text-xs text-brand-blue hover:underline disabled:opacity-60"
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
