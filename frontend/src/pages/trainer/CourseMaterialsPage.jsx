import { useEffect, useMemo, useState } from 'react'
import { downloadFile } from '../../api/client'
import { Card } from '../../components/Card'
import { SearchableSelect } from '../../components/SearchableSelect'
import { useAuth } from '../../hooks/useAuth'
import { useApi } from '../../hooks/useApi'
import { usePickerSearch } from '../../hooks/usePickerSearch'
import { formatDate } from '../../utils/date'

function loadCourseFilterOptions(pickerSearch, query) {
  return pickerSearch.courses(query).then((cs) => (query ? cs : [{ value: '', label: 'All courses' }, ...cs]))
}

// One section per course, each listing that course's own files — replaces a flat
// table that repeated the course name on every row.
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
  const [courseFilter, setCourseFilter] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

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

  const groups = useMemo(() => groupByCourse(materials), [materials])

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">Course Materials</h1>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="mb-4 max-w-xs">
        <SearchableSelect
          placeholder="All courses"
          value={courseFilter}
          onChange={setCourseFilter}
          loadOptions={(q) => loadCourseFilterOptions(pickerSearch, q)}
        />
      </div>

      {groups.map((g) => (
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
                  <td className="table-cell text-right">
                    <button
                      disabled={busy === m.id}
                      onClick={() => handleDownload(m.id)}
                      className="text-brand-violet hover:underline disabled:opacity-60 focus-ring"
                    >
                      {busy === m.id ? 'Downloading…' : 'Download'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ))}
      {groups.length === 0 && (
        <Card className="text-center text-gray-400 py-6">No course materials yet.</Card>
      )}
    </div>
  )
}
