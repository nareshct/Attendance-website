import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { downloadFile, getParentView } from '../api/client'
import { Badge } from '../components/Badge'
import { Card } from '../components/Card'
import { formatDate, formatWeekday } from '../utils/date'
import { formatDays, formatTime } from '../utils/schedule'

export default function ParentSharePage() {
  const { token } = useParams()
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState('')
  const [downloadingId, setDownloadingId] = useState(null)
  const [downloadError, setDownloadError] = useState('')
  const [expandedEnrollmentIds, setExpandedEnrollmentIds] = useState(new Set())

  function toggleClassesExpanded(enrollmentId) {
    setExpandedEnrollmentIds((prev) => {
      const next = new Set(prev)
      if (next.has(enrollmentId)) {
        next.delete(enrollmentId)
      } else {
        next.add(enrollmentId)
      }
      return next
    })
  }

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
          <p className="text-error text-sm">{error}</p>
        </Card>
      </div>
    )
  }

  if (!profile) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-text-tertiary text-sm">Loading…</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-semibold text-navy mb-1">{profile.name}</h1>
        <p className="text-sm text-text-secondary mb-6">Std {profile.grade} · {profile.student_id}</p>

        {downloadError && <p className="text-error text-sm mb-4">{downloadError}</p>}

        {profile.enrollments.map((e) => (
          <Card key={e.id} className="mb-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-medium text-navy">{e.course_name}</h2>
              <div className="flex items-center gap-3">
                {e.status === 'completed' && (
                  <button
                    disabled={downloadingId === e.id}
                    onClick={() => handleDownloadCertificate(e.id)}
                    className="text-xs font-medium text-success hover:underline disabled:opacity-60 focus-ring"
                  >
                    {downloadingId === e.id ? 'Downloading…' : 'Download certificate'}
                  </button>
                )}
                <Badge status={e.status} />
              </div>
            </div>
            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm mb-4">
              <div><dt className="text-text-secondary">Trainer</dt><dd>{e.trainer_name}</dd></div>
              <div><dt className="text-text-secondary">Batch</dt><dd>{e.batch_number}</dd></div>
              <div><dt className="text-text-secondary">Progress</dt><dd className="tabular-nums">{e.classes_completed}/{e.classes_total}</dd></div>
              <div>
                <dt className="text-text-secondary">Schedule</dt>
                <dd>{formatDays(e.class_days)}{e.class_time && ` · ${formatTime(e.class_time)}`}</dd>
              </div>
            </dl>

            {e.payment_plan && (
              <div className="border-t border-gray-100 pt-3 mb-4">
                <p className="text-xs font-medium text-navy mb-2">
                  Payment plan — {e.payment_plan.plan_type_display} · Total ₹{e.payment_plan.total_amount}
                </p>
                {Number(e.payment_plan.refunded_amount) > 0 && (
                  <p className="text-xs text-error mb-2">
                    Refunded ₹{e.payment_plan.refunded_amount}
                  </p>
                )}
                <table className="table-compact">
                  <thead>
                    <tr>
                      <th className="table-compact-head-cell">Due</th>
                      <th className="table-compact-head-cell">Amount</th>
                      <th className="table-compact-head-cell"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {e.payment_plan.installments.map((inst) => (
                      <tr key={inst.id} className="table-compact-row">
                        <td className="table-compact-cell">
                          {inst.due_at_classes === null ? 'Before class 1' : `Before class ${inst.due_at_classes}`}
                        </td>
                        <td className="table-compact-cell tabular-nums">₹{inst.amount}</td>
                        <td className="table-compact-cell">
                          {inst.paid_status === 'paid' ? (
                            <span className="text-success">
                              Paid{inst.paid_date ? ` on ${formatDate(inst.paid_date)}` : ''}
                            </span>
                          ) : inst.paid_status === 'cancelled' ? (
                            <span className="text-text-tertiary">Cancelled</span>
                          ) : (
                            <span className="text-warning">Pending</span>
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
                <button
                  onClick={() => toggleClassesExpanded(e.id)}
                  className="text-xs font-medium text-primary hover:underline focus-ring"
                >
                  {expandedEnrollmentIds.has(e.id) ? 'Hide class history' : 'View class history'}
                </button>

                {expandedEnrollmentIds.has(e.id) && (
                  <div className="mt-3">
                    <p className="text-xs text-text-secondary mb-2">
                      {e.recent_classes.length} class{e.recent_classes.length === 1 ? '' : 'es'} recorded
                    </p>
                    <div className="rounded-lg border border-gray-100 overflow-hidden">
                      <table className="table">
                        <thead>
                          <tr className="table-head-row">
                            <th className="table-head-cell w-12">#</th>
                            <th className="table-head-cell">Date</th>
                            <th className="table-head-cell">Topic covered</th>
                          </tr>
                        </thead>
                        <tbody>
                          {e.recent_classes.map((c, idx) => {
                            const num = e.recent_classes.length - idx
                            return (
                              <tr key={idx} className="table-row">
                                <td className="table-cell">
                                  <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-primary-tint text-primary text-[11px] font-semibold tabular-nums">
                                    {num}
                                  </span>
                                </td>
                                <td className="table-cell whitespace-nowrap">
                                  <div className="font-medium text-navy">{formatDate(c.date)}</div>
                                  <div className="text-xs text-text-tertiary">
                                    {formatWeekday(c.date)}
                                    {idx === 0 && <span className="ml-1.5 text-primary">· Most recent</span>}
                                  </div>
                                </td>
                                <td className="table-cell text-text-secondary">{c.topic_covered || '—'}</td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>
        ))}
        {profile.enrollments.length === 0 && (
          <Card className="text-center text-text-tertiary text-sm">No enrollments yet.</Card>
        )}
      </div>
    </div>
  )
}
