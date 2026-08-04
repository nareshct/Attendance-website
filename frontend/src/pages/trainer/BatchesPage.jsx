import { useCallback, useEffect, useState } from 'react'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { Modal } from '../../components/Modal'
import { useAuth } from '../../hooks/useAuth'
import { useApi } from '../../hooks/useApi'
import { formatDate } from '../../utils/date'
import { formatDays, formatTime } from '../../utils/schedule'

const EMPTY_SESSION_FORM = { date: '', topic_covered: '', recording_link: '' }

export default function TrainerBatchesPage() {
  const api = useApi()
  const { auth } = useAuth()
  const [batches, setBatches] = useState([])
  const [sessionsByBatch, setSessionsByBatch] = useState({})
  const [payoutsByBatch, setPayoutsByBatch] = useState({})
  const [error, setError] = useState('')

  const [logTarget, setLogTarget] = useState(null)
  const [sessionForm, setSessionForm] = useState(EMPTY_SESSION_FORM)
  const [logError, setLogError] = useState('')
  const [logging, setLogging] = useState(false)

  const loadBatches = useCallback(() => {
    return api('/api/my-batches/').then(setBatches)
  }, [api])

  useEffect(() => {
    loadBatches().catch((err) => setError(err.message))
  }, [loadBatches])

  useEffect(() => {
    batches.forEach((b) => {
      api(`/api/batch-sessions/?batch=${b.id}`).then((s) => setSessionsByBatch((prev) => ({ ...prev, [b.id]: s }))).catch(() => {})
      api(`/api/batch-payouts/?batch=${b.id}`).then((p) => setPayoutsByBatch((prev) => ({ ...prev, [b.id]: p }))).catch(() => {})
    })
  }, [api, batches])

  function openLogSession(batch) {
    setLogTarget(batch)
    setSessionForm(EMPTY_SESSION_FORM)
    setLogError('')
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
      const updated = await api(`/api/batch-sessions/?batch=${logTarget.id}`)
      setSessionsByBatch((prev) => ({ ...prev, [logTarget.id]: updated }))
      setLogTarget(null)
    } catch (err) {
      setLogError(err.message)
    } finally {
      setLogging(false)
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
                <ul className="text-xs text-gray-600 space-y-1 max-h-32 overflow-y-auto">
                  {(sessionsByBatch[b.id] || []).map((s) => (
                    <li key={s.id}>
                      {formatDate(s.date)}{s.topic_covered && ` — ${s.topic_covered}`}
                      {s.recording_link && (
                        <>
                          {' · '}
                          <a href={s.recording_link} target="_blank" rel="noreferrer" className="text-primary hover:underline">Recording</a>
                        </>
                      )}
                    </li>
                  ))}
                  {(sessionsByBatch[b.id] || []).length === 0 && <li className="text-text-tertiary">No sessions logged yet.</li>}
                </ul>
              </div>
              <div>
                <p className="text-xs text-text-secondary mb-1">Your payouts on this batch</p>
                <ul className="text-xs text-gray-600 space-y-1">
                  {(payoutsByBatch[b.id] || []).map((p) => (
                    <li key={p.id} className="flex items-center justify-between">
                      <span className="tabular-nums">₹{p.amount}</span>
                      <Badge status={p.paid ? 'paid' : 'pending'} />
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
    </div>
  )
}
