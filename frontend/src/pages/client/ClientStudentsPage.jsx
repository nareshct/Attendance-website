import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { useApi } from '../../hooks/useApi'

export default function ClientStudentsPage() {
  const api = useApi()
  const [students, setStudents] = useState([])
  const [statusTab, setStatusTab] = useState('active')
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    api('/api/my-client-students/')
      .then((data) => {
        if (!cancelled) setStudents(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [api])

  const term = search.trim().toLowerCase()
  const filtered = students
    .filter((s) => s.status === statusTab)
    .filter((s) => !term || s.name.toLowerCase().includes(term) || s.student_id.toLowerCase().includes(term))

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">My Students</h1>

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

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">#</th>
              <th className="table-head-cell">Student ID</th>
              <th className="table-head-cell">Name</th>
              <th className="table-head-cell">Course/Batch</th>
              <th className="table-head-cell">Progress</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s, i) => (
              <tr key={s.id} className="table-row">
                <td className="table-cell text-text-tertiary">{i + 1}</td>
                <td className="table-cell font-mono text-xs">{s.student_id}</td>
                <td className="table-cell">
                  <Link to={`/client/students/${s.id}`} className="font-medium text-primary hover:underline focus-ring">
                    {s.name}
                  </Link>
                </td>
                <td className="table-cell">{s.course_batch || '—'}</td>
                <td className="table-cell tabular-nums">
                  {s.progress || (s.course_batch ? <span className="text-text-tertiary text-xs">not tracked per student</span> : '—')}
                </td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">
                {term ? 'No students match your search.' : `No ${statusTab} students.`}
              </td></tr>
            )}
            {loading && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">Loading…</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
