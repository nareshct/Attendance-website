import { useEffect, useState } from 'react'
import { Button } from './Button'
import { Modal } from './Modal'
import { SearchableSelect } from './SearchableSelect'
import { useApi } from '../hooks/useApi'
import { formatDate, formatDateRange } from '../utils/date'
import { formatDays, formatTime } from '../utils/schedule'

const EMPTY_BLOCKERS = {
  ongoing_enrollments: [], ongoing_batches: [], pending_attendance_requests: [],
  pending_payouts: [], pending_batch_payouts: [], active_substitute_assignments: [],
  current_cycle_earnings: [],
}

function removeName(trainerNames, name) {
  const target = name.trim().toLowerCase()
  return (trainerNames || '')
    .split(',')
    .map((n) => n.trim())
    .filter((n) => n && n.toLowerCase() !== target)
    .join(', ')
}

// Warns before archiving a trainer who's still tied to active/unresolved work
// (ongoing batches/enrollments, pending attendance requests, pending payouts) and
// lets the admin resolve each one inline, right here, rather than bouncing between
// several other pages first. Archive stays hard-blocked (both here and server-side,
// see TrainerViewSet.archive) until every category clears.
export function ArchiveTrainerModal({ open, trainerId, trainerName, onClose, onArchived }) {
  const api = useApi()
  const [blockers, setBlockers] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [activeTrainers, setActiveTrainers] = useState([])

  const [transferTargets, setTransferTargets] = useState({})
  const [busyKey, setBusyKey] = useState('')
  const [rowErrors, setRowErrors] = useState({})

  const [archiving, setArchiving] = useState(false)
  const [archiveError, setArchiveError] = useState('')

  async function refreshBlockers() {
    setBlockers(await api(`/api/trainers/${trainerId}/archive-blockers/`))
  }

  useEffect(() => {
    if (!open) return
    setLoadError('')
    setArchiveError('')
    setRowErrors({})
    setTransferTargets({})
    setBlockers(null)
    refreshBlockers().catch((err) => setLoadError(err.message))
    api('/api/trainers/').then(setActiveTrainers).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, trainerId])

  function setRowError(key, message) {
    setRowErrors((prev) => ({ ...prev, [key]: message }))
  }

  async function runRowAction(key, fn) {
    setBusyKey(key)
    setRowError(key, '')
    try {
      await fn()
      await refreshBlockers()
    } catch (err) {
      setRowError(key, err.message)
    } finally {
      setBusyKey('')
    }
  }

  function handleTransfer(enrollmentId) {
    const target = transferTargets[enrollmentId]
    if (!target) {
      setRowError(`enrollment-${enrollmentId}`, 'Select a trainer to transfer to.')
      return
    }
    runRowAction(`enrollment-${enrollmentId}`, () =>
      api(`/api/enrollments/${enrollmentId}/transfer/`, { method: 'POST', body: { trainer: Number(target) } }),
    )
  }

  function handleRemoveFromBatch(batch) {
    runRowAction(`batch-${batch.id}`, () =>
      api(`/api/batches/${batch.id}/`, { method: 'PATCH', body: { trainer_names: removeName(batch.trainer_names, trainerName) } }),
    )
  }

  function handleReviewRequest(requestId, action) {
    runRowAction(`request-${requestId}`, () => api(`/api/attendance-requests/${requestId}/${action}/`, { method: 'POST' }))
  }

  function handlePayout(payoutId, action) {
    runRowAction(`payout-${payoutId}`, () => api(`/api/payouts/${payoutId}/${action}/`, { method: 'POST' }))
  }

  function handleBatchPayout(payoutId, action) {
    runRowAction(`batch-payout-${payoutId}`, () => api(`/api/batch-payouts/${payoutId}/${action}/`, { method: 'POST' }))
  }

  function handleCancelSubstitute(assignmentId) {
    runRowAction(`substitute-${assignmentId}`, () => api(`/api/substitute-assignments/${assignmentId}/`, { method: 'DELETE' }))
  }

  function handleSettleCurrentCycle() {
    runRowAction('current-cycle', () => api(`/api/trainers/${trainerId}/settle-current-cycle/`, { method: 'POST' }))
  }

  async function handleArchive() {
    setArchiving(true)
    setArchiveError('')
    try {
      await api(`/api/trainers/${trainerId}/archive/`, { method: 'POST' })
      onArchived?.()
      onClose()
    } catch (err) {
      setArchiveError(err.message)
      await refreshBlockers().catch(() => {})
    } finally {
      setArchiving(false)
    }
  }

  const trainerOptions = activeTrainers
    .filter((t) => t.status === 'active' && t.id !== trainerId)
    .map((t) => ({ value: t.id, label: t.name }))

  const b = blockers || EMPTY_BLOCKERS
  const isClear = blockers != null && Object.values(b).every((list) => list.length === 0)

  return (
    <Modal open={open} onClose={onClose} title={`Archive ${trainerName}`} maxWidthClass="max-w-3xl">
      {loadError && <p className="text-error text-sm mb-4">{loadError}</p>}

      {!blockers && !loadError && <p className="text-sm text-text-tertiary">Checking for ongoing or pending work…</p>}

      {blockers && isClear && (
        <p className="text-sm text-text-secondary mb-4">
          {trainerName} has no ongoing batches/enrollments, pending attendance requests, or pending payouts. Safe to archive.
        </p>
      )}

      {blockers && !isClear && (
        <div className="space-y-6">
          <p className="text-sm text-text-secondary">
            {trainerName} still has ongoing or unresolved work. Resolve everything below before archiving.
          </p>

          {b.ongoing_enrollments.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-navy mb-2">Ongoing 1:1 enrollments ({b.ongoing_enrollments.length})</h3>
              <div className="space-y-2">
                {b.ongoing_enrollments.map((e) => {
                  const key = `enrollment-${e.id}`
                  return (
                    <div key={e.id} className="rounded-lg border border-gray-200 p-3">
                      <p className="text-sm font-medium text-navy">{e.student_name} <span className="text-text-secondary font-normal">— {e.course_name}</span></p>
                      <p className="text-xs text-text-tertiary mb-2">{formatDays(e.class_days)}{e.class_time && ` · ${formatTime(e.class_time)}`}</p>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 max-w-xs">
                          <SearchableSelect
                            placeholder="Transfer to…"
                            options={trainerOptions}
                            value={transferTargets[e.id] || ''}
                            onChange={(v) => setTransferTargets((prev) => ({ ...prev, [e.id]: v }))}
                          />
                        </div>
                        <Button size="sm" disabled={busyKey === key} onClick={() => handleTransfer(e.id)}>
                          {busyKey === key ? 'Transferring…' : 'Transfer'}
                        </Button>
                      </div>
                      {rowErrors[key] && <p className="text-error text-xs mt-1">{rowErrors[key]}</p>}
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {b.ongoing_batches.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-navy mb-2">Ongoing batches ({b.ongoing_batches.length})</h3>
              <div className="space-y-2">
                {b.ongoing_batches.map((batch) => {
                  const key = `batch-${batch.id}`
                  return (
                    <div key={batch.id} className="flex items-center justify-between rounded-lg border border-gray-200 p-3">
                      <div>
                        <p className="text-sm font-medium text-navy">{batch.name}</p>
                        <p className="text-xs text-text-tertiary">{batch.course_name}</p>
                        {rowErrors[key] && <p className="text-error text-xs mt-1">{rowErrors[key]}</p>}
                      </div>
                      <Button size="sm" variant="secondary" disabled={busyKey === key} onClick={() => handleRemoveFromBatch(batch)}>
                        {busyKey === key ? 'Removing…' : `Remove ${trainerName} from batch`}
                      </Button>
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {b.pending_attendance_requests.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-navy mb-2">Pending attendance requests ({b.pending_attendance_requests.length})</h3>
              <div className="space-y-2">
                {b.pending_attendance_requests.map((r) => {
                  const key = `request-${r.id}`
                  return (
                    <div key={r.id} className="flex items-center justify-between rounded-lg border border-gray-200 p-3 gap-3">
                      <div>
                        <p className="text-sm font-medium text-navy">{formatDate(r.date)} <span className="text-text-secondary font-normal">— {r.student_name} · {r.course_name}</span></p>
                        {r.topic_covered && <p className="text-xs text-text-tertiary">{r.topic_covered}</p>}
                        {rowErrors[key] && <p className="text-error text-xs mt-1">{rowErrors[key]}</p>}
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <button disabled={busyKey === key} onClick={() => handleReviewRequest(r.id, 'approve')} className="text-xs font-medium text-success hover:underline disabled:opacity-60 focus-ring">
                          Approve
                        </button>
                        <button disabled={busyKey === key} onClick={() => handleReviewRequest(r.id, 'deny')} className="text-xs font-medium text-error hover:underline disabled:opacity-60 focus-ring">
                          Deny
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {b.pending_payouts.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-navy mb-2">Pending cycle payouts ({b.pending_payouts.length})</h3>
              <div className="space-y-2">
                {b.pending_payouts.map((p) => {
                  const key = `payout-${p.id}`
                  return (
                    <div key={p.id} className="flex items-center justify-between rounded-lg border border-gray-200 p-3 gap-3">
                      <div>
                        <p className="text-sm font-medium text-navy">{formatDateRange(p.cycle_start, p.cycle_end)}</p>
                        <p className="text-xs text-text-tertiary">₹{p.total_amount}</p>
                        {rowErrors[key] && <p className="text-error text-xs mt-1">{rowErrors[key]}</p>}
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <button disabled={busyKey === key} onClick={() => handlePayout(p.id, 'mark_paid')} className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring">
                          Mark paid
                        </button>
                        <button disabled={busyKey === key} onClick={() => handlePayout(p.id, 'cancel')} className="text-xs font-medium text-error hover:underline disabled:opacity-60 focus-ring">
                          Cancel
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {b.pending_batch_payouts.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-navy mb-2">Pending batch payouts ({b.pending_batch_payouts.length})</h3>
              <div className="space-y-2">
                {b.pending_batch_payouts.map((p) => {
                  const key = `batch-payout-${p.id}`
                  return (
                    <div key={p.id} className="flex items-center justify-between rounded-lg border border-gray-200 p-3 gap-3">
                      <div>
                        <p className="text-sm font-medium text-navy">{p.batch_name}</p>
                        <p className="text-xs text-text-tertiary">₹{p.amount}</p>
                        {rowErrors[key] && <p className="text-error text-xs mt-1">{rowErrors[key]}</p>}
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <button disabled={busyKey === key} onClick={() => handleBatchPayout(p.id, 'mark_paid')} className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring">
                          Mark paid
                        </button>
                        <button disabled={busyKey === key} onClick={() => handleBatchPayout(p.id, 'cancel')} className="text-xs font-medium text-error hover:underline disabled:opacity-60 focus-ring">
                          Cancel
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {b.active_substitute_assignments.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-navy mb-2">Active/upcoming substitute coverage ({b.active_substitute_assignments.length})</h3>
              <div className="space-y-2">
                {b.active_substitute_assignments.map((a) => {
                  const key = `substitute-${a.id}`
                  return (
                    <div key={a.id} className="flex items-center justify-between rounded-lg border border-gray-200 p-3 gap-3">
                      <div>
                        <p className="text-sm font-medium text-navy">{a.student_name} <span className="text-text-secondary font-normal">— {a.course_name}</span></p>
                        <p className="text-xs text-text-tertiary">Covering {formatDate(a.start_date)} – {formatDate(a.end_date)}</p>
                        {rowErrors[key] && <p className="text-error text-xs mt-1">{rowErrors[key]}</p>}
                      </div>
                      <Button size="sm" variant="secondary" disabled={busyKey === key} onClick={() => handleCancelSubstitute(a.id)}>
                        {busyKey === key ? 'Cancelling…' : 'Cancel coverage'}
                      </Button>
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {b.current_cycle_earnings.length > 0 && (() => {
            const c = b.current_cycle_earnings[0]
            const key = 'current-cycle'
            return (
              <section>
                <h3 className="text-sm font-semibold text-navy mb-2">Current cycle earnings (not yet paid out)</h3>
                <div className="flex items-center justify-between rounded-lg border border-gray-200 p-3 gap-3">
                  <div>
                    <p className="text-sm font-medium text-navy">{formatDateRange(c.cycle_start, c.cycle_end)} <span className="text-text-secondary font-normal">— still open</span></p>
                    <p className="text-xs text-text-tertiary">
                      ₹{c.total_amount} for {c.total_classes} class{c.total_classes === 1 ? '' : 'es'}
                      {c.carried_forward_count > 0 && ` (incl. ₹${c.carried_forward_amount} carried forward from ${c.carried_forward_count} late-approved class${c.carried_forward_count === 1 ? '' : 'es'})`}
                    </p>
                    {rowErrors[key] && <p className="text-error text-xs mt-1">{rowErrors[key]}</p>}
                  </div>
                  <Button size="sm" variant="secondary" disabled={busyKey === key} onClick={handleSettleCurrentCycle}>
                    {busyKey === key ? 'Settling…' : 'Settle now'}
                  </Button>
                </div>
              </section>
            )
          })()}
        </div>
      )}

      {archiveError && <p className="text-error text-sm mt-4">{archiveError}</p>}

      <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-gray-100">
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="button" variant="danger" disabled={!isClear || archiving} onClick={handleArchive}>
          {archiving ? 'Archiving…' : 'Archive trainer'}
        </Button>
      </div>
    </Modal>
  )
}
