import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from './Badge'
import { Button } from './Button'
import { Modal } from './Modal'
import { useApi } from '../hooks/useApi'
import { formatDateRange } from '../utils/date'

const EMPTY_BLOCKERS = { active_students: [], pending_invoices: [], current_cycle_unbilled: 0 }

// Warns before archiving a client who still has active students, pending
// invoices, or unbilled current-cycle classes, and lets the admin resolve
// each one inline. Archive stays hard-blocked (both here and server-side,
// see ClientViewSet.archive) until every category clears — mirrors
// ArchiveTrainerModal.
export function ArchiveClientModal({ open, clientId, clientName, onClose, onArchived }) {
  const api = useApi()
  const [blockers, setBlockers] = useState(null)
  const [loadError, setLoadError] = useState('')

  const [busyKey, setBusyKey] = useState('')
  const [rowErrors, setRowErrors] = useState({})

  const [archiving, setArchiving] = useState(false)
  const [archiveError, setArchiveError] = useState('')

  async function refreshBlockers() {
    setBlockers(await api(`/api/clients/${clientId}/archive-blockers/`))
  }

  useEffect(() => {
    if (!open) return
    setLoadError('')
    setArchiveError('')
    setRowErrors({})
    setBlockers(null)
    refreshBlockers().catch((err) => setLoadError(err.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, clientId])

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

  function handleMarkReceived(invoiceId) {
    runRowAction(`invoice-${invoiceId}`, () => api(`/api/client-invoices/${invoiceId}/mark_received/`, { method: 'POST' }))
  }

  function handleWithdraw(enrollmentId) {
    runRowAction(`enrollment-${enrollmentId}`, () => api(`/api/enrollments/${enrollmentId}/withdraw/`, { method: 'POST' }))
  }

  function handleArchiveStudent(studentId) {
    runRowAction(`student-${studentId}`, () => api(`/api/students/${studentId}/archive/`, { method: 'POST' }))
  }

  function studentError(s) {
    return rowErrors[`student-${s.id}`] || s.enrollments.map((e) => rowErrors[`enrollment-${e.id}`]).find(Boolean)
  }

  async function handleArchive() {
    setArchiving(true)
    setArchiveError('')
    try {
      await api(`/api/clients/${clientId}/archive/`, { method: 'POST' })
      onArchived?.()
      onClose()
    } catch (err) {
      setArchiveError(err.message)
      await refreshBlockers().catch(() => {})
    } finally {
      setArchiving(false)
    }
  }

  const b = blockers || EMPTY_BLOCKERS
  const isClear = blockers != null && b.active_students.length === 0 && b.pending_invoices.length === 0 && Number(b.current_cycle_unbilled) === 0

  return (
    <Modal open={open} onClose={onClose} title={`Archive ${clientName}`} maxWidthClass="max-w-2xl">
      {loadError && <p className="text-error text-sm mb-4">{loadError}</p>}

      {!blockers && !loadError && <p className="text-sm text-text-tertiary">Checking for active students or unpaid invoices…</p>}

      {blockers && isClear && (
        <p className="text-sm text-text-secondary mb-4">
          {clientName} has no active students, pending invoices, or unbilled current-cycle classes. Safe to archive.
        </p>
      )}

      {blockers && !isClear && (
        <div className="space-y-6">
          <p className="text-sm text-text-secondary">
            {clientName} still has active students or unresolved billing. Resolve everything below before archiving.
          </p>

          {b.active_students.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-navy mb-2">Active students ({b.active_students.length})</h3>
              <div className="space-y-2">
                {b.active_students.map((s) => {
                  const hasOngoing = s.enrollments.some((e) => e.status === 'ongoing')
                  const archiveKey = `student-${s.id}`
                  const error = studentError(s)
                  return (
                    <div key={s.id} className="rounded-lg border border-gray-200 p-3">
                      <div className="flex items-center justify-between gap-3 mb-2">
                        <Link to={`/admin/students/${s.id}`} className="text-sm font-medium text-primary hover:underline focus-ring">
                          {s.name}
                        </Link>
                        {!hasOngoing && (
                          <Button size="sm" disabled={busyKey === archiveKey} onClick={() => handleArchiveStudent(s.id)}>
                            {busyKey === archiveKey ? 'Archiving…' : 'Archive student'}
                          </Button>
                        )}
                      </div>
                      {s.enrollments.length > 0 ? (
                        <ul className="space-y-1.5">
                          {s.enrollments.map((e) => {
                            const withdrawKey = `enrollment-${e.id}`
                            return (
                              <li key={e.id} className="flex items-center justify-between gap-3">
                                <span className="text-xs text-text-secondary">
                                  {e.course_name} — batch {e.batch_number} · {e.classes_completed}/{e.classes_total}
                                </span>
                                <div className="flex items-center gap-2 shrink-0">
                                  <Badge status={e.status} />
                                  {e.status === 'ongoing' && (
                                    <button
                                      disabled={busyKey === withdrawKey}
                                      onClick={() => handleWithdraw(e.id)}
                                      className="text-xs font-medium text-error hover:underline disabled:opacity-60 focus-ring"
                                    >
                                      {busyKey === withdrawKey ? 'Withdrawing…' : 'Withdraw'}
                                    </button>
                                  )}
                                </div>
                              </li>
                            )
                          })}
                        </ul>
                      ) : (
                        <p className="text-xs text-text-tertiary">No enrollments.</p>
                      )}
                      {error && <p className="text-error text-xs mt-2">{error}</p>}
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {b.pending_invoices.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-navy mb-2">Pending invoices ({b.pending_invoices.length})</h3>
              <div className="space-y-2">
                {b.pending_invoices.map((inv) => {
                  const key = `invoice-${inv.id}`
                  return (
                    <div key={inv.id} className="flex items-center justify-between rounded-lg border border-gray-200 p-3 gap-3">
                      <div>
                        <p className="text-sm font-medium text-navy">{formatDateRange(inv.cycle_start, inv.cycle_end)}</p>
                        <p className="text-xs text-text-tertiary">₹{inv.amount}</p>
                        {rowErrors[key] && <p className="text-error text-xs mt-1">{rowErrors[key]}</p>}
                      </div>
                      <Button size="sm" disabled={busyKey === key} onClick={() => handleMarkReceived(inv.id)}>
                        {busyKey === key ? 'Marking…' : 'Mark received'}
                      </Button>
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {Number(b.current_cycle_unbilled) > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-navy mb-2">Current cycle (not yet invoiced)</h3>
              <div className="rounded-lg border border-gray-200 p-3">
                <p className="text-sm font-medium text-navy">₹{b.current_cycle_unbilled} billed so far this cycle</p>
                <p className="text-xs text-text-tertiary mt-1">
                  This becomes an invoice once the current billing cycle closes — nothing to do here but wait.
                </p>
              </div>
            </section>
          )}
        </div>
      )}

      {archiveError && <p className="text-error text-sm mt-4">{archiveError}</p>}

      <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-gray-100">
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="button" variant="danger" disabled={!isClear || archiving} onClick={handleArchive}>
          {archiving ? 'Archiving…' : 'Archive client'}
        </Button>
      </div>
    </Modal>
  )
}
