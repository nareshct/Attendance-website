import { useEffect, useState } from 'react'
import { Card } from '../../components/Card'
import { usePaginatedList } from '../../hooks/usePaginatedList'
import { formatDateTime } from '../../utils/date'

const ACTION_LABELS = {
  invoice_mark_received: 'Marked invoice received',
  payout_mark_paid: 'Marked payout paid',
  installment_mark_paid: 'Marked installment paid',
  installment_revoke: 'Undid installment payment',
  enrollment_transfer: 'Transferred enrollment',
  attendance_delete: 'Deleted attendance record',
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
  batch_delete: 'Deleted batch',
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
      <p className="text-sm text-gray-500 mb-6">
        A trail of sensitive actions — payments, transfers, and deletions — showing who did what and when.
      </p>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <Card className="p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-left">
            <tr>
              <th className="px-4 py-3">When</th>
              <th className="px-4 py-3">Who</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Record</th>
              <th className="px-4 py-3">Detail</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id} className="border-t border-gray-100">
                <td className="px-4 py-3 whitespace-nowrap">{formatDateTime(log.created_at)}</td>
                <td className="px-4 py-3">{log.actor_name}</td>
                <td className="px-4 py-3">{ACTION_LABELS[log.action] || log.action}</td>
                <td className="px-4 py-3">{log.object_repr}</td>
                <td className="px-4 py-3 text-gray-500">{log.detail || '—'}</td>
              </tr>
            ))}
            {!loading && logs.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-gray-400">No activity recorded yet.</td></tr>
            )}
            {loading && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-gray-400">Loading…</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      {!loading && logs.length > 0 && (
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-gray-400">Showing {logs.length} of {count}</p>
          <div className="flex gap-4">
            {page > 1 && (
              <button onClick={loadLess} className="text-xs text-brand-blue hover:underline">
                Load less
              </button>
            )}
            {hasMore && (
              <button
                disabled={loadingMore}
                onClick={loadMore}
                className="text-xs text-brand-blue hover:underline disabled:opacity-60"
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
