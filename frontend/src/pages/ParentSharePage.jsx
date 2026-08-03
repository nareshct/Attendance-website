import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { downloadFile, getParentView } from '../api/client'
import { Badge } from '../components/Badge'
import { Card } from '../components/Card'
import { formatDate } from '../utils/date'
import { formatDays, formatTime } from '../utils/schedule'

export default function ParentSharePage() {
  const { token } = useParams()
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState('')
  const [downloadingId, setDownloadingId] = useState(null)
  const [downloadError, setDownloadError] = useState('')

  useEffect(() => {
    getParentView(token).then(setProfile).catch((err) => setError(err.message || 'This link is invalid or has been revoked.'))
  }, [token])

  async function handleDownloadCertificate(enrollmentId) {
    setDownloadingId(enrollmentId)
    setDownloadError('')
    try {
      await downloadFile(`/api/parent-view/${token}/enrollments/${enrollmentId}/certificate/`)
    } catch (err) {
      setDownloadError(err.message)
    } finally {
      setDownloadingId(null)
    }
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <Card className="max-w-sm text-center">
          <p className="text-red-600 text-sm">{error}</p>
        </Card>
      </div>
    )
  }

  if (!profile) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-400 text-sm">Loading…</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-semibold text-navy mb-1">{profile.name}</h1>
        <p className="text-sm text-gray-500 mb-6">Std {profile.grade} · {profile.student_id}</p>

        {downloadError && <p className="text-red-600 text-sm mb-4">{downloadError}</p>}

        {profile.enrollments.map((e) => (
          <Card key={e.id} className="mb-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-medium text-navy">{e.course_name}</h2>
              <div className="flex items-center gap-3">
                {e.status === 'completed' && (
                  <button
                    disabled={downloadingId === e.id}
                    onClick={() => handleDownloadCertificate(e.id)}
                    className="text-xs text-brand-green hover:underline disabled:opacity-60"
                  >
                    {downloadingId === e.id ? 'Downloading…' : 'Download certificate'}
                  </button>
                )}
                <Badge status={e.status} />
              </div>
            </div>
            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm mb-4">
              <div><dt className="text-gray-500">Trainer</dt><dd>{e.trainer_name}</dd></div>
              <div><dt className="text-gray-500">Batch</dt><dd>{e.batch_number}</dd></div>
              <div><dt className="text-gray-500">Progress</dt><dd>{e.classes_completed}/{e.classes_total}</dd></div>
              <div>
                <dt className="text-gray-500">Schedule</dt>
                <dd>{formatDays(e.class_days)}{e.class_time && ` · ${formatTime(e.class_time)}`}</dd>
              </div>
            </dl>

            {e.payment_plan && (
              <div className="border-t border-gray-100 pt-3 mb-4">
                <p className="text-xs font-medium text-navy mb-2">
                  Payment plan — {e.payment_plan.plan_type_display} · Total ₹{e.payment_plan.total_amount}
                </p>
                {Number(e.payment_plan.refunded_amount) > 0 && (
                  <p className="text-xs text-red-600 mb-2">
                    Refunded ₹{e.payment_plan.refunded_amount}
                    {e.payment_plan.refund_note && ` — ${e.payment_plan.refund_note}`}
                  </p>
                )}
                <table className="w-full text-xs">
                  <thead className="text-gray-500 text-left">
                    <tr>
                      <th className="py-1 pr-4">Due</th>
                      <th className="py-1 pr-4">Amount</th>
                      <th className="py-1"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {e.payment_plan.installments.map((inst) => (
                      <tr key={inst.id} className="border-t border-gray-50">
                        <td className="py-1 pr-4">
                          {inst.due_at_classes === null ? 'Before class 1' : `Before class ${inst.due_at_classes}`}
                        </td>
                        <td className="py-1 pr-4">₹{inst.amount}</td>
                        <td className="py-1 text-right">
                          {inst.paid_status === 'paid' ? (
                            <span className="text-brand-green">
                              Paid{inst.paid_date ? ` on ${formatDate(inst.paid_date)}` : ''}
                            </span>
                          ) : inst.paid_status === 'cancelled' ? (
                            <span className="text-gray-400">Cancelled</span>
                          ) : (
                            <span className="text-brand-amber">Pending</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {e.recent_classes.length > 0 && (
              <div className="border-t border-gray-100 pt-3">
                <p className="text-xs font-medium text-navy mb-2">Recent classes</p>
                <ul className="text-xs text-gray-600 space-y-1">
                  {e.recent_classes.map((c, j) => (
                    <li key={j}>{formatDate(c.date)} — {c.topic_covered || '—'}</li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        ))}
        {profile.enrollments.length === 0 && (
          <Card className="text-center text-gray-400 text-sm">No enrollments yet.</Card>
        )}
      </div>
    </div>
  )
}
