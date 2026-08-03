import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import { Modal } from '../../components/Modal'
import { SearchableSelect } from '../../components/SearchableSelect'
import { useApi } from '../../hooks/useApi'
import { usePaginatedList } from '../../hooks/usePaginatedList'

const GRADES = Array.from({ length: 10 }, (_, i) => String(i + 3)) // std 3-12

const EMPTY_FORM = {
  name: '', grade: '', source_type: 'B2B', client: '',
  parent_name: '', place: '', parent_phone_number: '',
}

export default function StudentsPage() {
  const api = useApi()
  const [clients, setClients] = useState([])
  const [trainers, setTrainers] = useState([])
  const [courses, setCourses] = useState([])
  const [enrollments, setEnrollments] = useState([])
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [statusTab, setStatusTab] = useState('active')
  const [sourceFilter, setSourceFilter] = useState('')
  const [clientFilter, setClientFilter] = useState('')
  const [gradeFilter, setGradeFilter] = useState('')
  const [trainerFilter, setTrainerFilter] = useState('')
  const [courseFilter, setCourseFilter] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Debounced so rapid typing doesn't fire a request per keystroke — the actual search
  // runs server-side (see StudentViewSet.search_fields), so it always covers every
  // student regardless of how many pages have been loaded.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  const studentsPath = debouncedSearch ? `/api/students/?search=${encodeURIComponent(debouncedSearch)}` : '/api/students/'
  const {
    items: students, count: studentCount, hasMore, loading, loadingMore, reload, loadMore, loadLess, page,
  } = usePaginatedList(studentsPath)

  useEffect(() => {
    reload().catch((err) => setError(err.message))
  }, [reload])

  useEffect(() => {
    api('/api/clients/').then(setClients).catch(() => {})
    api('/api/trainers/').then(setTrainers).catch(() => {})
    api('/api/courses/').then(setCourses).catch(() => {})
    api('/api/enrollments/').then(setEnrollments).catch(() => {})
  }, [api])

  const studentTrainerIds = {}
  const studentCourseIds = {}
  for (const e of enrollments) {
    ;(studentTrainerIds[e.student] ??= new Set()).add(e.trainer)
    ;(studentCourseIds[e.student] ??= new Set()).add(e.course)
  }

  // Search is already applied server-side (see studentsPath above) — this only layers
  // the status tab and dropdown filters on top of the already-matching results.
  const filtered = students.filter((s) => {
    const matchesStatus = s.status === statusTab
    const matchesSource = !sourceFilter || s.source_type === sourceFilter
    const matchesClient = sourceFilter !== 'B2B' || !clientFilter || String(s.client) === clientFilter
    const matchesGrade = !gradeFilter || s.grade === gradeFilter
    const matchesTrainer = !trainerFilter || (studentTrainerIds[s.id]?.has(Number(trainerFilter)) ?? false)
    const matchesCourse = !courseFilter || (studentCourseIds[s.id]?.has(Number(courseFilter)) ?? false)
    return matchesStatus && matchesSource && matchesClient && matchesGrade && matchesTrainer && matchesCourse
  })

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await api('/api/students/', {
        method: 'POST',
        body: {
          name: form.name,
          grade: form.grade,
          parent_name: form.parent_name,
          place: form.place,
          parent_phone_number: form.parent_phone_number,
          source_type: form.source_type,
          client: form.source_type === 'B2B' ? form.client || null : null,
        },
      })

      setForm(EMPTY_FORM)
      setShowForm(false)
      await reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleArchive(id) {
    await api(`/api/students/${id}/archive/`, { method: 'POST' })
    await reload()
  }

  async function handleUnarchive(id) {
    await api(`/api/students/${id}/unarchive/`, { method: 'POST' })
    await reload()
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-navy">Students</h1>
        <button
          onClick={() => setShowForm(true)}
          className="text-sm rounded-lg bg-brand-blue text-white px-4 py-2 hover:bg-blue-800"
        >
          + Add student
        </button>
      </div>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <Modal open={showForm} onClose={() => setShowForm(false)} title="Add student" maxWidthClass="max-w-2xl">
        <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input required placeholder="Student name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="input sm:col-span-2" />

          <select required value={form.grade} onChange={(e) => setForm({ ...form, grade: e.target.value })} className="input">
            <option value="">Select grade…</option>
            {GRADES.map((g) => <option key={g} value={g}>Std {g}</option>)}
          </select>
          <select
            value={form.source_type}
            onChange={(e) => setForm({ ...form, source_type: e.target.value, client: '' })}
            className="input"
          >
            <option value="B2C">B2C</option>
            <option value="B2B">B2B</option>
          </select>
          {form.source_type === 'B2B' && (
            <select required value={form.client} onChange={(e) => setForm({ ...form, client: e.target.value })} className="input">
              <option value="">Select client…</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>{c.company_name}</option>
              ))}
            </select>
          )}

          <p className="sm:col-span-2 text-xs text-gray-400 -mb-1">Optional — parent details</p>
          <input placeholder="Parent name" value={form.parent_name} onChange={(e) => setForm({ ...form, parent_name: e.target.value })} className="input" />
          <input placeholder="Parent phone" value={form.parent_phone_number} onChange={(e) => setForm({ ...form, parent_phone_number: e.target.value })} className="input" />
          <input placeholder="Place" value={form.place} onChange={(e) => setForm({ ...form, place: e.target.value })} className="input" />

          <p className="sm:col-span-2 text-xs text-gray-400 -mt-1">
            Course, trainer, schedule, and payment plan are set up next in Enrollments.
          </p>
          {error && <p className="sm:col-span-2 text-red-600 text-xs">{error}</p>}
          <div className="sm:col-span-2 flex justify-end gap-3">
            <button type="button" onClick={() => setShowForm(false)} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button disabled={submitting} type="submit" className="rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800 disabled:opacity-60">
              {submitting ? 'Saving…' : 'Save student'}
            </button>
          </div>
        </form>
      </Modal>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <input
          placeholder="Search by name or student ID…"
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

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <select
          value={sourceFilter}
          onChange={(e) => {
            setSourceFilter(e.target.value)
            setClientFilter('')
          }}
          className="input"
        >
          <option value="">All sources</option>
          <option value="B2C">B2C</option>
          <option value="B2B">B2B</option>
        </select>
        {sourceFilter === 'B2B' && (
          <SearchableSelect
            placeholder="All clients"
            value={clientFilter}
            onChange={setClientFilter}
            options={[{ value: '', label: 'All clients' }, ...clients.map((c) => ({ value: c.id, label: c.company_name }))]}
          />
        )}
        <select value={gradeFilter} onChange={(e) => setGradeFilter(e.target.value)} className="input">
          <option value="">All grades</option>
          {GRADES.map((g) => <option key={g} value={g}>Std {g}</option>)}
        </select>
        <SearchableSelect
          placeholder="All trainers"
          value={trainerFilter}
          onChange={setTrainerFilter}
          options={[{ value: '', label: 'All trainers' }, ...trainers.map((t) => ({ value: t.id, label: t.name }))]}
        />
        <SearchableSelect
          placeholder="All classes"
          value={courseFilter}
          onChange={setCourseFilter}
          options={[{ value: '', label: 'All classes' }, ...courses.map((c) => ({ value: c.id, label: c.name }))]}
        />
      </div>

      <Card className="p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-left">
            <tr>
              <th className="px-4 py-3">#</th>
              <th className="px-4 py-3">Student ID</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Client</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s, i) => (
              <tr key={s.id} className="border-t border-gray-100">
                <td className="px-4 py-3 text-gray-400">{i + 1}</td>
                <td className="px-4 py-3 font-mono text-xs">{s.student_id}</td>
                <td className="px-4 py-3">
                  <Link to={`/admin/students/${s.id}`} className="text-brand-blue hover:underline">{s.name}</Link>
                </td>
                <td className="px-4 py-3">{s.source_type === 'B2B' ? (s.client_name || '—') : 'Own'}</td>
                <td className="px-4 py-3"><Badge status={s.status} /></td>
                <td className="px-4 py-3 text-right">
                  {s.status === 'active' ? (
                    <button onClick={() => handleArchive(s.id)} className="text-xs text-gray-500 hover:text-red-600">
                      Archive
                    </button>
                  ) : (
                    <button onClick={() => handleUnarchive(s.id)} className="text-xs text-gray-500 hover:text-brand-green">
                      Unarchive
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-gray-400">No students found.</td></tr>
            )}
            {loading && (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-gray-400">Loading…</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      {!loading && students.length > 0 && (
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-gray-400">
            Loaded {students.length} of {studentCount} students
            {hasMore && ' — search covers everyone; status and dropdown filters only apply to what\'s loaded'}
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
