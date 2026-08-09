import { useCallback, useEffect, useState } from 'react'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { Modal } from '../../components/Modal'
import { SearchableSelect } from '../../components/SearchableSelect'
import { useApi } from '../../hooks/useApi'
import { usePaginatedList } from '../../hooks/usePaginatedList'
import { usePickerSearch } from '../../hooks/usePickerSearch'
import { formatDate, formatDateRange } from '../../utils/date'
import { DAY_OPTIONS, formatDays, formatTime } from '../../utils/schedule'

const PAYMENT_PLAN_OPTIONS = [
  { value: 'two_installments', label: 'Two installments (10th class)' },
  { value: 'three_installments', label: 'Three installments (6th, 18th class)' },
  { value: 'four_installments', label: 'Four installments (6th, 11th, 18th class)' },
]

// The class count whose worth is due upfront (before class 1) for each plan —
// mirrors the backend's PLAN_SCHEDULES first milestone. See upfront_payment_for()
// in enrollments/services.py, which computes the authoritative amount server-side.
const UPFRONT_MILESTONE = {
  two_installments: 10,
  three_installments: 6,
  four_installments: 6,
}

const EMPTY_FORM = {
  student: '', course: '', trainer: '', class_time: '', class_days: [],
  payment_type: '', discount_percent: '0', classes_total: '24',
  trainer_rate_per_class: '', client_rate_per_class: '',
}

// Mirrors Trainer.has_rate_for() — an explicit per-course override, or the trainer's
// default rate. Only pre-checks what's already loaded client-side; the backend
// (EnrollmentSerializer.validate()) remains the authoritative check either way.
function trainerHasRateForCourse(trainer, courseId) {
  if (!trainer || !courseId) return true
  const hasOverride = (trainer.course_rates || []).some((r) => String(r.course) === String(courseId))
  if (hasOverride) return true
  return trainer.default_rate_per_class != null
}

// Mirrors Trainer.rate_for() / Client.rate_for(): an explicit per-course override, else
// the entity's own default/flat rate. Used only to pre-fill the enrollment form's rate
// fields — the backend recomputes the same default if the field is left blank.
function rateForCourse(entity, courseId) {
  if (!entity || !courseId) return null
  const override = (entity.course_rates || []).find((r) => String(r.course) === String(courseId))
  if (override) return override.rate_per_class
  return entity.default_rate_per_class ?? entity.rate_per_class ?? null
}

// Mirrors find_schedule_conflict() in enrollments/services.py: same trainer, same
// class_time, at least one overlapping class_day, on either the trainer's own ongoing
// enrollments or anything they're currently covering as a substitute. Only checks
// against enrollments/substitute assignments already loaded client-side — a best-effort
// pre-check, not a replacement for the backend's own check.
function findScheduleConflict(trainerId, classTime, classDays, enrollments, substituteAssignments, excludeEnrollmentId = null) {
  if (!trainerId || !classTime || classDays.length === 0) return null
  const daysSet = new Set(classDays)
  const overlapsDays = (days) => (days || '').split(',').some((d) => daysSet.has(d))

  const own = enrollments.find((e) =>
    String(e.trainer) === String(trainerId) && e.status === 'ongoing' && e.id !== excludeEnrollmentId &&
    (e.class_time || '').slice(0, 5) === classTime && overlapsDays(e.class_days)
  )
  if (own) return own

  for (const sa of substituteAssignments) {
    if (String(sa.substitute_trainer) !== String(trainerId)) continue
    const covered = enrollments.find((e) => e.id === sa.enrollment)
    if (!covered || covered.id === excludeEnrollmentId) continue
    if ((covered.class_time || '').slice(0, 5) === classTime && overlapsDays(covered.class_days)) {
      return covered
    }
  }
  return null
}

