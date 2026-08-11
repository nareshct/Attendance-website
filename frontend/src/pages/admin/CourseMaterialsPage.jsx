import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiUpload, downloadFile } from '../../api/client'
import { Card } from '../../components/Card'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { Modal } from '../../components/Modal'
import { SearchableSelect } from '../../components/SearchableSelect'
import { useAuth } from '../../hooks/useAuth'
import { useApi } from '../../hooks/useApi'
import { usePickerSearch } from '../../hooks/usePickerSearch'
import { formatDate } from '../../utils/date'

const EMPTY_FORM = { course: '', title: '', description: '' }

function titleForFile(file, titlePrefix, multiple) {
  const base = file.name.replace(/\.pdf$/i, '')
  if (!multiple) return titlePrefix.trim()
  return titlePrefix.trim() ? `${titlePrefix.trim()} — ${base}` : base
}

// One section per course, each listing that course's own files — replaces a flat
// table that repeated the course name on every row, which got hard to scan once a
// course had several materials (e.g. uploading 5 files at once for one course).
function groupByCourse(materials) {
  const map = new Map()
  for (const m of materials) {
    if (!map.has(m.course)) map.set(m.course, { course: m.course, course_name: m.course_name, items: [] })
    map.get(m.course).items.push(m)
  }
  return Array.from(map.values()).sort((a, b) => a.course_name.localeCompare(b.course_name))
}

