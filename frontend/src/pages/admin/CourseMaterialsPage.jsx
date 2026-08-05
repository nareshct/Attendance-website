import { useCallback, useEffect, useState } from 'react'
import { apiUpload, downloadFile } from '../../api/client'
import { Card } from '../../components/Card'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { Modal } from '../../components/Modal'
import { SearchableSelect } from '../../components/SearchableSelect'
import { useAuth } from '../../hooks/useAuth'
import { useApi } from '../../hooks/useApi'
import { formatDate } from '../../utils/date'

const EMPTY_FORM = { course: '', title: '', description: '' }

export default function CourseMaterialsPage() {
  const api = useApi()
  const { auth } = useAuth()
  const [courses, setCourses] = useState([])
  const [materials, setMaterials] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [file, setFile] = useState(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [busy, setBusy] = useState('')

  const loadMaterials = useCallback(async () => {
    setMaterials(await api('/api/course-materials/'))
  }, [api])

  useEffect(() => {
    loadMaterials().catch((err) => setError(err.message))
    api('/api/courses/').then(setCourses).catch(() => {})
  }, [api, loadMaterials])

  async function handleSubmit(e) {
    e.preventDefault()
    if (!file) {
      setError('Please choose a PDF file.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const data = new FormData()
      data.append('course', form.course)
      data.append('title', form.title)
      data.append('description', form.description)
      data.append('file', file)
      await apiUpload('/api/course-materials/', data, auth.token)
      setForm(EMPTY_FORM)
      setFile(null)
      setShowForm(false)
      await loadMaterials()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const [deleteTarget, setDeleteTarget] = useState(null)

  async function handleDelete() {
    const id = deleteTarget
    setBusy(`delete-${id}`)
    setError('')
    try {
      await api(`/api/course-materials/${id}/`, { method: 'DELETE' })
      setDeleteTarget(null)
      await loadMaterials()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  async function handleDownload(id) {
    setBusy(`download-${id}`)
    setError('')
    try {
      await downloadFile(`/api/course-materials/${id}/download/`, auth.token)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-navy">Course Materials</h1>
        <button onClick={() => setShowForm(true)} className="text-sm rounded-lg bg-brand-blue text-white px-4 py-2 hover:bg-blue-800">
          + Upload PDF
        </button>
      </div>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <Modal open={showForm} onClose={() => setShowForm(false)} title="Upload course material">
        <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <SearchableSelect
            required
            placeholder="Search course…"
            value={form.course}
            onChange={(v) => setForm({ ...form, course: v })}
            options={courses.map((c) => ({ value: c.id, label: c.name }))}
          />
          <input required placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="input" />
          <textarea
            placeholder="Description"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            className="input sm:col-span-2"
            rows={3}
          />
          <input
            required
            type="file"
            accept="application/pdf"
            onChange={(e) => setFile(e.target.files[0] || null)}
            className="sm:col-span-2 text-sm"
          />
          {error && <p className="sm:col-span-2 text-red-600 text-xs">{error}</p>}
          <div className="sm:col-span-2 flex justify-end gap-3">
            <button type="button" onClick={() => setShowForm(false)} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button disabled={submitting} type="submit" className="rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800 disabled:opacity-60">
              {submitting ? 'Uploading…' : 'Upload material'}
            </button>
          </div>
        </form>
      </Modal>

      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">Course</th>
              <th className="table-head-cell">Title</th>
              <th className="table-head-cell">Description</th>
              <th className="table-head-cell">Uploaded</th>
              <th className="table-head-cell"></th>
            </tr>
          </thead>
          <tbody>
            {materials.map((m) => (
              <tr key={m.id} className="table-row">
                <td className="table-cell">{m.course_name}</td>
                <td className="table-cell">{m.title}</td>
                <td className="table-cell text-gray-500 max-w-xs truncate">{m.description}</td>
                <td className="table-cell">{formatDate(m.uploaded_at)}</td>
                <td className="table-cell whitespace-nowrap space-x-3 text-right">
                  <button
                    disabled={busy === `download-${m.id}`}
                    onClick={() => handleDownload(m.id)}
                    className="text-brand-blue hover:underline disabled:opacity-60 focus-ring"
                  >
                    {busy === `download-${m.id}` ? 'Downloading…' : 'Download'}
                  </button>
                  <button
                    disabled={busy === `delete-${m.id}`}
                    onClick={() => setDeleteTarget(m.id)}
                    className="text-red-600 hover:underline disabled:opacity-60 focus-ring"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {materials.length === 0 && (
              <tr><td colSpan={5} className="table-cell text-center text-gray-400">No course materials yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete material"
        message="Delete this material? This cannot be undone."
        confirmLabel="Delete"
        busyLabel="Deleting…"
        danger
        busy={busy === `delete-${deleteTarget}`}
      />
    </div>
  )
}
