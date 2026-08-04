import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiUpload, downloadFile } from '../../api/client'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { Modal } from '../../components/Modal'
import { SearchableSelect } from '../../components/SearchableSelect'
import { useAuth } from '../../hooks/useAuth'
import { useApi } from '../../hooks/useApi'
import { usePaginatedList } from '../../hooks/usePaginatedList'
import { formatDate } from '../../utils/date'
import { DAY_OPTIONS, formatDays, formatTime } from '../../utils/schedule'

const PAYMENT_TYPE_OPTIONS = [
  { value: 'one_time', label: 'One-time payment' },
  { value: 'two_installments', label: 'Two installments' },
  { value: 'three_installments', label: 'Three installments' },
  { value: 'four_installments', label: 'Four installments' },
]

export default function BatchDetailPage() {
  const { id } = useParams()
  const api = useApi()
  const navigate = useNavigate()
  const { auth } = useAuth()
  const [batch, setBatch] = useState(null)
  const [revenue, setRevenue] = useState(null)
  const [sessions, setSessions] = useState([])
  const [payouts, setPayouts] = useState([])
  const [students, setStudents] = useState([])
  const [courses, setCourses] = useState([])
  const [trainers, setTrainers] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const [showAddPayout, setShowAddPayout] = useState(false)
  const [payoutForm, setPayoutForm] = useState({ recipient_name: '', amount: '' })
  const [addPayoutError, setAddPayoutError] = useState('')
  const [addingPayout, setAddingPayout] = useState(false)

  const [editingBatch, setEditingBatch] = useState(false)
  const [batchForm, setBatchForm] = useState(null)
  const [batchFormError, setBatchFormError] = useState('')
  const [savingBatch, setSavingBatch] = useState(false)
  const [trainerNameInput, setTrainerNameInput] = useState('')

  const EMPTY_GUEST_FORM = { guest_name: '', guest_phone_number: '', guest_email: '', guest_occupation: '', guest_source: '' }
  const [showAddStudent, setShowAddStudent] = useState(false)
  const [addMode, setAddMode] = useState('existing')
  const [addStudentId, setAddStudentId] = useState('')
  const [guestForm, setGuestForm] = useState(EMPTY_GUEST_FORM)
  const [addStudentError, setAddStudentError] = useState('')
  const [addingStudent, setAddingStudent] = useState(false)

  const [showAddSession, setShowAddSession] = useState(false)
  const [sessionForm, setSessionForm] = useState({ date: '', conducted_by_name: '', topic_covered: '', recording_link: '' })
  const [addSessionError, setAddSessionError] = useState('')
  const [addingSession, setAddingSession] = useState(false)

  const [showImport, setShowImport] = useState(false)
  const [importFile, setImportFile] = useState(null)
  const [importResult, setImportResult] = useState(null)
  const [importError, setImportError] = useState('')
  const [importing, setImporting] = useState(false)
  const [downloadingTemplate, setDownloadingTemplate] = useState(false)
  const [exporting, setExporting] = useState(false)

  const [deletingBatch, setDeletingBatch] = useState(false)

  const [withdrawTarget, setWithdrawTarget] = useState(null)
  const [refundForm, setRefundForm] = useState({ refund_amount: '', refund_note: '' })
  const [withdrawError, setWithdrawError] = useState('')

  const [editingInstallmentId, setEditingInstallmentId] = useState(null)
  const [editingInstallmentAmount, setEditingInstallmentAmount] = useState('')
  const [installmentEditError, setInstallmentEditError] = useState('')

  const loadBatch = useCallback(() => {
    return api(`/api/batches/${id}/`).then(setBatch)
  }, [api, id])
  const loadRevenue = useCallback(() => {
    return api(`/api/batches/${id}/revenue/`).then(setRevenue)
  }, [api, id])
  const loadSessions = useCallback(() => {
    return api(`/api/batch-sessions/?batch=${id}`).then(setSessions)
  }, [api, id])
  const loadPayouts = useCallback(() => {
    return api(`/api/batch-payouts/?batch=${id}`).then(setPayouts)
  }, [api, id])

  const [studentSearch, setStudentSearch] = useState('')
  const [debouncedStudentSearch, setDebouncedStudentSearch] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedStudentSearch(studentSearch), 300)
    return () => clearTimeout(timer)
  }, [studentSearch])

  const enrollmentsPath = debouncedStudentSearch
    ? `/api/batch-enrollments/?batch=${id}&search=${encodeURIComponent(debouncedStudentSearch)}`
    : `/api/batch-enrollments/?batch=${id}`
  const {
    items: enrollments, count: enrollmentCount, hasMore: enrollmentsHasMore, loading: enrollmentsLoading,
    loadingMore: enrollmentsLoadingMore, reload: reloadEnrollments, loadMore: loadMoreEnrollments,
    loadLess: loadLessEnrollments, page: enrollmentsPage,
  } = usePaginatedList(enrollmentsPath)

  useEffect(() => {
    reloadEnrollments().catch((err) => setError(err.message))
  }, [reloadEnrollments])

  useEffect(() => {
    loadBatch().catch((err) => setError(err.message))
    loadRevenue().catch(() => {})
    loadSessions().catch(() => {})
    loadPayouts().catch(() => {})
    api('/api/students/').then((s) => setStudents(s.filter((x) => x.status === 'active'))).catch(() => {})
    api('/api/courses/').then(setCourses).catch(() => {})
    // Only used as autocomplete suggestions below — a batch trainer isn't required to be
    // a registered trainer, so this list doesn't restrict what can be typed/added.
    api('/api/trainers/').then((t) => setTrainers(t.filter((x) => x.status === 'active'))).catch(() => {})
  }, [api, id, loadBatch, loadRevenue, loadSessions, loadPayouts])

  function openEditBatch() {
    setBatchForm({
      name: batch.name,
      course: String(batch.course),
      description: batch.description || '',
      total_classes: batch.total_classes,
      fee_per_student: batch.fee_per_student,
      payment_type: batch.payment_type,
      status: batch.status,
      accepting_enrollments: batch.accepting_enrollments,
      start_date: batch.start_date,
      class_time: (batch.class_time || '').slice(0, 5),
      class_days: (batch.class_days || '').split(',').filter(Boolean),
      meet_link: batch.meet_link || '',
      trainerNames: (batch.trainer_names || '').split(',').map((n) => n.trim()).filter(Boolean),
    })
    setBatchFormError('')
    setEditingBatch(true)
  }

  function closeEditBatch() {
    setEditingBatch(false)
    setBatchForm(null)
    setBatchFormError('')
    setTrainerNameInput('')
  }

  function toggleFormDay(code) {
    setBatchForm((f) => ({
      ...f,
      class_days: f.class_days.includes(code) ? f.class_days.filter((d) => d !== code) : [...f.class_days, code],
    }))
  }

  function addFormTrainerName() {
    const name = trainerNameInput.trim()
    if (!name || batchForm.trainerNames.includes(name)) return
    setBatchForm((f) => ({ ...f, trainerNames: [...f.trainerNames, name] }))
    setTrainerNameInput('')
  }

  function removeFormTrainerName(name) {
    setBatchForm((f) => ({ ...f, trainerNames: f.trainerNames.filter((n) => n !== name) }))
  }

  async function handleSaveBatch(e) {
    e.preventDefault()
    if (batchForm.class_days.length === 0) {
      setBatchFormError('Select at least one class day.')
      return
    }
    setSavingBatch(true)
    setBatchFormError('')
    try {
      await api(`/api/batches/${id}/`, {
        method: 'PATCH',
        body: {
          name: batchForm.name,
          course: Number(batchForm.course),
          description: batchForm.description,
          total_classes: Number(batchForm.total_classes),
          fee_per_student: batchForm.fee_per_student,
          payment_type: batchForm.payment_type,
          status: batchForm.status,
          accepting_enrollments: batchForm.accepting_enrollments,
          start_date: batchForm.start_date,
          class_time: batchForm.class_time,
          class_days: batchForm.class_days.join(','),
          meet_link: batchForm.meet_link,
          trainer_names: batchForm.trainerNames.join(', '),
        },
      })
      closeEditBatch()
      await loadBatch()
    } catch (err) {
      setBatchFormError(err.message)
    } finally {
      setSavingBatch(false)
    }
  }

  const [confirmDeleteBatchOpen, setConfirmDeleteBatchOpen] = useState(false)

  async function handleDeleteBatch() {
    setConfirmDeleteBatchOpen(false)
    setDeletingBatch(true)
    setError('')
    try {
      await api(`/api/batches/${id}/`, { method: 'DELETE' })
      navigate('/admin/batches')
    } catch (err) {
      setError(err.message)
      setDeletingBatch(false)
    }
  }

  async function refreshAfterMoneyChange() {
    await Promise.all([reloadEnrollments(), loadRevenue()])
  }

  const alreadyEnrolledIds = new Set(enrollments.map((e) => e.student))
  const availableStudents = students.filter((s) => !alreadyEnrolledIds.has(s.id))

  const [studentStatusFilter, setStudentStatusFilter] = useState('all')
  const [studentPaymentFilter, setStudentPaymentFilter] = useState('all')
  const [studentRegFilter, setStudentRegFilter] = useState('all')

  function enrollmentPaymentState(e) {
    const relevant = e.installments.filter((inst) => inst.paid_status !== 'cancelled')
    if (relevant.length === 0) return 'paid'
    return relevant.every((inst) => inst.paid_status === 'paid') ? 'paid' : 'pending'
  }

  // Search (studentSearch above) is already applied server-side via enrollmentsPath —
  // this only layers the status/payment/registration dropdowns on top of what's loaded,
  // same trade-off documented in usePaginatedList.
  const filteredEnrollments = enrollments.filter((e) => {
    if (studentStatusFilter !== 'all' && e.status !== studentStatusFilter) return false
    if (studentRegFilter === 'registered' && e.is_guest) return false
    if (studentRegFilter === 'guest' && !e.is_guest) return false
    if (studentPaymentFilter !== 'all' && enrollmentPaymentState(e) !== studentPaymentFilter) return false
    return true
  })

  function closeAddStudent() {
    setShowAddStudent(false)
    setAddMode('existing')
    setAddStudentId('')
    setGuestForm(EMPTY_GUEST_FORM)
    setAddStudentError('')
  }

  async function handleAddStudent(e) {
    e.preventDefault()
    setAddingStudent(true)
    setAddStudentError('')
    try {
      const body = addMode === 'existing'
        ? { batch: Number(id), student: Number(addStudentId) }
        : { batch: Number(id), ...guestForm }
      await api('/api/batch-enrollments/', { method: 'POST', body })
      closeAddStudent()
      await refreshAfterMoneyChange()
    } catch (err) {
      setAddStudentError(err.message)
    } finally {
      setAddingStudent(false)
    }
  }

  function openWithdraw(enrollment) {
    setWithdrawTarget(enrollment)
    setRefundForm({ refund_amount: '', refund_note: '' })
    setWithdrawError('')
  }

  async function handleWithdraw(e) {
    e.preventDefault()
    setBusy(true)
    setWithdrawError('')
    try {
      await api(`/api/batch-enrollments/${withdrawTarget.id}/withdraw/`, {
        method: 'POST',
        body: refundForm.refund_amount ? refundForm : {},
      })
      setWithdrawTarget(null)
      await refreshAfterMoneyChange()
    } catch (err) {
      setWithdrawError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleReactivate(enrollmentId) {
    setBusy(true)
    setError('')
    try {
      await api(`/api/batch-enrollments/${enrollmentId}/reactivate/`, { method: 'POST' })
      await refreshAfterMoneyChange()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const [removeTarget, setRemoveTarget] = useState(null)

  async function handleRemoveEnrollment() {
    setBusy(true)
    setError('')
    try {
      await api(`/api/batch-enrollments/${removeTarget.id}/`, { method: 'DELETE' })
      setRemoveTarget(null)
      await refreshAfterMoneyChange()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const [convertTarget, setConvertTarget] = useState(null)

  async function handleConvertToStudent() {
    setBusy(true)
    setError('')
    try {
      await api(`/api/batch-enrollments/${convertTarget.id}/convert_to_student/`, { method: 'POST' })
      setConvertTarget(null)
      await refreshAfterMoneyChange()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const [editGuestTarget, setEditGuestTarget] = useState(null)
  const [editGuestForm, setEditGuestForm] = useState(EMPTY_GUEST_FORM)
  const [editGuestError, setEditGuestError] = useState('')
  const [savingGuestEdit, setSavingGuestEdit] = useState(false)

  function openEditGuest(enrollment) {
    setEditGuestTarget(enrollment)
    setEditGuestForm({
      guest_name: enrollment.guest_name || '',
      guest_phone_number: enrollment.guest_phone_number || '',
      guest_email: enrollment.guest_email || '',
      guest_occupation: enrollment.guest_occupation || '',
      guest_source: enrollment.guest_source || '',
    })
    setEditGuestError('')
  }

  async function handleSaveGuestEdit(e) {
    e.preventDefault()
    setSavingGuestEdit(true)
    setEditGuestError('')
    try {
      await api(`/api/batch-enrollments/${editGuestTarget.id}/`, { method: 'PATCH', body: editGuestForm })
      setEditGuestTarget(null)
      await reloadEnrollments()
    } catch (err) {
      setEditGuestError(err.message)
    } finally {
      setSavingGuestEdit(false)
    }
  }

  async function handleMarkInstallmentPaid(installmentId) {
    setBusy(true)
    setError('')
    try {
      await api(`/api/batch-installments/${installmentId}/mark_paid/`, { method: 'POST' })
      await refreshAfterMoneyChange()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleRevokeInstallment(installmentId) {
    setBusy(true)
    setError('')
    try {
      await api(`/api/batch-installments/${installmentId}/revoke/`, { method: 'POST' })
      await refreshAfterMoneyChange()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function openEditInstallment(installment) {
    setEditingInstallmentId(installment.id)
    setEditingInstallmentAmount(installment.amount)
    setInstallmentEditError('')
  }

  async function handleSaveInstallmentAmount(installmentId) {
    setBusy(true)
    setInstallmentEditError('')
    try {
      await api(`/api/batch-installments/${installmentId}/`, {
        method: 'PATCH',
        body: { amount: editingInstallmentAmount },
      })
      setEditingInstallmentId(null)
      await refreshAfterMoneyChange()
    } catch (err) {
      setInstallmentEditError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleAddSession(e) {
    e.preventDefault()
    setAddingSession(true)
    setAddSessionError('')
    try {
      await api('/api/batch-sessions/', { method: 'POST', body: { batch: Number(id), ...sessionForm } })
      setSessionForm({ date: '', conducted_by_name: '', topic_covered: '', recording_link: '' })
      setShowAddSession(false)
      await loadSessions()
    } catch (err) {
      setAddSessionError(err.message)
    } finally {
      setAddingSession(false)
    }
  }

  function closeImport() {
    setShowImport(false)
    setImportFile(null)
    setImportResult(null)
    setImportError('')
  }

  async function handleDownloadTemplate() {
    setDownloadingTemplate(true)
    setImportError('')
    try {
      await downloadFile('/api/batches/import_template/', auth.token)
    } catch (err) {
      setImportError(err.message)
    } finally {
      setDownloadingTemplate(false)
    }
  }

  async function handleImport(e) {
    e.preventDefault()
    if (!importFile) return
    setImporting(true)
    setImportError('')
    setImportResult(null)
    try {
      const data = new FormData()
      data.append('file', importFile)
      const result = await apiUpload(`/api/batches/${id}/import_students/`, data, auth.token)
      setImportResult(result)
      setImportFile(null)
      await refreshAfterMoneyChange()
    } catch (err) {
      setImportError(err.message)
    } finally {
      setImporting(false)
    }
  }

  async function handleExportStudents() {
    setExporting(true)
    setError('')
    try {
      await downloadFile(`/api/batches/${id}/export_students/`, auth.token)
    } catch (err) {
      setError(err.message)
    } finally {
      setExporting(false)
    }
  }

  async function handleAddPayout(e) {
    e.preventDefault()
    setAddingPayout(true)
    setAddPayoutError('')
    try {
      await api('/api/batch-payouts/', { method: 'POST', body: { batch: Number(id), ...payoutForm } })
      setPayoutForm({ recipient_name: '', amount: '' })
      setShowAddPayout(false)
      await Promise.all([loadPayouts(), loadRevenue()])
    } catch (err) {
      setAddPayoutError(err.message)
    } finally {
      setAddingPayout(false)
    }
  }

  async function handleMarkPayoutPaid(payoutId) {
    setBusy(true)
    setError('')
    try {
      await api(`/api/batch-payouts/${payoutId}/mark_paid/`, { method: 'POST' })
      await loadPayouts()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (error && !batch) return <p className="text-error text-sm">{error}</p>
  if (!batch) return <p className="text-text-tertiary text-sm">Loading…</p>

  return (
    <div>
      <Link to="/admin/batches" className="text-sm font-medium text-primary hover:underline focus-ring">&larr; Back to batches</Link>

      <div className="flex flex-wrap items-center justify-between gap-3 mt-3 mb-6">
        <h1 className="text-2xl font-semibold text-navy">{batch.name}</h1>
        <div className="flex flex-wrap items-center gap-3">
          <Badge status={batch.status} />
          {!batch.accepting_enrollments && (
            <span className="text-xs text-warning bg-warning-tint rounded-full px-2.5 py-0.5">Enrollment closed</span>
          )}
          <Button variant="success" onClick={openEditBatch}>Edit details</Button>
          <Button variant="danger" disabled={deletingBatch} onClick={() => setConfirmDeleteBatchOpen(true)}>
            {deletingBatch ? 'Deleting…' : 'Delete batch'}
          </Button>
        </div>
      </div>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <Card className="mb-6">
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div><dt className="text-text-secondary">Course</dt><dd>{batch.course_name}</dd></div>
          <div><dt className="text-text-secondary">Total classes</dt><dd>{batch.total_classes}</dd></div>
          <div><dt className="text-text-secondary">Fee per student</dt><dd>₹{batch.fee_per_student}</dd></div>
          <div><dt className="text-text-secondary">Payment plan</dt><dd>{batch.payment_type_display}</dd></div>
          <div>
            <dt className="text-text-secondary">Schedule</dt>
            <dd>{formatDays(batch.class_days)}{batch.class_time && ` · ${formatTime(batch.class_time)}`}</dd>
          </div>
          <div><dt className="text-text-secondary">Started</dt><dd>{formatDate(batch.start_date)}</dd></div>
          <div>
            <dt className="text-text-secondary">Meet link</dt>
            <dd>
              {batch.meet_link ? (
                <a href={batch.meet_link} target="_blank" rel="noreferrer" className="text-primary hover:underline focus-ring">Open</a>
              ) : '—'}
            </dd>
          </div>
          <div><dt className="text-text-secondary">Sessions logged</dt><dd>{batch.session_count}</dd></div>
          <div className="col-span-2">
            <dt className="text-text-secondary">Trainers</dt>
            <dd>{batch.trainer_names ? batch.trainer_names.split(',').filter(Boolean).join(', ') : '—'}</dd>
          </div>
        </dl>
        {batch.description && (
          <p className="text-sm text-text-secondary mt-4 pt-4 border-t border-gray-100">{batch.description}</p>
        )}
      </Card>

      <Modal open={editingBatch} onClose={closeEditBatch} title="Edit batch details" maxWidthClass="max-w-2xl">
        {batchForm && (
          <form onSubmit={handleSaveBatch} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input required placeholder="Batch name" value={batchForm.name} onChange={(e) => setBatchForm({ ...batchForm, name: e.target.value })} className="input sm:col-span-2" />
            <SearchableSelect
              required
              placeholder="Search course…"
              value={batchForm.course}
              onChange={(v) => setBatchForm({ ...batchForm, course: v })}
              options={courses.map((c) => ({ value: c.id, label: c.name }))}
            />
            <select value={batchForm.status} onChange={(e) => setBatchForm({ ...batchForm, status: e.target.value })} className="input">
              <option value="ongoing">Ongoing</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
            </select>
            <input required type="number" min="1" placeholder="Total classes" value={batchForm.total_classes} onChange={(e) => setBatchForm({ ...batchForm, total_classes: e.target.value })} className="input" />
            <input
              required
              type="number"
              step="0.01"
              placeholder="Fee per student (₹)"
              value={batchForm.fee_per_student}
              onChange={(e) => setBatchForm({ ...batchForm, fee_per_student: e.target.value })}
              disabled={batch.enrolled_count > 0}
              className="input"
            />
            <select
              value={batchForm.payment_type}
              onChange={(e) => setBatchForm({ ...batchForm, payment_type: e.target.value })}
              disabled={batch.enrolled_count > 0}
              className="input"
            >
              {PAYMENT_TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            {batch.enrolled_count > 0 && (
              <p className="sm:col-span-2 text-xs text-text-tertiary -mt-2">
                Fee and payment plan are locked — {batch.enrolled_count} student(s) already enrolled, and their
                existing installments won't be recalculated.
              </p>
            )}
            <input required type="date" value={batchForm.start_date} onChange={(e) => setBatchForm({ ...batchForm, start_date: e.target.value })} className="input" />
            <input required type="time" value={batchForm.class_time} onChange={(e) => setBatchForm({ ...batchForm, class_time: e.target.value })} className="input" />
            <label className="sm:col-span-2 flex items-center gap-2 text-sm text-gray-600">
              <input
                type="checkbox"
                checked={batchForm.accepting_enrollments}
                onChange={(e) => setBatchForm({ ...batchForm, accepting_enrollments: e.target.checked })}
              />
              Accepting new enrollments (uncheck to close sign-ups without changing batch status)
            </label>
            <div className="sm:col-span-2">
              <p className="text-sm text-text-secondary mb-1">Class days</p>
              <div className="flex flex-wrap gap-2">
                {DAY_OPTIONS.map((d) => (
                  <Button
                    key={d.code}
                    type="button"
                    size="sm"
                    variant={batchForm.class_days.includes(d.code) ? 'primary' : 'secondary'}
                    onClick={() => toggleFormDay(d.code)}
                  >
                    {d.label}
                  </Button>
                ))}
              </div>
            </div>
            <div className="sm:col-span-2">
              <p className="text-sm text-text-secondary mb-1">
                Trainers (optional — any name, not just registered trainers; any number, for split schedules or co-teaching)
              </p>
              <div className="flex gap-2 mb-2">
                <input
                  placeholder="Type a name and add…"
                  value={trainerNameInput}
                  onChange={(e) => setTrainerNameInput(e.target.value)}
                  onKeyDown={(ev) => { if (ev.key === 'Enter') { ev.preventDefault(); addFormTrainerName() } }}
                  list="batch-trainer-suggestions-detail"
                  className="input flex-1"
                />
                <datalist id="batch-trainer-suggestions-detail">
                  {trainers.map((t) => <option key={t.id} value={t.name} />)}
                </datalist>
                <button type="button" onClick={addFormTrainerName} disabled={!trainerNameInput.trim()} className="text-sm font-medium text-primary hover:underline disabled:opacity-60 shrink-0 focus-ring">
                  + Add
                </button>
              </div>
              {batchForm.trainerNames.length > 0 && (
                <ul className="space-y-1">
                  {batchForm.trainerNames.map((name) => (
                    <li key={name} className="flex items-center justify-between text-sm bg-surface-sunken rounded px-3 py-1.5">
                      <span>{name}</span>
                      <button type="button" onClick={() => removeFormTrainerName(name)} className="text-xs font-medium text-error hover:underline focus-ring">
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <input placeholder="Google Meet link (optional)" value={batchForm.meet_link} onChange={(e) => setBatchForm({ ...batchForm, meet_link: e.target.value })} className="input sm:col-span-2" />
            <textarea placeholder="Description (optional)" value={batchForm.description} onChange={(e) => setBatchForm({ ...batchForm, description: e.target.value })} className="input sm:col-span-2" rows={2} />

            {batchFormError && <p className="sm:col-span-2 text-error text-xs">{batchFormError}</p>}
            <div className="sm:col-span-2 flex justify-end gap-3">
              <Button type="button" variant="ghost" onClick={closeEditBatch}>
                Cancel
              </Button>
              <Button type="submit" variant="success" disabled={savingBatch}>
                {savingBatch ? 'Saving…' : 'Save changes'}
              </Button>
            </div>
          </form>
        )}
      </Modal>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-6">
        <Card>
          <h2 className="text-sm font-semibold text-navy mb-3">Revenue — separate from billing cycles</h2>
          {revenue ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-text-secondary">Enrolled</dt><dd className="text-lg font-semibold text-navy tabular-nums">{revenue.enrolled_count}</dd></div>
              <div><dt className="text-text-secondary">Gross expected</dt><dd className="text-lg font-semibold text-navy tabular-nums">₹{revenue.gross_expected}</dd></div>
              <div><dt className="text-text-secondary">Collected</dt><dd className="text-lg font-semibold text-success tabular-nums">₹{revenue.collected}</dd></div>
              <div><dt className="text-text-secondary">Pending</dt><dd className="text-lg font-semibold text-warning tabular-nums">₹{revenue.pending}</dd></div>
              {Number(revenue.total_refunded) > 0 && (
                <div><dt className="text-text-secondary">Refunded</dt><dd className="text-lg font-semibold text-error tabular-nums">₹{revenue.total_refunded}</dd></div>
              )}
              <div className="col-span-2 pt-2 border-t border-gray-100">
                <dt className="text-text-secondary">Net after payouts</dt>
                <dd className="text-lg font-semibold text-navy tabular-nums">₹{revenue.net_after_payout}</dd>
              </div>
            </dl>
          ) : <p className="text-sm text-text-tertiary">Loading…</p>}
        </Card>

        <Card>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-navy">Payouts for running this batch</h2>
            <button onClick={() => setShowAddPayout(true)} className="text-xs font-medium text-primary hover:underline focus-ring">
              + Add payout
            </button>
          </div>
          {payouts.length > 0 ? (
            <ul className="space-y-2 text-sm">
              {payouts.map((p) => (
                <li key={p.id} className="flex items-center justify-between">
                  <span>
                    {p.recipient_name} <span className="text-text-secondary tabular-nums">· ₹{p.amount}</span>
                  </span>
                  <span className="flex items-center gap-2">
                    <Badge status={p.paid ? 'paid' : 'pending'} />
                    {p.paid ? (
                      p.paid_date && <span className="text-xs text-text-tertiary">on {formatDate(p.paid_date)}</span>
                    ) : (
                      <button disabled={busy} onClick={() => handleMarkPayoutPaid(p.id)} className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring">
                        Mark paid
                      </button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-text-tertiary">No payouts added for this batch yet — one entry per person.</p>
          )}
        </Card>
      </div>

      <Modal open={showAddPayout} onClose={() => setShowAddPayout(false)} title="Add a payout">
        <form onSubmit={handleAddPayout} className="space-y-3">
          <input
            required
            placeholder="Recipient name"
            value={payoutForm.recipient_name}
            onChange={(e) => setPayoutForm({ ...payoutForm, recipient_name: e.target.value })}
            list="batch-payout-suggestions"
            className="input"
          />
          <datalist id="batch-payout-suggestions">
            {(batch.trainer_names || '').split(',').map((n) => n.trim()).filter(Boolean).map((n) => <option key={n} value={n} />)}
          </datalist>
          <input
            required
            type="number"
            step="0.01"
            placeholder="Amount (₹)"
            value={payoutForm.amount}
            onChange={(e) => setPayoutForm({ ...payoutForm, amount: e.target.value })}
            className="input"
          />
          {addPayoutError && <p className="text-error text-xs">{addPayoutError}</p>}
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={() => setShowAddPayout(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="success" disabled={addingPayout}>
              {addingPayout ? 'Adding…' : 'Add'}
            </Button>
          </div>
        </form>
      </Modal>

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-navy">Enrolled students</h2>
        <div className="flex gap-2">
          <Button variant="secondary" disabled={exporting || enrollmentCount === 0} onClick={handleExportStudents}>
            {exporting ? 'Exporting…' : 'Export to Excel'}
          </Button>
          <Button
            variant="secondary"
            disabled={!batch.accepting_enrollments}
            onClick={() => setShowImport(true)}
            title={!batch.accepting_enrollments ? 'This batch is closed to new enrollments' : undefined}
          >
            Import from Excel
          </Button>
          <Button
            disabled={!batch.accepting_enrollments}
            onClick={() => setShowAddStudent(true)}
            title={!batch.accepting_enrollments ? 'This batch is closed to new enrollments' : undefined}
          >
            + Add student
          </Button>
        </div>
      </div>

      <Modal open={showImport} onClose={closeImport} title="Import students from Excel" maxWidthClass="max-w-lg">
        <div className="space-y-3">
          <p className="text-sm text-text-secondary">
            Download the response sheet from your Google Form, rename its columns to match the template below
            (extra columns like Timestamp are fine, they're ignored), then upload it here.
          </p>
          <button
            type="button"
            onClick={handleDownloadTemplate}
            disabled={downloadingTemplate}
            className="text-sm font-medium text-primary hover:underline disabled:opacity-60 focus-ring"
          >
            {downloadingTemplate ? 'Downloading…' : 'Download template (.xlsx)'}
          </button>
          <ul className="text-xs text-text-tertiary list-disc pl-4">
            <li><span className="font-medium text-text-secondary">Name</span> — required</li>
            <li><span className="font-medium text-text-secondary">Phone Number</span>, <span className="font-medium text-text-secondary">Occupation</span>, <span className="font-medium text-text-secondary">Email</span>, <span className="font-medium text-text-secondary">How did you know about us?</span> — optional</li>
            <li><span className="font-medium text-text-secondary">Payment Status</span> — "Paid" marks the upfront installment paid; leave blank otherwise</li>
          </ul>
          <p className="text-xs text-text-tertiary">
            Every row is added as someone not yet registered in the system — same as adding a guest by hand. This
            never creates or links a registered Student record.
          </p>
          <form onSubmit={handleImport} className="space-y-3 pt-2 border-t border-gray-100">
            <input
              required
              type="file"
              accept=".xlsx"
              onChange={(e) => setImportFile(e.target.files[0] || null)}
              className="input"
            />
            {importError && <p className="text-error text-xs">{importError}</p>}
            {importResult && (
              <div className="text-xs bg-surface-sunken rounded-lg p-3 space-y-1">
                <p className="text-success font-medium">
                  Enrolled {importResult.enrolled}
                  {importResult.marked_paid > 0 && `, ${importResult.marked_paid} marked paid`}.
                </p>
                {importResult.skipped.length > 0 && (
                  <div>
                    <p className="text-warning font-medium">{importResult.skipped.length} row(s) skipped:</p>
                    <ul className="list-disc pl-4 text-text-secondary">
                      {importResult.skipped.map((s, i) => <li key={i}>Row {s.row}: {s.reason}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}
            <div className="flex justify-end gap-3">
              <Button type="button" variant="ghost" onClick={closeImport}>
                Close
              </Button>
              <Button type="submit" variant="success" disabled={!importFile || importing}>
                {importing ? 'Importing…' : 'Import'}
              </Button>
            </div>
          </form>
        </div>
      </Modal>

      <Modal open={showAddStudent} onClose={closeAddStudent} title="Add student to batch">
        <div className="flex gap-2 mb-3">
          <Button type="button" size="sm" variant={addMode === 'existing' ? 'primary' : 'secondary'} onClick={() => setAddMode('existing')}>
            Registered student
          </Button>
          <Button type="button" size="sm" variant={addMode === 'guest' ? 'primary' : 'secondary'} onClick={() => setAddMode('guest')}>
            Not registered yet
          </Button>
        </div>
        <form onSubmit={handleAddStudent} className="space-y-3">
          {addMode === 'existing' ? (
            <SearchableSelect
              placeholder="Search student…"
              value={addStudentId}
              onChange={setAddStudentId}
              options={availableStudents.map((s) => ({ value: s.id, label: `${s.name} (${s.student_id})` }))}
            />
          ) : (
            <>
              <input
                required
                placeholder="Name"
                value={guestForm.guest_name}
                onChange={(e) => setGuestForm({ ...guestForm, guest_name: e.target.value })}
                className="input"
              />
              <input
                placeholder="Phone number (optional)"
                value={guestForm.guest_phone_number}
                onChange={(e) => setGuestForm({ ...guestForm, guest_phone_number: e.target.value })}
                className="input"
              />
              <input
                placeholder="Occupation (optional)"
                value={guestForm.guest_occupation}
                onChange={(e) => setGuestForm({ ...guestForm, guest_occupation: e.target.value })}
                className="input"
              />
              <input
                type="email"
                placeholder="Email (optional)"
                value={guestForm.guest_email}
                onChange={(e) => setGuestForm({ ...guestForm, guest_email: e.target.value })}
                className="input"
              />
              <input
                placeholder="How did they hear about us? (optional)"
                value={guestForm.guest_source}
                onChange={(e) => setGuestForm({ ...guestForm, guest_source: e.target.value })}
                className="input"
              />
              <p className="text-xs text-text-tertiary">Not registered as a student — this just records their details for this batch.</p>
            </>
          )}
          <p className="text-xs text-text-tertiary">
            Fee: ₹{batch.fee_per_student} · {batch.payment_type_display}
          </p>
          {addStudentError && <p className="text-error text-xs">{addStudentError}</p>}
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={closeAddStudent}>
              Cancel
            </Button>
            <Button
              disabled={(addMode === 'existing' ? !addStudentId : !guestForm.guest_name.trim()) || addingStudent}
              type="submit"
              variant="success"
            >
              {addingStudent ? 'Adding…' : 'Add'}
            </Button>
          </div>
        </form>
      </Modal>

      {enrollments.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <input
            placeholder="Search by name…"
            value={studentSearch}
            onChange={(e) => setStudentSearch(e.target.value)}
            className="input max-w-xs"
          />
          <select value={studentStatusFilter} onChange={(e) => setStudentStatusFilter(e.target.value)} className="input w-auto">
            <option value="all">All statuses</option>
            <option value="active">Active</option>
            <option value="withdrawn">Withdrawn</option>
          </select>
          <select value={studentPaymentFilter} onChange={(e) => setStudentPaymentFilter(e.target.value)} className="input w-auto">
            <option value="all">All payments</option>
            <option value="paid">Fully paid</option>
            <option value="pending">Payment pending</option>
          </select>
          <select value={studentRegFilter} onChange={(e) => setStudentRegFilter(e.target.value)} className="input w-auto">
            <option value="all">Registered + not registered</option>
            <option value="registered">Registered only</option>
            <option value="guest">Not registered only</option>
          </select>
          <span className="text-xs text-text-tertiary">
            {filteredEnrollments.length} shown · {enrollments.length} of {enrollmentCount} loaded
          </span>
        </div>
      )}

      <div className="space-y-3 mb-3">
        {filteredEnrollments.map((e) => (
          <Card key={e.id}>
            <div className="flex items-center justify-between mb-2">
              <div>
                {e.is_guest ? (
                  <span className="font-medium">{e.student_name}</span>
                ) : (
                  <Link to={`/admin/students/${e.student}`} className="text-primary hover:underline font-medium focus-ring">{e.student_name}</Link>
                )}
                {e.is_guest ? (
                  <span className="text-xs text-warning bg-warning-tint rounded px-1.5 py-0.5 ml-2">Not registered</span>
                ) : (
                  <span className="text-xs text-text-tertiary ml-2">{e.student_id_code}</span>
                )}
                <span className="text-xs text-text-tertiary ml-2">joined {formatDate(e.joined_date)}</span>
                {e.is_guest && (e.guest_phone_number || e.guest_email || e.guest_occupation || e.guest_source) && (
                  <div className="text-xs text-text-tertiary mt-0.5">
                    {[e.guest_phone_number, e.guest_email, e.guest_occupation, e.guest_source].filter(Boolean).join(' · ')}
                  </div>
                )}
                {e.status === 'withdrawn' && Number(e.refunded_amount) > 0 && (
                  <div className="text-xs text-error mt-0.5">
                    Refunded ₹{e.refunded_amount}{e.refund_note && ` — ${e.refund_note}`}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-3">
                <Badge status={e.status} />
                {e.is_guest && (
                  <button disabled={busy} onClick={() => openEditGuest(e)} className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring">
                    Edit
                  </button>
                )}
                {e.is_guest && (
                  <button disabled={busy} onClick={() => setConvertTarget(e)} className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring">
                    Register
                  </button>
                )}
                {e.status === 'active' && (
                  <button disabled={busy} onClick={() => openWithdraw(e)} className="text-xs font-medium text-error hover:underline disabled:opacity-60 focus-ring">
                    Withdraw
                  </button>
                )}
                {e.status === 'withdrawn' && (
                  <button disabled={busy} onClick={() => handleReactivate(e.id)} className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring">
                    Reactivate
                  </button>
                )}
                <button disabled={busy} onClick={() => setRemoveTarget(e)} className="text-xs text-text-tertiary hover:text-error hover:underline disabled:opacity-60 focus-ring">
                  Remove
                </button>
              </div>
            </div>
            <table className="w-full text-xs">
              <thead className="text-text-secondary text-left">
                <tr>
                  <th className="py-1 pr-4">Due</th>
                  <th className="py-1 pr-4">Amount</th>
                  <th className="py-1"></th>
                </tr>
              </thead>
              <tbody>
                {e.installments.map((inst) => (
                  <tr key={inst.id} className="border-t border-gray-50">
                    <td className="py-1 pr-4">
                      {inst.due_at_sessions === null ? 'At signup' : `By session ${inst.due_at_sessions}`}
                    </td>
                    <td className="py-1 pr-4 tabular-nums">
                      {editingInstallmentId === inst.id ? (
                        <input
                          type="number"
                          step="0.01"
                          autoFocus
                          value={editingInstallmentAmount}
                          onChange={(ev) => setEditingInstallmentAmount(ev.target.value)}
                          className="input py-0.5 px-1.5 text-xs w-24"
                        />
                      ) : (
                        `₹${inst.amount}`
                      )}
                    </td>
                    <td className="py-1 text-right whitespace-nowrap">
                      {editingInstallmentId === inst.id ? (
                        <span>
                          <button disabled={busy} onClick={() => handleSaveInstallmentAmount(inst.id)} className="font-medium text-success hover:underline focus-ring">
                            Save
                          </button>
                          {' · '}
                          <button onClick={() => setEditingInstallmentId(null)} className="text-text-tertiary hover:underline focus-ring">
                            Cancel
                          </button>
                        </span>
                      ) : inst.paid_status === 'cancelled' ? (
                        <span className="text-text-tertiary">Cancelled</span>
                      ) : inst.paid_status === 'paid' ? (
                        <span className="text-success">
                          Paid{inst.paid_date ? ` on ${formatDate(inst.paid_date)}` : ''}
                          {' · '}
                          <button disabled={busy} onClick={() => handleRevokeInstallment(inst.id)} className="text-text-tertiary hover:text-error hover:underline focus-ring">
                            Undo
                          </button>
                        </span>
                      ) : (
                        <span>
                          <button disabled={busy} onClick={() => handleMarkInstallmentPaid(inst.id)} className="font-medium text-primary hover:underline focus-ring">
                            Mark as paid
                          </button>
                          {' · '}
                          <button disabled={busy} onClick={() => openEditInstallment(inst)} className="text-text-tertiary hover:underline focus-ring">
                            Edit amount
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {installmentEditError && editingInstallmentId && <p className="text-error text-xs mt-1">{installmentEditError}</p>}
          </Card>
        ))}
        {enrollmentsLoading && <p className="text-text-tertiary text-sm">Loading…</p>}
        {!enrollmentsLoading && enrollments.length === 0 && <p className="text-text-tertiary text-sm">No students enrolled yet.</p>}
        {!enrollmentsLoading && enrollments.length > 0 && filteredEnrollments.length === 0 && (
          <p className="text-text-tertiary text-sm">No students match these filters.</p>
        )}
      </div>

      {!enrollmentsLoading && enrollments.length > 0 && (
        <div className="flex items-center justify-end gap-4 mb-6">
          {enrollmentsPage > 1 && (
            <button onClick={loadLessEnrollments} className="text-xs font-medium text-primary hover:underline focus-ring">
              Load less
            </button>
          )}
          {enrollmentsHasMore && (
            <button
              disabled={enrollmentsLoadingMore}
              onClick={loadMoreEnrollments}
              className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring"
            >
              {enrollmentsLoadingMore ? 'Loading…' : 'Load more'}
            </button>
          )}
        </div>
      )}

      <Modal open={Boolean(withdrawTarget)} onClose={() => setWithdrawTarget(null)} title="Withdraw student">
        {withdrawTarget && (
          <form onSubmit={handleWithdraw} className="space-y-3">
            <p className="text-sm text-gray-600">
              Withdraw <span className="font-medium">{withdrawTarget.student_name}</span> from this batch? Any pending
              installments will be cancelled.
            </p>
            <input
              type="number"
              step="0.01"
              placeholder="Refund amount (₹, optional)"
              value={refundForm.refund_amount}
              onChange={(e) => setRefundForm({ ...refundForm, refund_amount: e.target.value })}
              className="input"
            />
            <input
              placeholder="Refund note (optional)"
              value={refundForm.refund_note}
              onChange={(e) => setRefundForm({ ...refundForm, refund_note: e.target.value })}
              className="input"
            />
            <p className="text-xs text-text-tertiary">Leave the refund amount blank if nothing needs to be paid back.</p>
            {withdrawError && <p className="text-error text-xs">{withdrawError}</p>}
            <div className="flex justify-end gap-3">
              <Button type="button" variant="ghost" onClick={() => setWithdrawTarget(null)}>
                Cancel
              </Button>
              <Button disabled={busy} type="submit" variant="danger">
                {busy ? 'Withdrawing…' : 'Withdraw'}
              </Button>
            </div>
          </form>
        )}
      </Modal>

      <Modal open={Boolean(editGuestTarget)} onClose={() => setEditGuestTarget(null)} title="Edit details">
        {editGuestTarget && (
          <form onSubmit={handleSaveGuestEdit} className="space-y-3">
            <input
              required
              placeholder="Name"
              value={editGuestForm.guest_name}
              onChange={(e) => setEditGuestForm({ ...editGuestForm, guest_name: e.target.value })}
              className="input"
            />
            <input
              placeholder="Phone number (optional)"
              value={editGuestForm.guest_phone_number}
              onChange={(e) => setEditGuestForm({ ...editGuestForm, guest_phone_number: e.target.value })}
              className="input"
            />
            <input
              placeholder="Occupation (optional)"
              value={editGuestForm.guest_occupation}
              onChange={(e) => setEditGuestForm({ ...editGuestForm, guest_occupation: e.target.value })}
              className="input"
            />
            <input
              type="email"
              placeholder="Email (optional)"
              value={editGuestForm.guest_email}
              onChange={(e) => setEditGuestForm({ ...editGuestForm, guest_email: e.target.value })}
              className="input"
            />
            <input
              placeholder="How did they hear about us? (optional)"
              value={editGuestForm.guest_source}
              onChange={(e) => setEditGuestForm({ ...editGuestForm, guest_source: e.target.value })}
              className="input"
            />
            {editGuestError && <p className="text-error text-xs">{editGuestError}</p>}
            <div className="flex justify-end gap-3">
              <Button type="button" variant="ghost" onClick={() => setEditGuestTarget(null)}>
                Cancel
              </Button>
              <Button disabled={savingGuestEdit} type="submit" variant="success">
                {savingGuestEdit ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </form>
        )}
      </Modal>

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-navy">Sessions</h2>
        <Button onClick={() => setShowAddSession(true)}>+ Log session</Button>
      </div>

      <Modal open={showAddSession} onClose={() => setShowAddSession(false)} title="Log a session">
        <form onSubmit={handleAddSession} className="space-y-3">
          <input required type="date" value={sessionForm.date} onChange={(e) => setSessionForm({ ...sessionForm, date: e.target.value })} className="input" />
          <input required placeholder="Conducted by (name)" value={sessionForm.conducted_by_name} onChange={(e) => setSessionForm({ ...sessionForm, conducted_by_name: e.target.value })} className="input" />
          <input placeholder="Topic covered (optional)" value={sessionForm.topic_covered} onChange={(e) => setSessionForm({ ...sessionForm, topic_covered: e.target.value })} className="input" />
          <input placeholder="Recording link (Google Drive, optional)" value={sessionForm.recording_link} onChange={(e) => setSessionForm({ ...sessionForm, recording_link: e.target.value })} className="input" />
          {addSessionError && <p className="text-error text-xs">{addSessionError}</p>}
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={() => setShowAddSession(false)}>
              Cancel
            </Button>
            <Button disabled={addingSession} type="submit" variant="success">
              {addingSession ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </form>
      </Modal>

      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">Date</th>
              <th className="table-head-cell">Conducted by</th>
              <th className="table-head-cell">Topic</th>
              <th className="table-head-cell">Recording</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id} className="table-row">
                <td className="table-cell">{formatDate(s.date)}</td>
                <td className="table-cell">{s.conducted_by_name}</td>
                <td className="table-cell text-text-secondary">{s.topic_covered || '—'}</td>
                <td className="table-cell">
                  {s.recording_link ? (
                    <a href={s.recording_link} target="_blank" rel="noreferrer" className="font-medium text-primary hover:underline focus-ring">Open</a>
                  ) : '—'}
                </td>
              </tr>
            ))}
            {sessions.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-text-tertiary">No sessions logged yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <ConfirmDialog
        open={confirmDeleteBatchOpen}
        onClose={() => setConfirmDeleteBatchOpen(false)}
        onConfirm={handleDeleteBatch}
        title="Delete batch"
        message={`Delete "${batch?.name}"? This removes every enrollment, installment, session, and payout on it — this cannot be undone.`}
        confirmLabel="Delete batch"
        busyLabel="Deleting…"
        danger
        busy={deletingBatch}
      />

      <ConfirmDialog
        open={Boolean(removeTarget)}
        onClose={() => setRemoveTarget(null)}
        onConfirm={handleRemoveEnrollment}
        title="Remove student"
        message={`Remove ${removeTarget?.student_name} from this batch? This deletes their enrollment and installment history — this cannot be undone.`}
        confirmLabel="Remove"
        busyLabel="Removing…"
        danger
        busy={busy}
      />

      <ConfirmDialog
        open={Boolean(convertTarget)}
        onClose={() => setConvertTarget(null)}
        onConfirm={handleConvertToStudent}
        title="Register as student"
        message={`Register ${convertTarget?.student_name} as a student using the details captured here?`}
        confirmLabel="Register"
        busyLabel="Registering…"
        busy={busy}
      />
    </div>
  )
}
