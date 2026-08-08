import { Link } from 'react-router-dom'
import { Modal } from './Modal'

// Shared by TrainerDetailPage and ClientDetailPage — the "Active students" stat
// on both is clickable and opens this same serial-no/student/course/progress
// breakdown, one row per ongoing enrollment (a student with two ongoing batches
// gets two rows, same as the underlying count).
export function ActiveStudentsModal({ open, onClose, title, rows }) {
  return (
    <Modal open={open} onClose={onClose} title={title} maxWidthClass="max-w-2xl">
      <div className="overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">#</th>
              <th className="table-head-cell">Student</th>
              <th className="table-head-cell">Course</th>
              <th className="table-head-cell">Progress</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.id} className="table-row">
                <td className="table-cell text-text-tertiary">{i + 1}</td>
                <td className="table-cell">
                  <Link to={`/admin/students/${r.studentId}`} className="font-medium text-primary hover:underline focus-ring">
                    {r.studentName}
                  </Link>
                </td>
                <td className="table-cell">{r.courseName}</td>
                <td className="table-cell tabular-nums">{r.classesCompleted}/{r.classesTotal}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-text-tertiary">No active students.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Modal>
  )
}
