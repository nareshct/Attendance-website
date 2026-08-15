import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { useApi } from '../../hooks/useApi'
import { formatDate } from '../../utils/date'
import { formatDays, formatTime } from '../../utils/schedule'

export default function ClientEnrollmentsPage() {
  const api = useApi()
  const [enrollments, setEnrollments] = useState([])
  const [statusTab, setStatusTab] = useState('ongoing')
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    api('/api/my-client-enrollments/')
      .then((data) => {
        if (!cancelled) setEnrollments(data)
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
  const filtered = enrollments
    .filter((e) => e.status === statusTab)
    .filter((e) => !term || e.student_name.toLowerCase().includes(term) || e.course_name.toLowerCase().includes(term))

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">Enrollments</h1>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <input
          placeholder="Search by student or course…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input max-w-sm"
        />
        <div className="flex gap-2 shrink-0">
          {['ongoing', 'completed', 'withdrawn'].map((t) => (
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
              <th className="table-head-cell">Student</th>
              <th className="table-head-cell">Course/Batch</th>
              <th className="table-head-cell">Progress</th>
              <th className="table-head-cell">Schedule</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((e, i) => (
              <tr key={e.id} className="table-row">
                <td className="table-cell text-text-tertiary">{i + 1}</td>
                <td className="table-cell">
                  <Link to={`/client/students/${e.student}`} className="font-medium text-primary hover:underline focus-ring">
                    {e.student_name}
                  </Link>
                </td>
                <td className="table-cell">{e.course_name} — Batch {e.batch_number}</td>
                <td className="table-cell tabular-nums">{e.classes_completed}/{e.classes_total}</td>
                <td className="table-cell text-text-secondary">
                  {formatDate(e.start_date)}
                  {e.class_days ? ` · ${formatDays(e.class_days)}${e.class_time ? ` at ${formatTime(e.class_time)}` : ''}` : ''}
                </td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">
                {term ? 'No enrollments match your search.' : `No ${statusTab} enrollments.`}
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
