import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { downloadFile } from '../../api/client'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import { useAuth } from '../../hooks/useAuth'
import { useApi } from '../../hooks/useApi'
import { formatDate, formatWeekday } from '../../utils/date'
import { formatDays, formatTime } from '../../utils/schedule'

export default function StudentProfilePage() {
  const { id } = useParams()
  const api = useApi()
  const { auth } = useAuth()
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(null)
  const [downloadingReportId, setDownloadingReportId] = useState(null)
  const [downloadReportError, setDownloadReportError] = useState('')
  const [downloadingCertificateId, setDownloadingCertificateId] = useState(null)
  const [downloadCertificateError, setDownloadCertificateError] = useState('')

  useEffect(() => {
    let cancelled = false
    setError('')
    setProfile(null)
    api(`/api/my-client-students/${id}/`)
      .then((data) => {
        if (!cancelled) setProfile(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [api, id])

  async function handleDownloadReport(enrollmentId) {
    setDownloadingReportId(enrollmentId)
    setDownloadReportError('')
    try {
      await downloadFile(`/api/my-client-enrollments/${enrollmentId}/report/`, auth.token)
    } catch (err) {
      setDownloadReportError(err.message)
    } finally {
      setDownloadingReportId(null)
    }
  }

  async function handleDownloadCertificate(enrollmentId) {
    setDownloadingCertificateId(enrollmentId)
    setDownloadCertificateError('')
    try {
      await downloadFile(`/api/my-client-enrollments/${enrollmentId}/certificate/`, auth.token)
    } catch (err) {
      setDownloadCertificateError(err.message)
    } finally {
      setDownloadingCertificateId(null)
    }
  }

  if (error && !profile) return <p className="text-error text-sm">{error}</p>
  if (!profile) return <p className="text-text-tertiary text-sm">Loading…</p>

  return (
    <div>
      <Link to="/client/students" className="text-sm font-medium text-primary hover:underline focus-ring">&larr; Back to my students</Link>

      <div className="flex flex-wrap items-center justify-between gap-3 mt-3 mb-6">
        <h1 className="text-2xl font-semibold text-navy">{profile.name}</h1>
        <Badge status={profile.status} />
      </div>

      <Card className="mb-6">
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
          <div><dt className="text-text-secondary">Student ID</dt><dd className="font-mono">{profile.student_id}</dd></div>
          <div><dt className="text-text-secondary">Grade</dt><dd>Std {profile.grade}</dd></div>
        </dl>
      </Card>

      <h2 className="text-lg font-semibold text-navy mb-3">Enrollments</h2>
      {downloadReportError && <p className="text-error text-xs mb-3">{downloadReportError}</p>}
      {downloadCertificateError && <p className="text-error text-xs mb-3">{downloadCertificateError}</p>}
      <div className="space-y-3 mb-8">
        {profile.enrollments.map((e) => (
          <Card key={e.id}>
            <div className="flex items-center justify-between mb-1">
              <span className="font-medium">{e.course_name} — Batch {e.batch_number}</span>
              <div className="flex flex-col items-end gap-1">
                <Badge status={e.status} />
                <button
                  disabled={downloadingReportId === e.id}
                  onClick={() => handleDownloadReport(e.id)}
                  className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring"
                >
                  {downloadingReportId === e.id ? 'Downloading…' : 'Report (PDF)'}
                </button>
                {e.status === 'completed' && (
                  <button
                    disabled={downloadingCertificateId === e.id}
                    onClick={() => handleDownloadCertificate(e.id)}
                    className="text-xs font-medium text-success hover:underline disabled:opacity-60 focus-ring"
                  >
                    {downloadingCertificateId === e.id ? 'Downloading…' : 'Certificate (PDF)'}
                  </button>
                )}
              </div>
            </div>
            <p className="text-sm text-text-secondary mb-2">
              Trainer: {e.trainer_name} · {e.classes_completed}/{e.classes_total} classes · started {formatDate(e.start_date)}
              {e.class_days ? ` · ${formatDays(e.class_days)}${e.class_time ? ` at ${formatTime(e.class_time)}` : ''}` : ''}
            </p>

            <button
              onClick={() => setExpanded(expanded === e.id ? null : e.id)}
              className="text-xs font-medium text-primary hover:underline focus-ring"
            >
              {expanded === e.id ? 'Hide class history' : 'View class history'}
            </button>

            {expanded === e.id && (
              <div className="mt-3 border-t border-gray-100 pt-3">
                {e.recent_classes.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-gray-200 py-6 text-center">
                    <p className="text-xs text-text-tertiary">No classes taken yet.</p>
                  </div>
                ) : (
                  <>
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
                          {e.recent_classes.map((s, idx) => {
                            const num = e.recent_classes.length - idx
                            return (
                              <tr key={`${e.id}-${s.date}-${idx}`} className="table-row">
                                <td className="table-cell">
                                  <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-primary-tint text-primary text-[11px] font-semibold tabular-nums">
                                    {num}
                                  </span>
                                </td>
                                <td className="table-cell whitespace-nowrap">
                                  <div className="font-medium text-navy">{formatDate(s.date)}</div>
                                  <div className="text-xs text-text-tertiary">
                                    {formatWeekday(s.date)}
                                    {idx === 0 && <span className="ml-1.5 text-primary">· Most recent</span>}
                                  </div>
                                </td>
                                <td className="table-cell text-text-secondary">{s.topic_covered || '—'}</td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            )}
          </Card>
        ))}
        {profile.enrollments.length === 0 && <p className="text-text-tertiary text-sm">No enrollments yet.</p>}
      </div>

      {profile.batch_enrollments.length > 0 && (
        <>
          <h2 className="text-lg font-semibold text-navy mb-3">Batches</h2>
          <div className="space-y-3">
            {profile.batch_enrollments.map((be) => (
              <Card key={be.id}>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium">{be.batch_name}</span>
                  <Badge status={be.status} />
                </div>
                <p className="text-sm text-text-secondary">
                  {be.course_name} · joined {formatDate(be.joined_date)}
                </p>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
