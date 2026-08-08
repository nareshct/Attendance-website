import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { Modal } from '../../components/Modal'
import { useAuth } from '../../hooks/useAuth'
import { useApi } from '../../hooks/useApi'
import { formatDate } from '../../utils/date'
import { formatDays, formatTime } from '../../utils/schedule'

const EMPTY_SESSION_FORM = { date: '', topic_covered: '', recording_link: '' }

export default function TrainerBatchesPage() {
  const api = useApi()
  const navigate = useNavigate()
  const { auth } = useAuth()
  const [batches, setBatches] = useState([])
  const [sessionsByBatch, setSessionsByBatch] = useState({})
  const [payoutsByBatch, setPayoutsByBatch] = useState({})
  const [error, setError] = useState('')

  const [logTarget, setLogTarget] = useState(null)
  const [sessionForm, setSessionForm] = useState(EMPTY_SESSION_FORM)
  const [logError, setLogError] = useState('')
  const [logging, setLogging] = useState(false)

  const [editTarget, setEditTarget] = useState(null)
  const [editForm, setEditForm] = useState(EMPTY_SESSION_FORM)
  const [editError, setEditError] = useState('')
  const [saving, setSaving] = useState(false)

  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteError, setDeleteError] = useState('')
  const [deleting, setDeleting] = useState(false)

  const loadBatches = useCallback(() => {
    // The nav link to this page is already hidden for a trainer on zero batches
    // (see TrainerShell in App.jsx) — this covers reaching the URL directly.
    return api('/api/my-batches/').then((data) => {
      if (data.length === 0) {
        navigate('/trainer', { replace: true })
        return
      }
      setBatches(data)
    })
  }, [api, navigate])

  useEffect(() => {
    loadBatches().catch((err) => setError(err.message))
  }, [loadBatches])

  useEffect(() => {
    batches.forEach((b) => {
      api(`/api/batch-sessions/?batch=${b.id}`).then((s) => setSessionsByBatch((prev) => ({ ...prev, [b.id]: s }))).catch((err) => setError(err.message))
      api(`/api/batch-payouts/?batch=${b.id}`).then((p) => setPayoutsByBatch((prev) => ({ ...prev, [b.id]: p }))).catch((err) => setError(err.message))
    })
  }, [api, batches])

  function openLogSession(batch) {
    setLogTarget(batch)
    setSessionForm(EMPTY_SESSION_FORM)
    setLogError('')
  }

  async function reloadSessions(batchId) {
    const updated = await api(`/api/batch-sessions/?batch=${batchId}`)
    setSessionsByBatch((prev) => ({ ...prev, [batchId]: updated }))
  }

  async function handleLogSession(e) {
    e.preventDefault()
    setLogging(true)
    setLogError('')
    try {
      await api('/api/batch-sessions/', {
        method: 'POST',
        body: { batch: logTarget.id, conducted_by_name: auth.name, ...sessionForm },
      })
      await reloadSessions(logTarget.id)
      setLogTarget(null)
    } catch (err) {
      setLogError(err.message)
    } finally {
      setLogging(false)
    }
  }

  function openEditSession(batch, session) {
    setEditTarget({ batch, session })
    setEditForm({
      date: session.date,
      topic_covered: session.topic_covered || '',
      recording_link: session.recording_link || '',
    })
    setEditError('')
  }

  async function handleSaveEdit(e) {
    e.preventDefault()
    setSaving(true)
    setEditError('')
    try {
      await api(`/api/batch-sessions/${editTarget.session.id}/`, { method: 'PATCH', body: editForm })
      await reloadSessions(editTarget.batch.id)
      setEditTarget(null)
    } catch (err) {
      setEditError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDeleteSession() {
    setDeleting(true)
    setDeleteError('')
    try {
      await api(`/api/batch-sessions/${deleteTarget.session.id}/`, { method: 'DELETE' })
      await reloadSessions(deleteTarget.batch.id)
      setDeleteTarget(null)
    } catch (err) {
      setDeleteError(err.message)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-6">My Batches</h1>
      <p className="text-sm text-text-secondary mb-6">
        Group classes you're listed as a trainer on — log a session after each class and check your payout status.
      </p>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <div className="space-y-4">
        {batches.map((b) => (
          <Card key={b.id}>
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="font-medium text-navy">{b.name}</p>
                <p className="text-xs text-text-tertiary">
                  {b.course_name} · {formatDays(b.class_days)}{b.class_time && ` · ${formatTime(b.class_time)}`}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Badge status={b.status} />
                <Button variant="primary" size="sm" onClick={() => openLogSession(b)}>
                  + Log session
                </Button>
              </div>
            </div>

            {b.meet_link && (
              <a href={b.meet_link} target="_blank" rel="noreferrer" className="text-xs font-medium text-primary hover:underline">
                Open Meet link
              </a>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-3 pt-3 border-t border-gray-100">
              <div>
                <p className="text-xs text-text-secondary mb-1">Sessions logged ({(sessionsByBatch[b.id] || []).length})</p>
                <div className="space-y-1.5 max-h-40 overflow-y-auto pr-0.5">
                  {(sessionsByBatch[b.id] || []).map((s) => (
                    <div key={s.id} className="flex items-center justify-between gap-2 rounded-md border border-gray-100 bg-surface-sunken px-2.5 py-1.5">
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-navy truncate">
                          {formatDate(s.date)}{s.topic_covered && ` — ${s.topic_covered}`}
                        </p>
                        {s.recording_link && (
                          <a href={s.recording_link} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">
                            Recording
                          </a>
                        )}
                      </div>
                      {s.can_edit && (
                        <div className="flex items-center gap-1 shrink-0">
                          <button type="button" onClick={() => openEditSession(b, s)} className="text-xs font-medium text-primary hover:underline">
                            Edit
                          </button>
                          <span className="text-gray-300">·</span>
                          <button type="button" onClick={() => { setDeleteTarget({ batch: b, session: s }); setDeleteError('') }} className="text-xs font-medium text-error hover:underline">
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                  {(sessionsByBatch[b.id] || []).length === 0 && <p className="text-xs text-text-tertiary">No sessions logged yet.</p>}
                </div>
              </div>
              <div>
                <p className="text-xs text-text-secondary mb-1">Your payouts on this batch</p>
                <ul className="text-xs text-gray-600 space-y-1">
                  {(payoutsByBatch[b.id] || []).map((p) => (
                    <li key={p.id} className="flex items-center justify-between">
                      <span className="tabular-nums">₹{p.amount}</span>
                      <Badge status={p.paid_status} />
                    </li>
                  ))}
                  {(payoutsByBatch[b.id] || []).length === 0 && <li className="text-text-tertiary">No payout recorded yet.</li>}
                </ul>
              </div>
            </div>
          </Card>
        ))}
        {batches.length === 0 && !error && <p className="text-text-tertiary text-sm">You're not listed on any batches yet.</p>}
      </div>

      <Modal open={Boolean(logTarget)} onClose={() => setLogTarget(null)} title="Log a session">
        {logTarget && (
          <form onSubmit={handleLogSession} className="space-y-3">
            <p className="text-sm text-text-secondary">{logTarget.name}</p>
            <input required type="date" value={sessionForm.date} onChange={(e) => setSessionForm({ ...sessionForm, date: e.target.value })} className="input" />
            <input placeholder="Topic covered (optional)" value={sessionForm.topic_covered} onChange={(e) => setSessionForm({ ...sessionForm, topic_covered: e.target.value })} className="input" />
            <input placeholder="Recording link (Google Drive, optional)" value={sessionForm.recording_link} onChange={(e) => setSessionForm({ ...sessionForm, recording_link: e.target.value })} className="input" />
            {logError && <p className="text-error text-xs">{logError}</p>}
            <div className="flex justify-end gap-3">
              <Button type="button" variant="ghost" onClick={() => setLogTarget(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="success" disabled={logging}>
                {logging ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </form>
        )}
      </Modal>

      <Modal open={Boolean(editTarget)} onClose={() => setEditTarget(null)} title="Edit session">
        {editTarget && (
          <form onSubmit={handleSaveEdit} className="space-y-3">
            <p className="text-sm text-text-secondary">{editTarget.batch.name}</p>
            <input required type="date" value={editForm.date} onChange={(e) => setEditForm({ ...editForm, date: e.target.value })} className="input" />
            <input placeholder="Topic covered (optional)" value={editForm.topic_covered} onChange={(e) => setEditForm({ ...editForm, topic_covered: e.target.value })} className="input" />
            <input placeholder="Recording link (Google Drive, optional)" value={editForm.recording_link} onChange={(e) => setEditForm({ ...editForm, recording_link: e.target.value })} className="input" />
            {editError && <p className="text-error text-xs">{editError}</p>}
            <div className="flex justify-end gap-3">
              <Button type="button" variant="ghost" onClick={() => setEditTarget(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="success" disabled={saving}>
                {saving ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </form>
        )}
      </Modal>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDeleteSession}
        title="Delete session"
        message={`Delete the session logged for ${deleteTarget ? formatDate(deleteTarget.session.date) : ''}? This cannot be undone.`}
        confirmLabel="Delete"
        busyLabel="Deleting…"
        danger
        busy={deleting}
        error={deleteError}
      />
    </div>
  )
}
