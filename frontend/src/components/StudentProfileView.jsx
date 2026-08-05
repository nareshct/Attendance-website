import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { downloadFile } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { useApi } from '../hooks/useApi'
import { formatDate, formatWeekday } from '../utils/date'
import { formatDays, formatTime } from '../utils/schedule'
import { Badge } from './Badge'
import { Button } from './Button'
import { Card } from './Card'
import { ConfirmDialog } from './ConfirmDialog'
import { Modal } from './Modal'
import { SearchableSelect } from './SearchableSelect'

const GRADES = Array.from({ length: 10 }, (_, i) => String(i + 3)) // std 3-12

export function StudentProfileView({ studentId, backTo, backLabel, allowTransfer = false, allowEdit = false }) {
  const api = useApi()
  const { auth } = useAuth()
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(null)
  const [sessionsByEnrollment, setSessionsByEnrollment] = useState({})
  const [loadingSessions, setLoadingSessions] = useState(null)
  const [trainers, setTrainers] = useState([])
  const [transferId, setTransferId] = useState(null)
  const [transferTrainer, setTransferTrainer] = useState('')
  const [transferring, setTransferring] = useState(false)
  const [transferError, setTransferError] = useState('')

  const [clients, setClients] = useState([])
  const [editingProfile, setEditingProfile] = useState(false)
  const [profileForm, setProfileForm] = useState(null)
  const [profileError, setProfileError] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)

  const [deleteSessionTarget, setDeleteSessionTarget] = useState(null)
  const [deletingSession, setDeletingSession] = useState(false)
  const [deleteSessionError, setDeleteSessionError] = useState('')

  const [downloadingReportId, setDownloadingReportId] = useState(null)
  const [downloadReportError, setDownloadReportError] = useState('')

  const [downloadingCertificateId, setDownloadingCertificateId] = useState(null)
  const [downloadCertificateError, setDownloadCertificateError] = useState('')

  const [markingPaidId, setMarkingPaidId] = useState(null)
  const [markPaidError, setMarkPaidError] = useState('')

  const [showParentLink, setShowParentLink] = useState(false)
  const [parentLink, setParentLink] = useState(null)
  const [parentLinkBusy, setParentLinkBusy] = useState(false)
  const [parentLinkError, setParentLinkError] = useState('')
  const [copied, setCopied] = useState(false)

  const loadProfile = useCallback(() => {
    return api(`/api/students/${studentId}/profile/`).then(setProfile)
  }, [api, studentId])

  useEffect(() => {
    loadProfile().catch((err) => setError(err.message))
  }, [loadProfile])

  useEffect(() => {
    if (allowTransfer) {
      api('/api/trainers/').then((t) => setTrainers(t.filter((x) => x.status === 'active'))).catch(() => {})
    }
  }, [api, allowTransfer])

  useEffect(() => {
    if (allowEdit) {
      api('/api/clients/').then(setClients).catch(() => {})
    }
  }, [api, allowEdit])

  function openEditProfile() {
    setProfileForm({
      name: profile.name,
      grade: profile.grade,
      source_type: profile.source_type,
      client: profile.client || '',
      parent_name: profile.parent_name,
      parent_phone_number: profile.parent_phone_number,
      place: profile.place,
    })
    setProfileError('')
    setEditingProfile(true)
  }

  function closeEditProfile() {
    setEditingProfile(false)
    setProfileForm(null)
    setProfileError('')
  }

  async function handleSaveProfile(e) {
    e.preventDefault()
    setSavingProfile(true)
    setProfileError('')
    try {
      await api(`/api/students/${studentId}/`, {
        method: 'PATCH',
        body: {
          name: profileForm.name,
          grade: profileForm.grade,
          source_type: profileForm.source_type,
          client: profileForm.source_type === 'B2B' ? (profileForm.client || null) : null,
          parent_name: profileForm.parent_name,
          parent_phone_number: profileForm.parent_phone_number,
          place: profileForm.place,
        },
      })
      closeEditProfile()
      await loadProfile()
    } catch (err) {
      setProfileError(err.message)
    } finally {
      setSavingProfile(false)
    }
  }

  function openTransfer(enrollmentId) {
    setTransferId(enrollmentId)
    setTransferTrainer('')
    setTransferError('')
  }

  function closeTransfer() {
    setTransferId(null)
    setTransferTrainer('')
    setTransferError('')
  }

  async function handleTransfer(enrollmentId) {
    setTransferring(true)
    setTransferError('')
    try {
      await api(`/api/enrollments/${enrollmentId}/transfer/`, {
        method: 'POST',
        body: { trainer: Number(transferTrainer) },
      })
      closeTransfer()
      await loadProfile()
    } catch (err) {
      setTransferError(err.message)
    } finally {
      setTransferring(false)
    }
  }

  async function toggleHistory(enrollmentId) {
    if (expanded === enrollmentId) {
      setExpanded(null)
      return
    }
    setExpanded(enrollmentId)
    if (!sessionsByEnrollment[enrollmentId]) {
      setLoadingSessions(enrollmentId)
      setError('')
      try {
        const sessions = await api(`/api/attendance/?enrollment=${enrollmentId}`)
        setSessionsByEnrollment((prev) => ({ ...prev, [enrollmentId]: sessions }))
      } catch (err) {
        setError(err.message)
      } finally {
        setLoadingSessions(null)
      }
    }
  }

  async function handleDownloadReport(enrollmentId) {
    setDownloadingReportId(enrollmentId)
    setDownloadReportError('')
    try {
      await downloadFile(`/api/enrollments/${enrollmentId}/report/`, auth.token)
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
      await downloadFile(`/api/enrollments/${enrollmentId}/certificate/`, auth.token)
    } catch (err) {
      setDownloadCertificateError(err.message)
    } finally {
      setDownloadingCertificateId(null)
    }
  }

  async function handleMarkPaid(installmentId) {
    setMarkingPaidId(installmentId)
    setMarkPaidError('')
    try {
      await api(`/api/installments/${installmentId}/mark_paid/`, { method: 'POST' })
      await loadProfile()
    } catch (err) {
      setMarkPaidError(err.message)
    } finally {
      setMarkingPaidId(null)
    }
  }

  async function handleRevokePaid(installmentId) {
    setMarkingPaidId(installmentId)
    setMarkPaidError('')
    try {
      await api(`/api/installments/${installmentId}/revoke/`, { method: 'POST' })
      await loadProfile()
    } catch (err) {
      setMarkPaidError(err.message)
    } finally {
      setMarkingPaidId(null)
    }
  }

  function openDeleteSession(enrollmentId, sessionId) {
    setDeleteSessionTarget({ enrollmentId, sessionId })
    setDeleteSessionError('')
  }

  function closeDeleteSession() {
    setDeleteSessionTarget(null)
    setDeleteSessionError('')
  }

  async function confirmDeleteSession() {
    const { enrollmentId, sessionId } = deleteSessionTarget
    setDeletingSession(true)
    setDeleteSessionError('')
    try {
      await api(`/api/attendance/${sessionId}/`, { method: 'DELETE' })
      setSessionsByEnrollment((prev) => ({
        ...prev,
        [enrollmentId]: prev[enrollmentId].filter((s) => s.id !== sessionId),
      }))
      setDeleteSessionTarget(null)
      // Deleting a present class shifts the enrollment's classes_completed/status.
      await loadProfile()
    } catch (err) {
      setDeleteSessionError(err.message)
    } finally {
      setDeletingSession(false)
    }
  }

  async function toggleParentLink() {
    if (showParentLink) {
      setShowParentLink(false)
      return
    }
    setShowParentLink(true)
    if (!parentLink) {
      setParentLinkBusy(true)
      setParentLinkError('')
      try {
        setParentLink(await api(`/api/students/${studentId}/parent_link/`))
      } catch (err) {
        setParentLinkError(err.message)
      } finally {
        setParentLinkBusy(false)
      }
    }
  }

  async function handleRegenerateParentLink() {
    setParentLinkBusy(true)
    setParentLinkError('')
    try {
      setParentLink(await api(`/api/students/${studentId}/regenerate_parent_link/`, { method: 'POST' }))
    } catch (err) {
      setParentLinkError(err.message)
    } finally {
      setParentLinkBusy(false)
    }
  }

  async function handleRevokeParentLink() {
    setParentLinkBusy(true)
    setParentLinkError('')
    try {
      setParentLink(await api(`/api/students/${studentId}/revoke_parent_link/`, { method: 'POST' }))
    } catch (err) {
      setParentLinkError(err.message)
    } finally {
      setParentLinkBusy(false)
    }
  }

  function handleCopyParentLink() {
    navigator.clipboard.writeText(parentLink.url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  if (error && !profile) return <p className="text-error text-sm">{error}</p>
  if (!profile) return <p className="text-text-tertiary text-sm">Loading…</p>

  const transferTarget = profile.enrollments.find((en) => en.id === transferId)

  return (
    <div>
      <Link to={backTo} className="text-sm font-medium text-primary hover:underline focus-ring">&larr; {backLabel}</Link>

      <div className="flex flex-wrap items-center justify-between gap-3 mt-3 mb-6">
        <h1 className="text-2xl font-semibold text-navy">{profile.name}</h1>
        <div className="flex flex-wrap items-center gap-3">
          <Badge status={profile.status} />
          {allowEdit && (
            <Button variant="secondary" onClick={toggleParentLink}>
              {showParentLink ? 'Hide parent link' : 'Parent link'}
            </Button>
          )}
          {allowEdit && !editingProfile && (
            <Button variant="success" onClick={openEditProfile}>Edit details</Button>
          )}
        </div>
      </div>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      {allowEdit && (
        <Modal open={showParentLink} onClose={toggleParentLink} title="Parent share link">
          <p className="text-xs text-text-secondary mb-3">
            A private, read-only link — no login required. Anyone with it can see this student's schedule,
            progress, and payment plan. Regenerate if it's ever shared by mistake.
          </p>
          {parentLinkBusy && !parentLink ? (
            <p className="text-sm text-text-tertiary">Loading…</p>
          ) : parentLink ? (
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <code className="text-xs bg-surface-sunken border border-gray-200 rounded px-2 py-1 break-all">
                  {parentLink.url}
                </code>
                {parentLink.revoked && <Badge status="denied" />}
              </div>
              <div className="flex gap-3 mt-3 text-sm">
                <button onClick={handleCopyParentLink} className="font-medium text-primary hover:underline focus-ring">
                  {copied ? 'Copied!' : 'Copy link'}
                </button>
                <button disabled={parentLinkBusy} onClick={handleRegenerateParentLink} className="font-medium text-primary hover:underline disabled:opacity-60 focus-ring">
                  Regenerate
                </button>
                {!parentLink.revoked && (
                  <button disabled={parentLinkBusy} onClick={handleRevokeParentLink} className="font-medium text-error hover:underline disabled:opacity-60 focus-ring">
                    Revoke
                  </button>
                )}
              </div>
            </div>
          ) : null}
          {parentLinkError && <p className="text-error text-xs mt-2">{parentLinkError}</p>}
        </Modal>
      )}

      <Card className="mb-6">
        <dl className={`grid grid-cols-2 gap-4 text-sm mb-2 ${profile.source_type !== undefined ? 'sm:grid-cols-3' : 'sm:grid-cols-4'}`}>
          <div><dt className="text-text-secondary">Student ID</dt><dd className="font-mono">{profile.student_id}</dd></div>
          <div><dt className="text-text-secondary">Grade</dt><dd>{profile.grade}</dd></div>
          {profile.source_type !== undefined && (
            <div><dt className="text-text-secondary">Source</dt><dd>{profile.source_type}</dd></div>
          )}
          {profile.client_name !== undefined && (
            <div>
              <dt className="text-text-secondary">Client</dt>
              <dd>
                {profile.client ? (
                  <Link to={`/admin/clients/${profile.client}`} className="text-primary hover:underline focus-ring">{profile.client_name}</Link>
                ) : (
                  profile.client_name || '—'
                )}
              </dd>
            </div>
          )}
          <div><dt className="text-text-secondary">Parent name</dt><dd>{profile.parent_name}</dd></div>
          {profile.parent_phone_number !== undefined && (
            <div><dt className="text-text-secondary">Parent phone</dt><dd>{profile.parent_phone_number}</dd></div>
          )}
          <div><dt className="text-text-secondary">Place</dt><dd>{profile.place}</dd></div>
        </dl>
      </Card>

      {allowEdit && (
        <Modal open={editingProfile} onClose={closeEditProfile} title="Edit student details" maxWidthClass="max-w-2xl">
          <form onSubmit={handleSaveProfile} className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-text-secondary mb-1">Name</label>
                <input required maxLength={255} value={profileForm?.name ?? ''} onChange={(e) => setProfileForm({ ...profileForm, name: e.target.value })} className="input" />
              </div>
              <div>
                <label className="block text-xs text-text-secondary mb-1">Grade</label>
                <select required value={profileForm?.grade ?? ''} onChange={(e) => setProfileForm({ ...profileForm, grade: e.target.value })} className="input">
                  {GRADES.map((g) => <option key={g} value={g}>Std {g}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-text-secondary mb-1">Source</label>
                <select
                  value={profileForm?.source_type ?? 'B2C'}
                  onChange={(e) => setProfileForm({ ...profileForm, source_type: e.target.value, client: '' })}
                  className="input"
                >
                  <option value="B2C">B2C</option>
                  <option value="B2B">B2B</option>
                </select>
              </div>
              {profileForm?.source_type === 'B2B' && (
                <div>
                  <label className="block text-xs text-text-secondary mb-1">Client</label>
                  <select required value={profileForm.client} onChange={(e) => setProfileForm({ ...profileForm, client: e.target.value })} className="input">
                    <option value="">Select client…</option>
                    {clients.map((c) => (
                      <option key={c.id} value={c.id}>{c.company_name}</option>
                    ))}
                  </select>
                </div>
              )}
              <div>
                <label className="block text-xs text-text-secondary mb-1">Parent name</label>
                <input maxLength={255} value={profileForm?.parent_name ?? ''} onChange={(e) => setProfileForm({ ...profileForm, parent_name: e.target.value })} className="input" />
              </div>
              <div>
                <label className="block text-xs text-text-secondary mb-1">Parent phone</label>
                <input maxLength={20} value={profileForm?.parent_phone_number ?? ''} onChange={(e) => setProfileForm({ ...profileForm, parent_phone_number: e.target.value })} className="input" />
              </div>
              <div>
                <label className="block text-xs text-text-secondary mb-1">Place</label>
                <input maxLength={255} value={profileForm?.place ?? ''} onChange={(e) => setProfileForm({ ...profileForm, place: e.target.value })} className="input" />
              </div>
            </div>
            {profileError && <p className="text-error text-xs">{profileError}</p>}
            <div className="flex justify-end gap-3">
              <Button type="button" variant="ghost" onClick={closeEditProfile}>
                Cancel
              </Button>
              <Button type="submit" variant="success" disabled={savingProfile}>
                {savingProfile ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {allowTransfer && (
        <Modal open={transferId != null} onClose={closeTransfer} title="Transfer student">
          {transferTarget && (
            <div className="space-y-3">
              <p className="text-sm text-text-secondary">
                {transferTarget.course_name} — Batch {transferTarget.batch_number}
                <br />
                Currently with <span className="font-medium text-navy">{transferTarget.trainer_name}</span>
              </p>
              <SearchableSelect
                placeholder="Search trainer…"
                value={transferTrainer}
                onChange={setTransferTrainer}
                options={trainers.filter((t) => t.id !== transferTarget.trainer).map((t) => ({ value: t.id, label: t.name }))}
              />
              {transferError && <p className="text-error text-xs">{transferError}</p>}
              <div className="flex justify-end gap-3">
                <Button type="button" variant="ghost" onClick={closeTransfer}>
                  Cancel
                </Button>
                <Button
                  type="button"
                  variant="success"
                  disabled={!transferTrainer || transferring}
                  onClick={() => handleTransfer(transferTarget.id)}
                >
                  {transferring ? 'Transferring…' : 'Confirm'}
                </Button>
              </div>
            </div>
          )}
        </Modal>
      )}

      <h2 className="text-lg font-semibold text-navy mb-3">Batch history</h2>
      {downloadReportError && <p className="text-error text-xs mb-3">{downloadReportError}</p>}
      {downloadCertificateError && <p className="text-error text-xs mb-3">{downloadCertificateError}</p>}
      <div className="space-y-3">
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
                  {downloadingReportId === e.id ? 'Downloading…' : 'Download PDF'}
                </button>
                {e.status === 'completed' && (
                  <button
                    disabled={downloadingCertificateId === e.id}
                    onClick={() => handleDownloadCertificate(e.id)}
                    className="text-xs font-medium text-success hover:underline disabled:opacity-60 focus-ring"
                  >
                    {downloadingCertificateId === e.id ? 'Downloading…' : 'Download certificate'}
                  </button>
                )}
              </div>
            </div>
            <p className="text-sm text-text-secondary mb-2">
              Trainer:{' '}
              {allowEdit ? (
                <Link
                  to={`/admin/trainers/${e.trainer}`}
                  state={{ from: `/admin/students/${studentId}`, fromLabel: `Back to ${profile.name}` }}
                  className="text-primary hover:underline focus-ring"
                >
                  {e.trainer_name}
                </Link>
              ) : (
                e.trainer_name
              )}{' '}
              · {e.classes_completed}/{e.classes_total} classes · started {formatDate(e.start_date)}
              {e.class_days ? ` · ${formatDays(e.class_days)}${e.class_time ? ` at ${formatTime(e.class_time)}` : ''}` : ''}
            </p>

            <div className="flex items-center gap-3">
              <button onClick={() => toggleHistory(e.id)} className="text-xs font-medium text-primary hover:underline focus-ring">
                {expanded === e.id ? 'Hide class history' : 'View class history'}
              </button>
              {allowTransfer && e.status === 'ongoing' && (
                <button onClick={() => openTransfer(e.id)} className="text-xs font-medium text-primary hover:underline focus-ring">
                  Transfer
                </button>
              )}
            </div>

            {expanded === e.id && (
              <div className="mt-3 border-t border-gray-100 pt-3">
                {loadingSessions === e.id && <p className="text-xs text-text-tertiary">Loading…</p>}
                {sessionsByEnrollment[e.id] && sessionsByEnrollment[e.id].length === 0 && (
                  <div className="rounded-lg border border-dashed border-gray-200 py-6 text-center">
                    <p className="text-xs text-text-tertiary">No classes taken yet.</p>
                  </div>
                )}
                {sessionsByEnrollment[e.id] && sessionsByEnrollment[e.id].length > 0 && (
                  <>
                    <p className="text-xs text-text-secondary mb-2">
                      {sessionsByEnrollment[e.id].length} class{sessionsByEnrollment[e.id].length === 1 ? '' : 'es'} recorded
                    </p>
                    <div className="rounded-lg border border-gray-100 overflow-hidden">
                      <table className="table">
                        <thead>
                          <tr className="table-head-row">
                            <th className="table-head-cell w-12">#</th>
                            <th className="table-head-cell">Date</th>
                            <th className="table-head-cell">Topic covered</th>
                            {allowEdit && <th className="table-head-cell"></th>}
                          </tr>
                        </thead>
                        <tbody>
                          {sessionsByEnrollment[e.id].map((s, idx) => {
                            const num = sessionsByEnrollment[e.id].length - idx
                            const isSubstitute = s.marked_by_name && s.marked_by_name !== e.trainer_name
                            return (
                              <tr key={s.id} className="table-row">
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
                                <td className="table-cell text-text-secondary">
                                  {s.topic_covered || '—'}
                                  {isSubstitute && (
                                    <div className="mt-0.5 text-xs text-warning">via substitute — {s.marked_by_name}</div>
                                  )}
                                </td>
                                {allowEdit && (
                                  <td className="table-cell text-right whitespace-nowrap">
                                    {s.in_closed_cycle ? (
                                      <span className="text-text-tertiary text-xs">Locked</span>
                                    ) : (
                                      <button onClick={() => openDeleteSession(e.id, s.id)} className="text-xs font-medium text-error hover:underline focus-ring">
                                        Delete
                                      </button>
                                    )}
                                  </td>
                                )}
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

            {allowEdit && e.payment_plan && (
              <div className="mt-3 border-t border-gray-100 pt-3">
                <p className="text-xs font-medium text-navy mb-2">
                  Payment plan — {e.payment_plan.plan_type_display} · Total ₹{e.payment_plan.total_amount}
                </p>
                {Number(e.payment_plan.refunded_amount) > 0 && (
                  <p className="text-xs text-error mb-2">
                    Refunded ₹{e.payment_plan.refunded_amount}
                    {e.payment_plan.refund_note && ` — ${e.payment_plan.refund_note}`}
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
                        <td className="table-compact-cell whitespace-nowrap">
                          {inst.paid_status === 'cancelled' ? (
                            <span className="text-text-tertiary">Cancelled</span>
                          ) : inst.paid_status === 'paid' ? (
                            markingPaidId === inst.id ? (
                              <span className="text-text-tertiary">Undoing…</span>
                            ) : (
                              <span className="text-success">
                                Paid{inst.paid_date ? ` on ${formatDate(inst.paid_date)}` : ''}
                                {' · '}
                                <button onClick={() => handleRevokePaid(inst.id)} className="text-text-tertiary hover:text-error hover:underline focus-ring">
                                  Undo
                                </button>
                              </span>
                            )
                          ) : markingPaidId === inst.id ? (
                            <span className="text-text-tertiary">Marking…</span>
                          ) : (
                            <button onClick={() => handleMarkPaid(inst.id)} className="font-medium text-primary hover:underline focus-ring">
                              Mark as paid
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {markPaidError && <p className="text-error text-xs mt-2">{markPaidError}</p>}
              </div>
            )}
          </Card>
        ))}
        {profile.enrollments.length === 0 && <p className="text-text-tertiary text-sm">No enrollments yet.</p>}
      </div>

      <ConfirmDialog
        open={deleteSessionTarget != null}
        onClose={closeDeleteSession}
        onConfirm={confirmDeleteSession}
        title="Delete class record"
        message="Delete this class record? This cannot be undone."
        confirmLabel="Delete"
        busyLabel="Deleting…"
        danger
        busy={deletingSession}
        error={deleteSessionError}
      />
    </div>
  )
}