export default function EnrollmentsPage() {
  const api = useApi()
  const pickerSearch = usePickerSearch()
  // The "New enrollment" form's student/course/trainer pickers are async-search (see
  // SearchableSelect's loadOptions mode) rather than backed by a preloaded list, so the
  // full picked objects are captured here directly from each picker's onChange instead
  // of being looked up from an array — see rateForCourse()/trainerHasRateForCourse()
  // below, which only ever need the one currently-selected entity, not the whole list.
  const [selectedStudent, setSelectedStudent] = useState(null)
  const [selectedCourse, setSelectedCourse] = useState(null)
  const [selectedTrainer, setSelectedTrainer] = useState(null)
  // The B2B student's client — fetched by id (not searched) once a B2B student is
  // picked, since the student picker's own result already carries the client's id/name
  // but not its rate data.
  const [selectedClient, setSelectedClient] = useState(null)
  const [substituteAssignments, setSubstituteAssignments] = useState([])
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [tab, setTab] = useState('ongoing')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Debounced so rapid typing doesn't fire a request per keystroke — the actual search
  // runs server-side (see EnrollmentViewSet.search_fields), so it always covers every
  // enrollment regardless of how many pages have been loaded.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  const enrollmentsPath = debouncedSearch ? `/api/enrollments/?search=${encodeURIComponent(debouncedSearch)}` : '/api/enrollments/'
  const {
    items: enrollments, count: enrollmentCount, hasMore, loading, loadingMore,
    reload: loadEnrollments, loadMore, loadLess, page,
  } = usePaginatedList(enrollmentsPath)

  const loadSubstituteAssignments = useCallback(async () => {
    setSubstituteAssignments(await api('/api/substitute-assignments/'))
  }, [api])

  useEffect(() => {
    loadEnrollments().catch((err) => setError(err.message))
  }, [loadEnrollments])

  useEffect(() => {
    loadSubstituteAssignments().catch(() => {})
  }, [loadSubstituteAssignments])

  function toggleDay(code) {
    setForm((f) => ({
      ...f,
      class_days: f.class_days.includes(code) ? f.class_days.filter((d) => d !== code) : [...f.class_days, code],
    }))
  }

  const upfrontMilestone = UPFRONT_MILESTONE[form.payment_type]

  // Standard price = course rate x total classes. The admin only enters a discount
  // percentage (capped at 15%, enforced server-side too) — the discounted total and the
  // upfront amount are both derived from it. Mirrors total_amount_for_discount() /
  // upfront_payment_for() in enrollments/services.py.
  const formClassesTotal = Number(form.classes_total) || null
  const standardTotal =
    selectedCourse?.rate_per_class && formClassesTotal
      ? Number(selectedCourse.rate_per_class) * formClassesTotal
      : null
  const discountPercent = form.discount_percent === '' ? 0 : Number(form.discount_percent)
  const discountedTotal = standardTotal != null ? Math.round(standardTotal * (1 - discountPercent / 100) * 100) / 100 : null
  const upfrontPreview =
    discountedTotal != null && upfrontMilestone && formClassesTotal
      ? Math.round(upfrontMilestone * (discountedTotal / formClassesTotal))
      : null

  async function handleSubmit(e) {
    e.preventDefault()
    if (form.class_days.length === 0) {
      setError('Select at least one class day.')
      return
    }

    if (selectedTrainer && selectedCourse && !trainerHasRateForCourse(selectedTrainer, selectedCourse.id)) {
      setError(
        `${selectedTrainer.name} has no rate set for ${selectedCourse.name} — set a default rate or add a course override first.`
      )
      return
    }

    const conflict = findScheduleConflict(form.trainer, form.class_time, form.class_days, enrollments, substituteAssignments)
    if (selectedTrainer && conflict) {
      setError(
        `${selectedTrainer.name} already has a class at that time — ${conflict.student_name} (${conflict.course_name}). Choose a different time or trainer.`
      )
      return
    }

    if (selectedStudent?.source_type === 'B2C' && selectedCourse && !selectedCourse.rate_per_class) {
      setError(`${selectedCourse.name} has no B2C rate set — set one on the Courses page first.`)
      return
    }

    setSubmitting(true)
    setError('')
    try {
      await api('/api/enrollments/', {
        method: 'POST',
        body: {
          student: Number(form.student),
          course: Number(form.course),
          trainer: Number(form.trainer),
          class_time: form.class_time,
          class_days: form.class_days.join(','),
          classes_total: Number(form.classes_total) || 24,
          ...(form.trainer_rate_per_class !== '' ? { trainer_rate_per_class: form.trainer_rate_per_class } : {}),
          ...(selectedStudent?.source_type === 'B2B' && form.client_rate_per_class !== '' ? {
            client_rate_per_class: form.client_rate_per_class,
          } : {}),
          ...(selectedStudent?.source_type === 'B2C' ? {
            payment_type: form.payment_type,
            discount_percent: form.discount_percent || '0',
          } : {}),
        },
      })
      setForm(EMPTY_FORM)
      setSelectedStudent(null)
      setSelectedCourse(null)
      setSelectedTrainer(null)
      setSelectedClient(null)
      setShowForm(false)
      await loadEnrollments()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const [transferId, setTransferId] = useState(null)
  const [transferTrainer, setTransferTrainer] = useState('')
  const [transferring, setTransferring] = useState(false)
  const [transferError, setTransferError] = useState('')

  function openTransfer(enrollmentId) {
    closeEditSchedule()
    closeWithdraw()
    closeSubstitute()
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
      await loadEnrollments()
    } catch (err) {
      setTransferError(err.message)
    } finally {
      setTransferring(false)
    }
  }

  const [withdrawId, setWithdrawId] = useState(null)
  const [withdrawRefundAmount, setWithdrawRefundAmount] = useState('')
  const [withdrawRefundNote, setWithdrawRefundNote] = useState('')
  const [withdrawing, setWithdrawing] = useState(false)
  const [withdrawError, setWithdrawError] = useState('')

  function openWithdraw(enrollmentId) {
    closeTransfer()
    closeEditSchedule()
    closeSubstitute()
    setWithdrawId(enrollmentId)
    setWithdrawRefundAmount('')
    setWithdrawRefundNote('')
    setWithdrawError('')
  }

  function closeWithdraw() {
    setWithdrawId(null)
    setWithdrawRefundAmount('')
    setWithdrawRefundNote('')
    setWithdrawError('')
  }

  async function handleWithdraw(enrollmentId) {
    setWithdrawing(true)
    setWithdrawError('')
    try {
      await api(`/api/enrollments/${enrollmentId}/withdraw/`, {
        method: 'POST',
        body: {
          ...(withdrawRefundAmount ? { refund_amount: withdrawRefundAmount } : {}),
          refund_note: withdrawRefundNote,
        },
      })
      closeWithdraw()
      await loadEnrollments()
    } catch (err) {
      setWithdrawError(err.message)
    } finally {
      setWithdrawing(false)
    }
  }

  const [substituteId, setSubstituteId] = useState(null)
  const [substituteTrainer, setSubstituteTrainer] = useState('')
  const [substituteStart, setSubstituteStart] = useState('')
  const [substituteEnd, setSubstituteEnd] = useState('')
  const [assigningSubstitute, setAssigningSubstitute] = useState(false)
  const [substituteError, setSubstituteError] = useState('')
  const [cancellingSubstituteId, setCancellingSubstituteId] = useState(null)

  function openSubstitute(enrollmentId) {
    closeTransfer()
    closeEditSchedule()
    closeWithdraw()
    setSubstituteId(enrollmentId)
    setSubstituteTrainer('')
    setSubstituteStart('')
    setSubstituteEnd('')
    setSubstituteError('')
  }

  function closeSubstitute() {
    setSubstituteId(null)
    setSubstituteTrainer('')
    setSubstituteStart('')
    setSubstituteEnd('')
    setSubstituteError('')
  }

  async function handleAssignSubstitute(enrollmentId) {
    setAssigningSubstitute(true)
    setSubstituteError('')
    try {
      await api(`/api/enrollments/${enrollmentId}/assign_substitute/`, {
        method: 'POST',
        body: { trainer: Number(substituteTrainer), start_date: substituteStart, end_date: substituteEnd },
      })
      closeSubstitute()
      await loadSubstituteAssignments()
    } catch (err) {
      setSubstituteError(err.message)
    } finally {
      setAssigningSubstitute(false)
    }
  }

  const [cancelSubstituteTarget, setCancelSubstituteTarget] = useState(null)

  async function handleCancelSubstitute() {
    const assignmentId = cancelSubstituteTarget
    setCancellingSubstituteId(assignmentId)
    try {
      await api(`/api/substitute-assignments/${assignmentId}/`, { method: 'DELETE' })
      setCancelSubstituteTarget(null)
      await loadSubstituteAssignments()
    } catch (err) {
      setError(err.message)
    } finally {
      setCancellingSubstituteId(null)
    }
  }

  const [editId, setEditId] = useState(null)
  const [editCourse, setEditCourse] = useState('')
  const [editClassTime, setEditClassTime] = useState('')
  const [editClassDays, setEditClassDays] = useState([])
  const [editClassesTotal, setEditClassesTotal] = useState('')
  const [editSaving, setEditSaving] = useState(false)
  const [editError, setEditError] = useState('')

  function openEditSchedule(enrollment) {
    closeTransfer()
    closeWithdraw()
    closeSubstitute()
    setEditId(enrollment.id)
    setEditCourse(String(enrollment.course))
    setEditClassTime((enrollment.class_time || '').slice(0, 5))
    setEditClassDays((enrollment.class_days || '').split(',').filter(Boolean))
    setEditClassesTotal(String(enrollment.classes_total))
    setEditError('')
  }

  function closeEditSchedule() {
    setEditId(null)
    setEditCourse('')
    setEditClassTime('')
    setEditClassDays([])
    setEditClassesTotal('')
    setEditError('')
  }

  function toggleEditDay(code) {
    setEditClassDays((days) => (days.includes(code) ? days.filter((d) => d !== code) : [...days, code]))
  }

  async function handleEditSchedule(enrollmentId) {
    if (editClassDays.length === 0) {
      setEditError('Select at least one class day.')
      return
    }
    setEditSaving(true)
    setEditError('')
    try {
      await api(`/api/enrollments/${enrollmentId}/`, {
        method: 'PATCH',
        body: {
          course: Number(editCourse),
          class_time: editClassTime,
          class_days: editClassDays.join(','),
          classes_total: Number(editClassesTotal),
        },
      })
      closeEditSchedule()
      await loadEnrollments()
    } catch (err) {
      setEditError(err.message)
    } finally {
      setEditSaving(false)
    }
  }

  const nextBatchNumber =
    form.student && form.course
      ? enrollments.filter((e) => String(e.student) === form.student && String(e.course) === form.course).length + 1
      : null

  // Soft warning only — a student intentionally repeating/retaking a course in a new
  // batch is valid, so this doesn't block submission, just flags the likely-accidental
  // case (e.g. a double-click or re-submit) before it happens.
  const duplicateOngoingEnrollment =
    form.student && form.course
      ? enrollments.find(
          (e) => String(e.student) === form.student && String(e.course) === form.course && e.status === 'ongoing'
        )
      : null

  const editingEnrollment = enrollments.find((en) => en.id === editId)
  const transferEnrollment = enrollments.find((en) => en.id === transferId)
  const substituteEnrollment = enrollments.find((en) => en.id === substituteId)
  const withdrawEnrollment = enrollments.find((en) => en.id === withdrawId)

  // Search is already applied server-side (see enrollmentsPath above) — this only
  // layers the status tab on top of the already-matching results.
  const filteredEnrollments = enrollments.filter((e) => e.status === tab)

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-navy">Enrollments</h1>
        <Button onClick={() => setShowForm(true)}>+ New enrollment</Button>
      </div>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <Modal open={showForm} onClose={() => setShowForm(false)} title="New enrollment" maxWidthClass="max-w-2xl">
        <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <SearchableSelect
              required
              placeholder="Search student…"
              value={form.student}
              selectedLabel={selectedStudent ? `${selectedStudent.name} (${selectedStudent.student_id})` : undefined}
              onChange={(v, student) => {
                setSelectedStudent(student)
                setSelectedClient(null)
                setForm((f) => ({
                  ...f,
                  student: v,
                  payment_type: '',
                  discount_percent: '0',
                  client_rate_per_class: '',
                }))
                // The student picker's own result already has the client's id/name, but
                // not its rate data — fetched by id (not searched) so rateForCourse()
                // below has what it needs.
                if (student?.source_type === 'B2B' && student.client) {
                  api(`/api/clients/${student.client}/`)
                    .then((client) => {
                      setSelectedClient(client)
                      setForm((f) => ({ ...f, client_rate_per_class: String(rateForCourse(client, f.course) ?? '') }))
                    })
                    .catch(() => {})
                }
              }}
              loadOptions={pickerSearch.students}
            />
            <SearchableSelect
              required
              placeholder="Search course…"
              value={form.course}
              selectedLabel={selectedCourse?.name}
              onChange={(v, course) => {
                // Default the batch count to this course's standard length — nothing
                // tied these together before, so "Batch count" silently stayed at
                // EMPTY_FORM's hardcoded 24 regardless of which course was picked,
                // which also fed the B2C total-price preview below with the wrong
                // class count for any course whose real length isn't 24. Still
                // editable afterward for a genuinely partial/extended batch. Trainer
                // rate/class and (for B2B) client rate/class are re-suggested the same
                // way — still editable afterward too.
                setSelectedCourse(course)
                setForm((f) => ({
                  ...f,
                  course: v,
                  classes_total: course ? String(course.total_classes) : f.classes_total,
                  trainer_rate_per_class: selectedTrainer ? String(rateForCourse(selectedTrainer, v) ?? '') : f.trainer_rate_per_class,
                  client_rate_per_class: selectedClient ? String(rateForCourse(selectedClient, v) ?? '') : f.client_rate_per_class,
                }))
              }}
              loadOptions={pickerSearch.courses}
            />
            <SearchableSelect
              required
              placeholder="Search trainer…"
              value={form.trainer}
              selectedLabel={selectedTrainer?.name}
              onChange={(v, trainer) => {
                setSelectedTrainer(trainer)
                setForm((f) => ({
                  ...f,
                  trainer: v,
                  trainer_rate_per_class: trainer ? String(rateForCourse(trainer, f.course) ?? '') : f.trainer_rate_per_class,
                }))
              }}
              loadOptions={pickerSearch.trainers}
            />
            <input
              required
              type="time"
              value={form.class_time}
              onChange={(e) => setForm({ ...form, class_time: e.target.value })}
              className="input"
            />
            <div>
              <label className="block text-xs text-text-secondary mb-1">Batch count (total classes)</label>
              <input
                required
                type="number"
                min="1"
                placeholder="Batch count"
                value={form.classes_total}
                onChange={(e) => setForm({ ...form, classes_total: e.target.value })}
                className="input"
              />
            </div>
            <div>
              <label className="block text-xs text-text-secondary mb-1">Trainer rate/class (₹)</label>
              <input
                type="number"
                min="0"
                step="0.01"
                placeholder="Trainer rate/class"
                value={form.trainer_rate_per_class}
                onChange={(e) => setForm({ ...form, trainer_rate_per_class: e.target.value })}
                className="input"
              />
            </div>
            <div className="sm:col-span-2">
              <p className="text-sm text-text-secondary mb-1">Class days</p>
              <div className="flex flex-wrap gap-2">
                {DAY_OPTIONS.map((d) => (
                  <Button
                    key={d.code}
                    type="button"
                    size="sm"
                    variant={form.class_days.includes(d.code) ? 'primary' : 'secondary'}
                    onClick={() => toggleDay(d.code)}
                  >
                    {d.label}
                  </Button>
                ))}
              </div>
            </div>
            {selectedStudent?.source_type === 'B2B' && (
              <>
                <div className="input bg-surface-sunken text-text-secondary flex items-center justify-between">
                  <span>Client</span>
                  <span className="font-medium text-navy">
                    {selectedStudent.client_name || '— no client set on this student'}
                  </span>
                </div>
                <div>
                  <label className="block text-xs text-text-secondary mb-1">Client rate/class (₹)</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="Client rate/class"
                    value={form.client_rate_per_class}
                    onChange={(e) => setForm({ ...form, client_rate_per_class: e.target.value })}
                    className="input"
                  />
                </div>
              </>
            )}
            {selectedStudent?.source_type === 'B2C' && (
              <>
                <p className="sm:col-span-2 text-xs text-text-tertiary -mb-1">Payment plan</p>
                <select
                  required
                  value={form.payment_type}
                  onChange={(e) => setForm({ ...form, payment_type: e.target.value })}
                  className="input"
                >
                  <option value="">Select payment plan…</option>
                  {PAYMENT_PLAN_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
                <div className="input bg-surface-sunken text-text-secondary flex items-center justify-between">
                  <span>Course rate</span>
                  <span className="font-medium text-navy">
                    {selectedCourse?.rate_per_class ? `₹${selectedCourse.rate_per_class}/class` : '— select a course first'}
                  </span>
                </div>
                <div>
                  <input
                    required
                    type="number"
                    min="0"
                    max="15"
                    step="0.01"
                    placeholder="Discount %"
                    value={form.discount_percent}
                    onChange={(e) => setForm({ ...form, discount_percent: e.target.value })}
                    className="input"
                  />
                  {standardTotal != null && (
                    <p className="text-xs text-text-tertiary mt-1">
                      Standard total ₹{standardTotal} → after {discountPercent || 0}% off: ₹{discountedTotal} (max 15% discount)
                    </p>
                  )}
                </div>
                <div className="input bg-surface-sunken text-text-secondary flex items-center justify-between">
                  <span>Due before class 1</span>
                  <span className="font-medium text-navy">
                    {upfrontPreview != null ? `₹${upfrontPreview}` : '—'}
                  </span>
                </div>
                {form.payment_type && (
                  <p className="sm:col-span-2 text-xs text-text-tertiary -mt-2">
                    Upfront amount = {upfrontMilestone} classes × this plan's effective rate (discounted total ÷ total
                    classes), rounded to the nearest rupee.
                  </p>
                )}
              </>
            )}
            {nextBatchNumber && (
              <p className="sm:col-span-2 text-sm text-text-secondary">
                This will be created as <strong>Batch {nextBatchNumber}</strong> for this student + course.
              </p>
            )}
            {duplicateOngoingEnrollment && (
              <p className="sm:col-span-2 text-sm text-warning">
                Heads up — {duplicateOngoingEnrollment.student_name} already has an ongoing enrollment in this course
                (Batch {duplicateOngoingEnrollment.batch_number}, with {duplicateOngoingEnrollment.trainer_name}). If
                this is a mistake (e.g. a double submit), cancel and check the Enrollments list first.
              </p>
            )}
            {error && <p className="sm:col-span-2 text-error text-xs">{error}</p>}
            <div className="sm:col-span-2 flex justify-end gap-3">
              <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="success" disabled={submitting}>
                {submitting ? 'Saving…' : 'Create enrollment'}
              </Button>
            </div>
        </form>
      </Modal>

      <Modal open={editId != null} onClose={closeEditSchedule} title="Edit schedule">
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-text-secondary mb-1">Course</label>
            {editingEnrollment?.classes_completed === 0 ? (
              <SearchableSelect
                placeholder="Search course…"
                value={editCourse}
                selectedLabel={editingEnrollment?.course_name}
                onChange={setEditCourse}
                loadOptions={pickerSearch.courses}
              />
            ) : (
              <p className="text-sm text-text-secondary">
                {editingEnrollment?.course_name} <span className="text-xs text-text-tertiary">— can't be changed once classes have started.</span>
              </p>
            )}
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">Class time</label>
            <input type="time" value={editClassTime} onChange={(ev) => setEditClassTime(ev.target.value)} className="input" />
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">Batch count (total classes)</label>
            <input
              type="number"
              min={editingEnrollment?.classes_completed || 1}
              value={editClassesTotal}
              onChange={(ev) => setEditClassesTotal(ev.target.value)}
              className="input"
            />
            {editingEnrollment?.classes_completed > 0 && (
              <p className="text-xs text-text-tertiary mt-1">
                Can't be less than the {editingEnrollment.classes_completed} classes already completed.
              </p>
            )}
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">Class days</label>
            <div className="flex flex-wrap gap-2">
              {DAY_OPTIONS.map((d) => (
                <Button
                  key={d.code}
                  type="button"
                  size="sm"
                  variant={editClassDays.includes(d.code) ? 'primary' : 'secondary'}
                  onClick={() => toggleEditDay(d.code)}
                >
                  {d.label}
                </Button>
              ))}
            </div>
          </div>
          {editError && <p className="text-error text-xs">{editError}</p>}
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={closeEditSchedule}>
              Cancel
            </Button>
            <Button variant="success" disabled={editSaving} onClick={() => handleEditSchedule(editId)}>
              {editSaving ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal open={transferId != null} onClose={closeTransfer} title="Transfer enrollment">
        <div className="space-y-3">
          <p className="text-sm text-text-secondary">
            Move <strong>{transferEnrollment?.student_name}</strong>'s {transferEnrollment?.course_name} enrollment to a different trainer.
          </p>
          <SearchableSelect
            placeholder="Search trainer…"
            value={transferTrainer}
            onChange={setTransferTrainer}
            loadOptions={(q) => pickerSearch.trainers(q).then((ts) => ts.filter((t) => t.id !== transferEnrollment?.trainer))}
          />
          {transferError && <p className="text-error text-xs">{transferError}</p>}
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={closeTransfer}>
              Cancel
            </Button>
            <Button variant="success" disabled={!transferTrainer || transferring} onClick={() => handleTransfer(transferId)}>
              {transferring ? 'Transferring…' : 'Confirm'}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal open={substituteId != null} onClose={closeSubstitute} title="Assign substitute">
        <div className="space-y-3">
          <p className="text-sm text-text-secondary">
            Temporary coverage for <strong>{substituteEnrollment?.student_name}</strong>'s {substituteEnrollment?.course_name} classes.
          </p>
          <SearchableSelect
            placeholder="Search substitute trainer…"
            value={substituteTrainer}
            onChange={setSubstituteTrainer}
            loadOptions={(q) => pickerSearch.trainers(q).then((ts) => ts.filter((t) => t.id !== substituteEnrollment?.trainer))}
          />
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-text-secondary mb-1">Start date</label>
              <input type="date" value={substituteStart} onChange={(ev) => setSubstituteStart(ev.target.value)} className="input" />
            </div>
            <div>
              <label className="block text-xs text-text-secondary mb-1">End date</label>
              <input type="date" value={substituteEnd} onChange={(ev) => setSubstituteEnd(ev.target.value)} className="input" />
            </div>
          </div>
          {substituteError && <p className="text-error text-xs">{substituteError}</p>}
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={closeSubstitute}>
              Cancel
            </Button>
            <Button
              variant="success"
              disabled={!substituteTrainer || !substituteStart || !substituteEnd || assigningSubstitute}
              onClick={() => handleAssignSubstitute(substituteId)}
            >
              {assigningSubstitute ? 'Assigning…' : 'Confirm'}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal open={withdrawId != null} onClose={closeWithdraw} title="Withdraw enrollment">
        <div className="space-y-3">
          <p className="text-sm text-text-secondary">
            Withdraw <strong>{withdrawEnrollment?.student_name}</strong> from {withdrawEnrollment?.course_name}.
          </p>
          {withdrawEnrollment?.student_source_type === 'B2C' && (
            <>
              <input
                type="number"
                step="0.01"
                min="0"
                placeholder="Refund amount (₹, optional)"
                value={withdrawRefundAmount}
                onChange={(ev) => setWithdrawRefundAmount(ev.target.value)}
                className="input"
              />
              <input
                type="text"
                placeholder="Refund note (optional)"
                value={withdrawRefundNote}
                onChange={(ev) => setWithdrawRefundNote(ev.target.value)}
                className="input"
              />
            </>
          )}
          <p className="text-xs text-text-tertiary">
            Any pending installments will be cancelled. Classes already taught stay on record.
          </p>
          {withdrawError && <p className="text-error text-xs">{withdrawError}</p>}
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={closeWithdraw}>
              Cancel
            </Button>
            <Button variant="danger" disabled={withdrawing} onClick={() => handleWithdraw(withdrawId)}>
              {withdrawing ? 'Withdrawing…' : 'Confirm withdrawal'}
            </Button>
          </div>
        </div>
      </Modal>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <input
          placeholder="Search by student, course, or trainer…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input max-w-sm"
        />
        <div className="flex gap-2 shrink-0">
          {['ongoing', 'completed', 'withdrawn'].map((t) => (
            <Button key={t} variant={tab === t ? 'primary' : 'secondary'} className="capitalize" onClick={() => setTab(t)}>
              {t}
            </Button>
          ))}
        </div>
      </div>

      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">#</th>
              <th className="table-head-cell">Student</th>
              <th className="table-head-cell">Course</th>
              <th className="table-head-cell">Trainer</th>
              <th className="table-head-cell">Schedule</th>
              <th className="table-head-cell">Batch</th>
              <th className="table-head-cell">Progress</th>
              <th className="table-head-cell">Status</th>
              <th className="table-head-cell">Enrolled</th>
              <th className="table-head-cell"></th>
            </tr>
          </thead>
          <tbody>
            {filteredEnrollments.map((e, i) => (
              <tr key={e.id} className="table-row">
                <td className="table-cell text-text-tertiary">{i + 1}</td>
                <td className="table-cell">{e.student_name}</td>
                <td className="table-cell">{e.course_name}</td>
                <td className="table-cell">{e.trainer_name}</td>
                <td className="table-cell text-text-secondary">
                  {formatDays(e.class_days)}{e.class_time && ` · ${formatTime(e.class_time)}`}
                </td>
                <td className="table-cell">{e.batch_number}</td>
                <td className="table-cell tabular-nums">{e.classes_completed}/{e.classes_total}</td>
                <td className="table-cell"><Badge status={e.status} /></td>
                <td className="table-cell">{formatDate(e.start_date)}</td>
                <td className="table-cell text-right">
                  {(e.status === 'ongoing' || e.status === 'completed') && (
                    <div className="space-y-1">
                      <div className="flex flex-wrap justify-end gap-x-3 gap-y-1">
                        <button onClick={() => openEditSchedule(e)} className="font-medium text-primary hover:underline whitespace-nowrap focus-ring">
                          Edit
                        </button>
                        {e.status === 'ongoing' && (
                          <>
                            <button onClick={() => openTransfer(e.id)} className="font-medium text-primary hover:underline whitespace-nowrap focus-ring">
                              Transfer
                            </button>
                            <button onClick={() => openSubstitute(e.id)} className="font-medium text-primary hover:underline whitespace-nowrap focus-ring">
                              Substitute
                            </button>
                            <button onClick={() => openWithdraw(e.id)} className="font-medium text-error hover:underline whitespace-nowrap focus-ring">
                              Withdraw
                            </button>
                          </>
                        )}
                      </div>
                      {e.status === 'ongoing' && substituteAssignments.filter((sa) => sa.enrollment === e.id).map((sa) => (
                        <div key={sa.id} className="text-xs text-text-tertiary">
                          {sa.substitute_trainer_name} covering {formatDateRange(sa.start_date, sa.end_date)}
                          {' · '}
                          <button
                            disabled={cancellingSubstituteId === sa.id}
                            onClick={() => setCancelSubstituteTarget(sa.id)}
                            className="font-medium text-error hover:underline disabled:opacity-60 focus-ring"
                          >
                            {cancellingSubstituteId === sa.id ? 'Cancelling…' : 'Cancel'}
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {!loading && filteredEnrollments.length === 0 && (
              <tr><td colSpan={10} className="px-4 py-6 text-center text-text-tertiary">
                {search ? 'No enrollments match your search.' : `No ${tab} enrollments.`}
              </td></tr>
            )}
            {loading && (
              <tr><td colSpan={10} className="px-4 py-6 text-center text-text-tertiary">Loading…</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      {!loading && enrollments.length > 0 && (
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-text-tertiary">
            Showing {filteredEnrollments.length} {tab} enrollment{filteredEnrollments.length === 1 ? '' : 's'}
            {hasMore && ` (${enrollments.length} of ${enrollmentCount} loaded overall — search covers everything, but the status tab only applies to what's loaded)`}
          </p>
          <div className="flex gap-4">
            {page > 1 && (
              <button onClick={loadLess} className="text-xs font-medium text-primary hover:underline focus-ring">
                Load less
              </button>
            )}
            {hasMore && (
              <button
                disabled={loadingMore}
                onClick={loadMore}
                className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring"
              >
                {loadingMore ? 'Loading…' : 'Load more'}
              </button>
            )}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={cancelSubstituteTarget != null}
        onClose={() => setCancelSubstituteTarget(null)}
        onConfirm={handleCancelSubstitute}
        title="Cancel substitute coverage"
        message="Cancel this substitute coverage? The original trainer resumes immediately."
        confirmLabel="Cancel coverage"
        busyLabel="Cancelling…"
        danger
        busy={cancellingSubstituteId === cancelSubstituteTarget}
      />
    </div>
  )
}
