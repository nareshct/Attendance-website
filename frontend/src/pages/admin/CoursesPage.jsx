import { useCallback, useEffect, useState } from 'react'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { Modal } from '../../components/Modal'
import { useApi } from '../../hooks/useApi'

const EMPTY_FORM = { name: '', total_classes: 24, rate_per_class: '' }

export default function CoursesPage() {
  const api = useApi()
  const [courses, setCourses] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [editingCourseId, setEditingCourseId] = useState(null)
  const [editForm, setEditForm] = useState(EMPTY_FORM)
  const [editError, setEditError] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)

  const loadCourses = useCallback(async () => {
    setCourses(await api('/api/courses/'))
  }, [api])

  useEffect(() => {
    loadCourses().catch((err) => setError(err.message))
  }, [loadCourses])

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await api('/api/courses/', {
        method: 'POST',
        body: { ...form, total_classes: Number(form.total_classes), rate_per_class: form.rate_per_class || null },
      })
      setForm(EMPTY_FORM)
      setShowForm(false)
      await loadCourses()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  function openEditCourse(course) {
    setEditingCourseId(course.id)
    setEditForm({ name: course.name, total_classes: course.total_classes, rate_per_class: course.rate_per_class ?? '' })
    setEditError('')
  }

  function closeEditCourse() {
    setEditingCourseId(null)
    setEditForm(EMPTY_FORM)
    setEditError('')
  }

  async function handleEditSubmit(e) {
    e.preventDefault()
    setSavingEdit(true)
    setEditError('')
    try {
      await api(`/api/courses/${editingCourseId}/`, {
        method: 'PATCH',
        body: { ...editForm, total_classes: Number(editForm.total_classes), rate_per_class: editForm.rate_per_class || null },
      })
      closeEditCourse()
      await loadCourses()
    } catch (err) {
      setEditError(err.message)
    } finally {
      setSavingEdit(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-navy">Courses</h1>
        <Button onClick={() => setShowForm(true)}>+ Add course</Button>
      </div>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <Modal open={showForm} onClose={() => setShowForm(false)} title="Add course">
        <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input required placeholder="Course name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="input" />
          <input required type="number" placeholder="Total classes" value={form.total_classes} onChange={(e) => setForm({ ...form, total_classes: e.target.value })} className="input" />
          <input type="number" step="0.01" placeholder="B2C rate per class (₹)" value={form.rate_per_class} onChange={(e) => setForm({ ...form, rate_per_class: e.target.value })} className="input" />
          {error && <p className="sm:col-span-2 text-error text-xs">{error}</p>}
          <div className="sm:col-span-2 flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="success" disabled={submitting}>
              {submitting ? 'Saving…' : 'Save course'}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal open={editingCourseId != null} onClose={closeEditCourse} title="Edit course">
        <form onSubmit={handleEditSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input required placeholder="Course name" value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} className="input" />
          <input required type="number" placeholder="Total classes" value={editForm.total_classes} onChange={(e) => setEditForm({ ...editForm, total_classes: e.target.value })} className="input" />
          <input type="number" step="0.01" placeholder="B2C rate per class (₹)" value={editForm.rate_per_class} onChange={(e) => setEditForm({ ...editForm, rate_per_class: e.target.value })} className="input" />
          {editError && <p className="sm:col-span-2 text-error text-xs">{editError}</p>}
          <div className="sm:col-span-2 flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={closeEditCourse}>
              Cancel
            </Button>
            <Button type="submit" variant="success" disabled={savingEdit}>
              {savingEdit ? 'Saving…' : 'Save changes'}
            </Button>
          </div>
        </form>
      </Modal>

      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">#</th>
              <th className="table-head-cell">Course</th>
              <th className="table-head-cell">Total classes</th>
              <th className="table-head-cell">B2C rate/class</th>
              <th className="table-head-cell"></th>
            </tr>
          </thead>
          <tbody>
            {courses.map((c, i) => (
              <tr key={c.id} className="table-row">
                <td className="table-cell text-text-tertiary">{i + 1}</td>
                <td className="table-cell">{c.name}</td>
                <td className="table-cell tabular-nums">{c.total_classes}</td>
                <td className="table-cell tabular-nums">{c.rate_per_class ? `₹${c.rate_per_class}` : '—'}</td>
                <td className="table-cell text-right">
                  <button onClick={() => openEditCourse(c)} className="text-xs font-medium text-primary hover:underline focus-ring">
                    Edit
                  </button>
                </td>
              </tr>
            ))}
            {courses.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">No courses yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