export default function CourseMaterialsPage() {
  const api = useApi()
  const pickerSearch = usePickerSearch()
  const { auth } = useAuth()
  const [materials, setMaterials] = useState([])
  const [search, setSearch] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [files, setFiles] = useState([])
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [busy, setBusy] = useState('')

  const loadMaterials = useCallback(async () => {
    setMaterials(await api('/api/course-materials/'))
  }, [api])

  useEffect(() => {
    loadMaterials().catch((err) => setError(err.message))
  }, [loadMaterials])

  function closeForm() {
    setShowForm(false)
    setForm(EMPTY_FORM)
    setFiles([])
    setError('')
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (files.length === 0) {
      setError('Please choose at least one PDF file.')
      return
    }
    if (files.length === 1 && !form.title.trim()) {
      setError('Title is required.')
      return
    }
    setSubmitting(true)
    setError('')

    // Each file becomes its own CourseMaterial — upload one at a time (not
    // Promise.all) so a failure partway through still leaves earlier files
    // uploaded, and the summary below can say exactly which ones failed and why,
    // same convention as the batches Excel-import skipped-rows summary.
    const multiple = files.length > 1
    const failures = []
    for (const f of files) {
      try {
        const data = new FormData()
        data.append('course', form.course)
        data.append('title', titleForFile(f, form.title, multiple))
        data.append('description', form.description)
        data.append('file', f)
        await apiUpload('/api/course-materials/', data, auth.token)
      } catch (err) {
        failures.push(`${f.name}: ${err.message}`)
      }
    }

    setSubmitting(false)
    await loadMaterials()
    if (failures.length > 0) {
      setError(`${files.length - failures.length} of ${files.length} file(s) uploaded. ${failures.join(' ')}`)
    } else {
      closeForm()
    }
  }

  const [editTarget, setEditTarget] = useState(null)
  const [editForm, setEditForm] = useState(EMPTY_FORM)
  const [editFile, setEditFile] = useState(null)
  const [editSaving, setEditSaving] = useState(false)
  const [editError, setEditError] = useState('')

  function openEdit(material) {
    setEditTarget(material)
    setEditForm({ course: String(material.course), title: material.title, description: material.description })
    setEditFile(null)
    setEditError('')
  }

  function closeEdit() {
    setEditTarget(null)
    setEditForm(EMPTY_FORM)
    setEditFile(null)
    setEditError('')
  }

  async function handleSaveEdit(e) {
    e.preventDefault()
    setEditSaving(true)
    setEditError('')
    try {
      const data = new FormData()
      data.append('course', editForm.course)
      data.append('title', editForm.title)
      data.append('description', editForm.description)
      if (editFile) data.append('file', editFile)
      await apiUpload(`/api/course-materials/${editTarget.id}/`, data, auth.token, 'PATCH')
      closeEdit()
      await loadMaterials()
    } catch (err) {
      setEditError(err.message)
    } finally {
      setEditSaving(false)
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

  const groups = useMemo(() => groupByCourse(materials), [materials])
  const query = search.trim().toLowerCase()
  const filteredGroups = query
    ? groups.filter((g) => g.course_name.toLowerCase().includes(query) || g.items.some((m) => m.title.toLowerCase().includes(query)))
    : groups

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-navy">Course Materials</h1>
        <button onClick={() => setShowForm(true)} className="text-sm rounded-lg bg-brand-blue text-white px-4 py-2 hover:bg-blue-800">
          + Upload PDF
        </button>
      </div>

      {error && !showForm && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <input
        placeholder="Search by course or file title…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="input max-w-sm mb-4"
      />

      <Modal open={showForm} onClose={closeForm} title="Upload course material">
        <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <SearchableSelect
            required
            placeholder="Search course…"
            value={form.course}
            onChange={(v) => setForm({ ...form, course: v })}
            loadOptions={pickerSearch.courses}
          />
          <input
            required={files.length <= 1}
            placeholder={files.length > 1 ? 'Title prefix (optional)' : 'Title'}
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            className="input"
          />
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
            multiple
            onChange={(e) => setFiles(Array.from(e.target.files))}
            className="sm:col-span-2 text-sm"
          />
          {files.length > 1 && (
            <p className="sm:col-span-2 text-xs text-text-tertiary">
              {files.length} files selected — each is uploaded as its own material, named{' '}
              {form.title.trim() ? `"${form.title.trim()} — <file name>"` : 'after its file'}.
            </p>
          )}
          {error && <p className="sm:col-span-2 text-red-600 text-xs">{error}</p>}
          <div className="sm:col-span-2 flex justify-end gap-3">
            <button type="button" onClick={closeForm} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button disabled={submitting} type="submit" className="rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800 disabled:opacity-60">
              {submitting ? 'Uploading…' : files.length > 1 ? `Upload ${files.length} materials` : 'Upload material'}
            </button>
          </div>
        </form>
      </Modal>

      <Modal open={Boolean(editTarget)} onClose={closeEdit} title="Edit course material">
        <form onSubmit={handleSaveEdit} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <SearchableSelect
            required
            placeholder="Search course…"
            value={editForm.course}
            selectedLabel={editTarget?.course_name}
            onChange={(v) => setEditForm({ ...editForm, course: v })}
            loadOptions={pickerSearch.courses}
          />
          <input required placeholder="Title" value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} className="input" />
          <textarea
            placeholder="Description"
            value={editForm.description}
            onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
            className="input sm:col-span-2"
            rows={3}
          />
          <div className="sm:col-span-2">
            <p className="text-xs text-text-secondary mb-1">
              Current file: {editTarget?.file_name || '—'} — choose a new one below to replace it, or leave blank to keep it.
            </p>
            <input
              type="file"
              accept="application/pdf"
              onChange={(e) => setEditFile(e.target.files[0] || null)}
              className="text-sm"
            />
          </div>
          {editError && <p className="sm:col-span-2 text-red-600 text-xs">{editError}</p>}
          <div className="sm:col-span-2 flex justify-end gap-3">
            <button type="button" onClick={closeEdit} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button disabled={editSaving} type="submit" className="rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800 disabled:opacity-60">
              {editSaving ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </form>
      </Modal>

      {filteredGroups.map((g) => (
        <Card key={g.course} className="p-0 overflow-x-auto mb-4">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <h2 className="font-semibold text-navy">{g.course_name}</h2>
            <span className="text-xs text-text-tertiary">{g.items.length} file{g.items.length !== 1 ? 's' : ''}</span>
          </div>
          <table className="table">
            <thead className="table-head-row">
              <tr>
                <th className="table-head-cell">Title</th>
                <th className="table-head-cell">Description</th>
                <th className="table-head-cell">Uploaded</th>
                <th className="table-head-cell"></th>
              </tr>
            </thead>
            <tbody>
              {g.items.map((m) => (
                <tr key={m.id} className="table-row">
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
                    <button onClick={() => openEdit(m)} className="text-brand-green hover:underline focus-ring">
                      Edit
                    </button>
                    <button
                      disabled={busy === `delete-${m.id}`}
                      onClick={() => { setDeleteTarget(m.id); setError('') }}
                      className="text-red-600 hover:underline disabled:opacity-60 focus-ring"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ))}
      {filteredGroups.length === 0 && (
        <Card className="text-center text-gray-400 py-6">
          {materials.length === 0 ? 'No course materials yet.' : 'No materials match your search.'}
        </Card>
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onClose={() => { setDeleteTarget(null); setError('') }}
        onConfirm={handleDelete}
        title="Delete material"
        message="Delete this material? This cannot be undone."
        confirmLabel="Delete"
        busyLabel="Deleting…"
        danger
        busy={busy === `delete-${deleteTarget}`}
        error={error}
      />
    </div>
  )
}
