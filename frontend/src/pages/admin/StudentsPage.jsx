import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArchiveStudentModal } from '../../components/ArchiveStudentModal'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { Modal } from '../../components/Modal'
import { SearchableSelect } from '../../components/SearchableSelect'
import { useApi } from '../../hooks/useApi'
import { usePaginatedList } from '../../hooks/usePaginatedList'
import { usePickerSearch } from '../../hooks/usePickerSearch'

const GRADES = Array.from({ length: 10 }, (_, i) => String(i + 3)) // std 3-12

const EMPTY_FORM = {
  name: '', grade: '', source_type: 'B2B', client: '',
  parent_name: '', place: '', parent_phone_number: '',
}

export default function StudentsPage() {
  const api = useApi()
  const pickerSearch = usePickerSearch()
  const [clients, setClients] = useState([])
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
    // Kept as a full unbounded fetch (unlike the filter pickers below) — this feeds the
    // "Add student" form's native <select> of active clients, which isn't a
    // SearchableSelect and so isn't converted to search-as-you-type here.
    api('/api/clients/').then(setClients).catch(() => {})
    api('/api/enrollments/').then(setEnrollments).catch(() => {})
  }, [api])

  const studentTrainerIds = {}
  const studentCourseIds = {}
  const studentPrimaryEnrollment = {}
  for (const e of enrollments) {
    ;(studentTrainerIds[e.student] ??= new Set()).add(e.trainer)
    ;(studentCourseIds[e.student] ??= new Set()).add(e.course)

    // One row per student — prefer their ongoing enrollment; among enrollments with the
    // same status, the most recently started one wins.
    const current = studentPrimaryEnrollment[e.student]
    if (
      !current ||
      (e.status === 'ongoing' && current.status !== 'ongoing') ||
      (e.status === current.status && e.start_date > current.start_date)
    ) {
      studentPrimaryEnrollment[e.student] = e
    }
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

  const [archiveTarget, setArchiveTarget] = useState(null)

  async function handleUnarchive(id) {
    setError('')
    try {
      await api(`/api/students/${id}/unarchive/`, { method: 'POST' })
      await reload()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-navy">Students</h1>
        <Button onClick={() => setShowForm(true)}>+ Add student</Button>
      </div>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <Modal open={showForm} onClose={() => setShowForm(false)} title="Add student" maxWidthClass="max-w-2xl">
        <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input required maxLength={255} placeholder="Student name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="input sm:col-span-2" />

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
              {clients.filter((c) => c.status === 'active').map((c) => (
                <option key={c.id} value={c.id}>{c.company_name}</option>
              ))}
            </select>
          )}

          <p className="sm:col-span-2 text-xs text-text-tertiary -mb-1">Optional — parent details</p>
          <input maxLength={255} placeholder="Parent name" value={form.parent_name} onChange={(e) => setForm({ ...form, parent_name: e.target.value })} className="input" />
          <input maxLength={20} placeholder="Parent phone" value={form.parent_phone_number} onChange={(e) => setForm({ ...form, parent_phone_number: e.target.value })} className="input" />
          <input maxLength={255} placeholder="Place" value={form.place} onChange={(e) => setForm({ ...form, place: e.target.value })} className="input" />

          <p className="sm:col-span-2 text-xs text-text-tertiary -mt-1">
            Course, trainer, schedule, and payment plan are set up next in Enrollments.
          </p>
          {error && <p className="sm:col-span-2 text-error text-xs">{error}</p>}
          <div className="sm:col-span-2 flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="success" disabled={submitting}>
              {submitting ? 'Saving…' : 'Save student'}
            </Button>
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
            <Button key={t} variant={statusTab === t ? 'primary' : 'secondary'} className="capitalize" onClick={() => setStatusTab(t)}>
              {t}
            </Button>
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
            loadOptions={(q) =>
              pickerSearch.clients(q, { status: '' }).then((cs) => (q ? cs : [{ value: '', label: 'All clients' }, ...cs]))
            }
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
          loadOptions={(q) =>
            pickerSearch.trainers(q, { status: '' }).then((ts) => (q ? ts : [{ value: '', label: 'All trainers' }, ...ts]))
          }
        />
        <SearchableSelect
          placeholder="All classes"
          value={courseFilter}
          onChange={setCourseFilter}
          loadOptions={(q) => pickerSearch.courses(q).then((cs) => (q ? cs : [{ value: '', label: 'All classes' }, ...cs]))}
        />
      </div>

      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">#</th>
              <th className="table-head-cell">Student ID</th>
              <th className="table-head-cell">Name</th>
              <th className="table-head-cell">Client</th>
              <th className="table-head-cell">Course/Batch</th>
              <th className="table-head-cell">Progress</th>
              <th className="table-head-cell"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s, i) => (
              <tr key={s.id} className="table-row">
                <td className="table-cell text-text-tertiary">{i + 1}</td>
                <td className="table-cell font-mono text-xs">{s.student_id}</td>
                <td className="table-cell">
                  <Link to={`/admin/students/${s.id}`} className="font-medium text-primary hover:underline focus-ring">{s.name}</Link>
                </td>
                <td className="table-cell">{s.source_type === 'B2B' ? (s.client_name || '—') : 'Own'}</td>
                <td className="table-cell">
                  {studentPrimaryEnrollment[s.id]
                    ? `${studentPrimaryEnrollment[s.id].course_name} — Batch ${studentPrimaryEnrollment[s.id].batch_number}`
                    : '—'}
                </td>
                <td className="table-cell tabular-nums">
                  {studentPrimaryEnrollment[s.id]
                    ? `${studentPrimaryEnrollment[s.id].classes_completed}/${studentPrimaryEnrollment[s.id].classes_total}`
                    : '—'}
                </td>
                <td className="table-cell text-right">
                  {s.status === 'active' ? (
                    <button onClick={() => setArchiveTarget(s)} className="text-xs text-text-secondary hover:text-error focus-ring">
                      Archive
                    </button>
                  ) : (
                    <button onClick={() => handleUnarchive(s.id)} className="text-xs text-text-secondary hover:text-success focus-ring">
                      Unarchive
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-text-tertiary">No students found.</td></tr>
            )}
            {loading && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-text-tertiary">Loading…</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      {!loading && students.length > 0 && (
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-text-tertiary">
            Loaded {students.length} of {studentCount} students
            {hasMore && ' — search covers everyone; status and dropdown filters only apply to what\'s loaded'}
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

      <ArchiveStudentModal
        open={Boolean(archiveTarget)}
        studentId={archiveTarget?.id}
        studentName={archiveTarget?.name}
        sourceType={archiveTarget?.source_type}
        onClose={() => setArchiveTarget(null)}
        onArchived={reload}
      />
    </div>
  )
}
