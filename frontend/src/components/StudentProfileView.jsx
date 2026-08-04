import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { downloadFile } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { useApi } from '../hooks/useApi'
import { formatDate } from '../utils/date'
import { formatDays, formatTime } from '../utils/schedule'
import { Badge } from './Badge'
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

  if (error) return <p className="text-red-600 text-sm">{error}</p>
  if (!profile) return <p className="text-gray-400 text-sm">Loading…</p>

  return (
    <div>
      <Link to={backTo} className="text-sm text-brand-blue hover:underline">&larr; {backLabel}</Link>

      <div className="flex flex-wrap items-center justify-between gap-3 mt-3 mb-6">
        <h1 className="text-2xl font-semibold text-navy">{profile.name}</h1>
        <div className="flex flex-wrap items-center gap-3">
          <Badge status={profile.status} />
          {allowEdit && (
            <button onClick={toggleParentLink} className="text-sm rounded-lg border border-brand-blue text-brand-blue px-4 py-2 hover:bg-blue-50">
              {showParentLink ? 'Hide parent link' : 'Parent link'}
            </button>
          )}
          {allowEdit && !editingProfile && (
            <button onClick={openEditProfile} className="text-sm rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800">
              Edit details
            </button>
          )}
        </div>
      </div>

      {allowEdit && (
        <Modal open={showParentLink} onClose={toggleParentLink} title="Parent share link">
          <p className="text-xs text-gray-500 mb-3">
            A private, read-only link — no login required. Anyone with it can see this student's schedule,
            progress, and payment plan. Regenerate if it's ever shared by mistake.
          </p>
          {parentLinkBusy && !parentLink ? (
            <p className="text-sm text-gray-400">Loading…</p>
          ) : parentLink ? (
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <code className="text-xs bg-gray-50 border border-gray-200 rounded px-2 py-1 break-all">
                  {parentLink.url}
                </code>
                {parentLink.revoked && <Badge status="denied" />}
              </div>
              <div className="flex gap-3 mt-3 text-sm">
                <button onClick={handleCopyParentLink} className="text-brand-blue hover:underline">
                  {copied ? 'Copied!' : 'Copy link'}
                </button>
                <button disabled={parentLinkBusy} onClick={handleRegenerateParentLink} className="text-brand-blue hover:underline disabled:opacity-60">
                  Regenerate
                </button>
                {!parentLink.revoked && (
                  <button disabled={parentLinkBusy} onClick={handleRevokeParentLink} className="text-red-600 hover:underline disabled:opacity-60">
                    Revoke
                  </button>
                )}
              </div>
            </div>
          ) : null}
          {parentLinkError && <p className="text-red-600 text-xs mt-2">{parentLinkError}</p>}
        </Modal>
      )}

      <Card className="mb-6">
        <dl className={`grid grid-cols-2 gap-4 text-sm mb-2 ${profile.source_type !== undefined ? 'sm:grid-cols-3' : 'sm:grid-cols-4'}`}>
          <div><dt className="text-gray-500">Student ID</dt><dd className="font-mono">{profile.student_id}</dd></div>
          <div><dt className="text-gray-500">Grade</dt><dd>{profile.grade}</dd></div>
          {profile.source_type !== undefined && (
            <div><dt className="text-gray-500">Source</dt><dd>{profile.source_type}</dd></div>
          )}
          {profile.client_name !== undefined && (
            <div>
              <dt className="text-gray-500">Client</dt>
              <dd>
                {profile.client ? (
                  <Link to={`/admin/clients/${profile.client}`} className="text-brand-blue hover:underline">{profile.client_name}</Link>
                ) : (
                  profile.client_name || '—'
                )}
              </dd>
            </div>
          )}
          <div><dt className="text-gray-500">Parent name</dt><dd>{profile.parent_name}</dd></div>
          {profile.parent_phone_number !== undefined && (
            <div><dt className="text-gray-500">Parent phone</dt><dd>{profile.parent_phone_number}</dd></div>
          )}
          <div><dt className="text-gray-500">Place</dt><dd>{profile.place}</dd></div>
        </dl>
      </Card>

      {allowEdit && (
        <Modal open={editingProfile} onClose={closeEditProfile} title="Edit student details" maxWidthClass="max-w-2xl">
          <form onSubmit={handleSaveProfile} className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Name</label>
                <input required value={profileForm?.name ?? ''} onChange={(e) => setProfileForm({ ...profileForm, name: e.target.value })} className="input" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Grade</label>
                <select required value={profileForm?.grade ?? ''} onChange={(e) => setProfileForm({ ...profileForm, grade: e.target.value })} className="input">
                  {GRADES.map((g) => <option key={g} value={g}>Std {g}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Source</label>
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
                  <label className="block text-xs text-gray-500 mb-1">Client</label>
                  <select required value={profileForm.client} onChange={(e) => setProfileForm({ ...profileForm, client: e.target.value })} className="input">
                    <option value="">Select client…</option>
                    {clients.map((c) => (
                      <option key={c.id} value={c.id}>{c.company_name}</option>
                    ))}
                  </select>
                </div>
              )}
              <div>
                <label className="block text-xs text-gray-500 mb-1">Parent name</label>
                <input value={profileForm?.parent_name ?? ''} onChange={(e) => setProfileForm({ ...profileForm, parent_name: e.target.value })} className="input" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Parent phone</label>
                <input value={profileForm?.parent_phone_number ?? ''} onChange={(e) => setProfileForm({ ...profileForm, parent_phone_number: e.target.value })} className="input" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Place</label>
                <input value={profileForm?.place ?? ''} onChange={(e) => setProfileForm({ ...profileForm, place: e.target.value })} className="input" />
              </div>
            </div>
            {profileError && <p className="text-red-600 text-xs">{profileError}</p>}
            <div className="flex justify-end gap-3">
              <button type="button" onClick={closeEditProfile} className="text-sm text-gray-500 hover:underline">
                Cancel
              </button>
              <button disabled={savingProfile} type="submit" className="text-sm text-brand-green hover:underline disabled:opacity-60">
                {savingProfile ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      <h2 className="text-lg font-semibold text-navy mb-3">Batch history</h2>
      {downloadReportError && <p className="text-red-600 text-xs mb-3">{downloadReportError}</p>}
      {downloadCertificateError && <p className="text-red-600 text-xs mb-3">{downloadCertificateError}</p>}
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
                  className="text-xs text-brand-blue hover:underline disabled:opacity-60"
                >
                  {downloadingReportId === e.id ? 'Downloading…' : 'Download PDF'}
                </button>
                {e.status === 'completed' && (
                  <button
                    disabled={downloadingCertificateId === e.id}
                    onClick={() => handleDownloadCertificate(e.id)}
                    className="text-xs text-brand-green hover:underline disabled:opacity-60"
                  >
                    {downloadingCertificateId === e.id ? 'Downloading…' : 'Download certificate'}
                  </button>
                )}
              </div>
            </div>
            <p className="text-sm text-gray-500 mb-2">
              Trainer:{' '}
              {allowEdit ? (
                <Link
                  to={`/admin/trainers/${e.trainer}`}
                  state={{ from: `/admin/students/${studentId}`, fromLabel: `Back to ${profile.name}` }}
                  className="text-brand-blue hover:underline"
                >
                  {e.trainer_name}
                </Link>
              ) : (
                e.trainer_name
              )}{' '}
              · {e.classes_completed}/{e.classes_total} classes · started {formatDate(e.start_date)}
              {e.class_days ? ` · ${formatDays(e.class_days)}${e.class_time ? ` at ${formatTime(e.class_time)}` : ''}` : ''}
            </p>

            {allowTransfer && transferId === e.id && (
              <div className="flex flex-col items-start gap-2 mb-2">
                <div className="min-w-[10rem]">
                  <SearchableSelect
                    placeholder="Search trainer…"
                    value={transferTrainer}
                    onChange={setTransferTrainer}
                    options={trainers.filter((t) => t.id !== e.trainer).map((t) => ({ value: t.id, label: t.name }))}
                  />
                </div>
                <div className="space-x-3">
                  <button
                    disabled={!transferTrainer || transferring}
                    onClick={() => handleTransfer(e.id)}
                    className="text-brand-green hover:underline disabled:opacity-60 text-xs"
                  >
                    {transferring ? 'Transferring…' : 'Confirm'}
                  </button>
                  <button onClick={closeTransfer} className="text-gray-500 hover:underline text-xs">
                    Cancel
                  </button>
                </div>
                {transferError && <p className="text-red-600 text-xs">{transferError}</p>}
              </div>
            )}

            <div className="flex items-center gap-3">
              <button onClick={() => toggleHistory(e.id)} className="text-xs text-brand-blue hover:underline">
                {expanded === e.id ? 'Hide class history' : 'View class history'}
              </button>
              {allowTransfer && e.status === 'ongoing' && transferId !== e.id && (
                <button onClick={() => openTransfer(e.id)} className="text-xs text-brand-blue hover:underline">
                  Transfer
                </button>
              )}
            </div>

            {expanded === e.id && (
              <div className="mt-3 border-t border-gray-100 pt-3">
                {loadingSessions === e.id && <p className="text-xs text-gray-400">Loading…</p>}
                {sessionsByEnrollment[e.id] && sessionsByEnrollment[e.id].length === 0 && (
                  <p className="text-xs text-gray-400">No classes taken yet.</p>
                )}
                {sessionsByEnrollment[e.id] && sessionsByEnrollment[e.id].length > 0 && (
                  <table className="w-full text-xs">
                    <thead className="text-gray-500 text-left">
                      <tr>
                        <th className="py-1 pr-4">Date</th>
                        <th className="py-1">Topic covered</th>
                        {allowEdit && <th className="py-1"></th>}
                      </tr>
                    </thead>
                    <tbody>
                      {sessionsByEnrollment[e.id].map((s) => (
                        <tr key={s.id} className="border-t border-gray-50">
                          <td className="py-1 pr-4">{formatDate(s.date)}</td>
                          <td className="py-1 text-gray-500">{s.topic_covered || '—'}</td>
                          {allowEdit && (
                            <td className="py-1 pl-4 text-right whitespace-nowrap">
                              {s.in_closed_cycle ? (
                                <span className="text-gray-400">Locked</span>
                              ) : (
                                <button onClick={() => openDeleteSession(e.id, s.id)} className="text-red-600 hover:underline">
                                  Delete
                                </button>
                              )}
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {allowEdit && e.payment_plan && (
              <div className="mt-3 border-t border-gray-100 pt-3">
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
                        <td className="py-1 text-right whitespace-nowrap">
                          {inst.paid_status === 'cancelled' ? (
                            <span className="text-gray-400">Cancelled</span>
                          ) : inst.paid_status === 'paid' ? (
                            markingPaidId === inst.id ? (
                              <span className="text-gray-400">Undoing…</span>
                            ) : (
                              <span className="text-brand-green">
                                Paid{inst.paid_date ? ` on ${formatDate(inst.paid_date)}` : ''}
                                {' · '}
                                <button onClick={() => handleRevokePaid(inst.id)} className="text-gray-400 hover:text-red-600 hover:underline">
                                  Undo
                                </button>
                              </span>
                            )
                          ) : markingPaidId === inst.id ? (
                            <span className="text-gray-400">Marking…</span>
                          ) : (
                            <button onClick={() => handleMarkPaid(inst.id)} className="text-brand-blue hover:underline">
                              Mark as paid
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {markPaidError && <p className="text-red-600 text-xs mt-2">{markPaidError}</p>}
              </div>
            )}
          </Card>
        ))}
        {profile.enrollments.length === 0 && <p className="text-gray-400 text-sm">No enrollments yet.</p>}
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
