import { useEffect, useState } from 'react'
import { Card } from '../../components/Card'
import { usePaginatedList } from '../../hooks/usePaginatedList'
import { formatDateTime } from '../../utils/date'

const ACTION_LABELS = {
  // Billing / invoicing
  invoice_mark_received: 'Marked invoice received',
  payout_mark_paid: 'Marked payout paid',
  payout_cancel: 'Cancelled payout',
  billing_cycle_close: 'Closed billing cycle',
  billing_cycle_reopen: 'Reopened billing cycle',
  installment_mark_paid: 'Marked installment paid',
  installment_revoke: 'Undid installment payment',
  payment_plan_recalculate: 'Recalculated payment plan',

  // Enrollments / attendance
  enrollment_transfer: 'Transferred enrollment',
  enrollment_withdraw: 'Withdrew enrollment',
  enrollment_status_change: 'Enrollment status changed',
  attendance_delete: 'Deleted attendance record',
  substitute_assign: 'Assigned substitute trainer',
  substitute_cancel: 'Cancelled substitute assignment',

  // Students
  student_archive: 'Archived student',
  student_unarchive: 'Unarchived student',
  parent_link_create: 'Created parent share link',
  parent_link_regenerate: 'Regenerated parent share link',
  parent_link_revoke: 'Revoked parent share link',

  // Trainers
  trainer_create: 'Onboarded trainer',
  trainer_edit: 'Edited trainer details',
  trainer_archive: 'Archived trainer',
  trainer_unarchive: 'Unarchived trainer',
  trainer_reset_password: "Reset trainer's password",
  trainer_course_rate_create: 'Added trainer course-rate override',
  trainer_course_rate_edit: 'Edited trainer course-rate override',
  trainer_course_rate_delete: 'Removed trainer course-rate override',
  payout_settle_current_cycle: 'Settled current-cycle payout early',

  // Courses / clients
  course_rate_change: 'Changed course rate',
  client_archive: 'Archived client',
  client_unarchive: 'Unarchived client',

  // Batches
  batch_enroll: 'Added student to batch',
  batch_withdraw: 'Withdrew student from batch',
  batch_reactivate: 'Reactivated withdrawn batch student',
  batch_enrollment_edit: 'Edited batch enrollment details',
  batch_enrollment_delete: 'Removed student from batch',
  batch_convert_guest: 'Registered a batch guest as a student',
  batch_import_students: 'Imported students into batch from Excel',
  batch_installment_mark_paid: 'Marked batch installment paid',
  batch_installment_amount_edit: 'Edited batch installment amount',
  batch_payout_create: 'Added batch payout',
  batch_payout_mark_paid: 'Marked batch payout paid',
  batch_payout_cancel: 'Cancelled batch payout',
  batch_payout_delete: 'Deleted batch payout',
  batch_session_edit: 'Edited batch session',
  batch_session_delete: 'Deleted batch session',
  batch_delete: 'Deleted batch',

  // Auth
  login: 'Logged in',
  password_change: 'Changed password',
  password_reset: 'Reset password',
}

export default function ActivityLogPage() {
  const { items: logs, count, hasMore, loading, loadingMore, reload, loadMore, loadLess, page } =
    usePaginatedList('/api/audit-log/')
  const [error, setError] = useState('')

  useEffect(() => {
    reload().catch((err) => setError(err.message))
  }, [reload])

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-2">Activity Log</h1>
      <p className="text-sm text-text-secondary mb-6">
        A trail of sensitive actions — payments, transfers, and deletions — showing who did what and when.
      </p>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">When</th>
              <th className="table-head-cell">Who</th>
              <th className="table-head-cell">Action</th>
              <th className="table-head-cell">Record</th>
              <th className="table-head-cell">Detail</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id} className="table-row">
                <td className="table-cell whitespace-nowrap">{formatDateTime(log.created_at)}</td>
                <td className="table-cell">{log.actor_name}</td>
                <td className="table-cell">{ACTION_LABELS[log.action] || log.action}</td>
                <td className="table-cell">{log.object_repr}</td>
                <td className="table-cell text-text-secondary">{log.detail || '—'}</td>
              </tr>
            ))}
            {!loading && logs.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">No activity recorded yet.</td></tr>
            )}
            {loading && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">Loading…</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      {!loading && logs.length > 0 && (
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-text-tertiary">Showing {logs.length} of {count}</p>
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
    </div>
  )
}
