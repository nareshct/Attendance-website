import { useEffect, useState } from 'react'
import { downloadFile } from '../../api/client'
import { Card } from '../../components/Card'
import { SearchableSelect } from '../../components/SearchableSelect'
import { useAuth } from '../../context/AuthContext'
import { useApi } from '../../hooks/useApi'
import { formatDate } from '../../utils/date'

export default function CourseMaterialsPage() {
  const api = useApi()
  const { auth } = useAuth()
  const [courses, setCourses] = useState([])
  const [materials, setMaterials] = useState([])
  const [courseFilter, setCourseFilter] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  useEffect(() => {
    api('/api/courses/').then(setCourses).catch(() => {})
  }, [api])

  useEffect(() => {
    const params = courseFilter ? `?course=${courseFilter}` : ''
    api(`/api/course-materials/${params}`)
      .then(setMaterials)
      .catch((err) => setError(err.message))
  }, [api, courseFilter])

  async function handleDownload(id) {
    setBusy(id)
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
      <h1 className="text-2xl font-semibold text-navy mb-6">Course Materials</h1>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="mb-4 max-w-xs">
        <SearchableSelect
          placeholder="All courses"
          value={courseFilter}
          onChange={setCourseFilter}
          options={[{ value: '', label: 'All courses' }, ...courses.map((c) => ({ value: c.id, label: c.name }))]}
        />
      </div>

      <Card className="p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-left">
            <tr>
              <th className="px-4 py-3">Course</th>
              <th className="px-4 py-3">Title</th>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3">Uploaded</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {materials.map((m) => (
              <tr key={m.id} className="border-t border-gray-100">
                <td className="px-4 py-3">{m.course_name}</td>
                <td className="px-4 py-3">{m.title}</td>
                <td className="px-4 py-3 text-gray-500 max-w-xs truncate">{m.description}</td>
                <td className="px-4 py-3">{formatDate(m.uploaded_at)}</td>
                <td className="px-4 py-3 text-right">
                  <button
                    disabled={busy === m.id}
                    onClick={() => handleDownload(m.id)}
                    className="text-brand-violet hover:underline disabled:opacity-60"
                  >
                    {busy === m.id ? 'Downloading…' : 'Download'}
                  </button>
                </td>
              </tr>
            ))}
            {materials.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-gray-400">No course materials yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
