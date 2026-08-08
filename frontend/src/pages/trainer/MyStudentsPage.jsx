import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import { useApi } from '../../hooks/useApi'

export default function MyStudentsPage() {
  const api = useApi()
  const [enrollments, setEnrollments] = useState([])
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState('ongoing')
  const [error, setError] = useState('')

  useEffect(() => {
    api('/api/my-students/').then(setEnrollments).catch((err) => setError(err.message))
  }, [api])

  const filtered = enrollments.filter((e) => {
    if (e.status !== tab) return false
    const q = search.toLowerCase()
    return e.student_name.toLowerCase().includes(q) || e.course_name.toLowerCase().includes(q)
  })

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">My Students</h1>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="flex items-center justify-between gap-3 mb-4">
        <input
          placeholder="Search by student or course…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input max-w-sm"
        />
        <div className="flex gap-2 shrink-0">
          {['ongoing', 'completed'].map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`text-sm rounded-lg px-4 py-2 capitalize ${
                tab === t ? 'bg-brand-violet text-white' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              {tab === 'completed' && <th className="table-head-cell">#</th>}
              <th className="table-head-cell">Student</th>
              <th className="table-head-cell">Course</th>
              <th className="table-head-cell">Batch</th>
              <th className="table-head-cell">Progress</th>
              {tab === 'ongoing' && <th className="table-head-cell">Status</th>}
            </tr>
          </thead>
          <tbody>
            {filtered.map((e, i) => (
              <tr key={e.id} className="table-row">
                {tab === 'completed' && <td className="table-cell text-gray-400">{i + 1}</td>}
                <td className="table-cell">
                  {tab === 'ongoing' ? (
                    <>
                      <Link to={`/trainer/students/${e.student}`} className="text-brand-blue hover:underline focus-ring">{e.student_name}</Link>
                      {e.covering_for && (
                        <span className="block text-xs text-brand-violet mt-1">Covering for {e.covering_for}</span>
                      )}
                    </>
                  ) : (
                    e.student_name
                  )}
                </td>
                <td className="table-cell">{e.course_name}</td>
                <td className="table-cell">{e.batch_number}</td>
                <td className="table-cell">{e.classes_completed}/{e.classes_total}</td>
                {tab === 'ongoing' && (
                  <td className="table-cell">
                    <Badge status={e.status} />
                    {e.payment_blocked && (
                      <span className="block text-xs text-brand-amber mt-1">Payment pending — schedule paused</span>
                    )}
                  </td>
                )}
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={5} className="table-cell text-center text-gray-400">
                {enrollments.length === 0
                  ? 'No students allocated to you yet.'
                  : search
                  ? 'No students match your search.'
                  : `No ${tab} batches.`}
              </td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
