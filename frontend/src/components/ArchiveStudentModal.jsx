import { useEffect, useState } from 'react'
import { Button } from './Button'
import { Modal } from './Modal'
import { useApi } from '../hooks/useApi'

// Ongoing enrollments and active batch enrollments both hard-block archiving
// (both here and server-side, see StudentViewSet.archive) — a student can't
// be archived while still taking classes, whether that's a 1:1 Enrollment or
// a group Batch. Each gets a Withdraw toggle: for 1:1 enrollments, B2C
// students get optional refund amount/note fields (withdrawing already
// auto-cancels any pending installment on that enrollment, refund fields
// just log what was given back), B2B students don't need them since there's
// no payment plan. Batch enrollments always get refund fields regardless of
// sourceType, since batches bill everyone the same way via fee_per_student.
// Unpaid installments are shown too, but only ever informational — see
// StudentViewSet.archive_blockers for why they can't block on their own.
export function ArchiveStudentModal({ open, studentId, studentName, sourceType, onClose, onArchived }) {
  const api = useApi()
  const [blockers, setBlockers] = useState(null)
  const [loadError, setLoadError] = useState('')

  const [refundForms, setRefundForms] = useState({})
  const [busyKey, setBusyKey] = useState('')
  const [rowErrors, setRowErrors] = useState({})

  const [archiving, setArchiving] = useState(false)
  const [archiveError, setArchiveError] = useState('')

  async function refreshBlockers() {
    setBlockers(await api(`/api/students/${studentId}/archive-blockers/`))
  }

  useEffect(() => {
    if (!open) return
    setLoadError('')
    setArchiveError('')
    setRowErrors({})
    setRefundForms({})
    setBlockers(null)
    refreshBlockers().catch((err) => setLoadError(err.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, studentId])

  function setRowError(key, message) {
    setRowErrors((prev) => ({ ...prev, [key]: message }))
  }

  function updateRefundForm(enrollmentId, field, value) {
    setRefundForms((prev) => ({ ...prev, [enrollmentId]: { ...prev[enrollmentId], [field]: value } }))
  }

  function updateBatchRefundForm(batchEnrollmentId, field, value) {
    const key = `batch-${batchEnrollmentId}`
    setRefundForms((prev) => ({ ...prev, [key]: { ...prev[key], [field]: value } }))
  }

  async function handleWithdraw(enrollmentId) {
    const key = `enrollment-${enrollmentId}`
    const form = refundForms[enrollmentId] || {}
    const body = {}
    if (form.refund_amount) body.refund_amount = form.refund_amount
    if (form.refund_note) body.refund_note = form.refund_note

    setBusyKey(key)
    setRowError(key, '')
    try {
      await api(`/api/enrollments/${enrollmentId}/withdraw/`, { method: 'POST', body })
      await refreshBlockers()
    } catch (err) {
      setRowError(key, err.message)
    } finally {
      setBusyKey('')
    }
  }

  async function handleBatchWithdraw(batchEnrollmentId) {
    const key = `batch-${batchEnrollmentId}`
    const form = refundForms[key] || {}
    const body = {}
    if (form.refund_amount) body.refund_amount = form.refund_amount
    if (form.refund_note) body.refund_note = form.refund_note

    setBusyKey(key)
    setRowError(key, '')
    try {
      await api(`/api/batch-enrollments/${batchEnrollmentId}/withdraw/`, { method: 'POST', body })
      await refreshBlockers()
    } catch (err) {
      setRowError(key, err.message)
    } finally {
      setBusyKey('')
    }
  }

  async function handleArchive() {
    setArchiving(true)
    setArchiveError('')
    try {
      await api(`/api/students/${studentId}/archive/`, { method: 'POST' })
      onArchived?.()
      onClose()
    } catch (err) {
      setArchiveError(err.message)
      await refreshBlockers().catch(() => {})
    } finally {
      setArchiving(false)
    }
  }

  const b = blockers || { ongoing_enrollments: [], active_batch_enrollments: [], pending_installments: [] }
  const isBlocked = blockers != null && (b.ongoing_enrollments.length > 0 || b.active_batch_enrollments.length > 0)
  const hasInfo = blockers != null && b.pending_installments.length > 0

  return (
    <Modal open={open} onClose={onClose} title={`Archive ${studentName}`} maxWidthClass="max-w-lg">
      {loadError && <p className="text-error text-sm mb-4">{loadError}</p>}

      {!blockers && !loadError && <p className="text-sm text-text-tertiary">Checking for ongoing enrollments…</p>}

      {blockers && !isBlocked && !hasInfo && (
        <p className="text-sm text-text-secondary">
          {studentName} has no ongoing enrollments or unpaid installments. Safe to archive.
        </p>
      )}

      {blockers && (isBlocked || hasInfo) && (
        <div className="space-y-4">
          {isBlocked && (
            <p className="text-sm text-text-secondary">
              {studentName} still has ongoing enrollments or batches. Withdraw them below before archiving.
            </p>
          )}
          {!isBlocked && hasInfo && (
            <p className="text-sm text-text-secondary">
              {studentName} has no ongoing enrollments or batches. The unpaid installment(s) below don't block
              archiving, but won't be cancelled by it either — resolve them separately if needed.
            </p>
          )}

          {b.ongoing_enrollments.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-navy mb-2">
                Ongoing enrollments ({b.ongoing_enrollments.length})
              </h3>
              <div className="space-y-2">
                {b.ongoing_enrollments.map((e) => {
                  const key = `enrollment-${e.id}`
                  const form = refundForms[e.id] || { refund_amount: '', refund_note: '' }
                  return (
                    <div key={e.id} className="rounded-lg border border-gray-200 p-2.5">
                      <p className="text-sm">
                        {e.course_name} <span className="text-text-secondary">— batch {e.batch_number} · {e.trainer_name}</span>
                      </p>
                      {sourceType === 'B2C' && (
                        <div className="flex items-center gap-2 mt-2">
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            placeholder="Refund amount (₹, optional)"
                            value={form.refund_amount}
                            onChange={(ev) => updateRefundForm(e.id, 'refund_amount', ev.target.value)}
                            className="input text-xs py-1.5"
                          />
                          <input
                            placeholder="Refund note (optional)"
                            value={form.refund_note}
                            onChange={(ev) => updateRefundForm(e.id, 'refund_note', ev.target.value)}
                            className="input text-xs py-1.5"
                          />
                        </div>
                      )}
                      <div className="flex items-center justify-between mt-2">
                        {rowErrors[key] && <p className="text-error text-xs">{rowErrors[key]}</p>}
                        <Button size="sm" disabled={busyKey === key} onClick={() => handleWithdraw(e.id)} className="ml-auto">
                          {busyKey === key ? 'Withdrawing…' : 'Withdraw'}
                        </Button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {b.active_batch_enrollments.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-navy mb-2">
                Active batches ({b.active_batch_enrollments.length})
              </h3>
              <div className="space-y-2">
                {b.active_batch_enrollments.map((be) => {
                  const key = `batch-${be.id}`
                  const form = refundForms[key] || { refund_amount: '', refund_note: '' }
                  return (
                    <div key={be.id} className="rounded-lg border border-gray-200 p-2.5">
                      <p className="text-sm">
                        {be.batch_name} <span className="text-text-secondary">— {be.course_name}</span>
                      </p>
                      <div className="flex items-center gap-2 mt-2">
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder="Refund amount (₹, optional)"
                          value={form.refund_amount}
                          onChange={(ev) => updateBatchRefundForm(be.id, 'refund_amount', ev.target.value)}
                          className="input text-xs py-1.5"
                        />
                        <input
                          placeholder="Refund note (optional)"
                          value={form.refund_note}
                          onChange={(ev) => updateBatchRefundForm(be.id, 'refund_note', ev.target.value)}
                          className="input text-xs py-1.5"
                        />
                      </div>
                      <div className="flex items-center justify-between mt-2">
                        {rowErrors[key] && <p className="text-error text-xs">{rowErrors[key]}</p>}
                        <Button size="sm" disabled={busyKey === key} onClick={() => handleBatchWithdraw(be.id)} className="ml-auto">
                          {busyKey === key ? 'Withdrawing…' : 'Withdraw'}
                        </Button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {b.pending_installments.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-navy mb-2">
                Unpaid installments ({b.pending_installments.length})
              </h3>
              <ul className="space-y-1">
                {b.pending_installments.map((i) => (
                  <li key={i.id} className="text-sm rounded-lg border border-gray-200 p-2.5">
                    {i.course_name} <span className="text-text-secondary">— installment #{i.sequence} · ₹{i.amount}</span>
                    <span className="text-text-tertiary"> ({i.due_at_classes == null ? 'due before class 1' : `due at class ${i.due_at_classes}`})</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}

      {archiveError && <p className="text-error text-sm mt-4">{archiveError}</p>}

      <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-gray-100">
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="button" variant="danger" disabled={!blockers || isBlocked || archiving} onClick={handleArchive}>
          {archiving ? 'Archiving…' : 'Archive student'}
        </Button>
      </div>
    </Modal>
  )
}
