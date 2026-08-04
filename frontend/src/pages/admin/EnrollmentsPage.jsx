import { useCallback, useEffect, useState } from 'react'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { Modal } from '../../components/Modal'
import { SearchableSelect } from '../../components/SearchableSelect'
import { useApi } from '../../hooks/useApi'
import { usePaginatedList } from '../../hooks/usePaginatedList'
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
  const [students, setStudents] = useState([])
  const [courses, setCourses] = useState([])
  const [trainers, setTrainers] = useState([])
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
    api('/api/students/').then((s) => setStudents(s.filter((x) => x.status === 'active'))).catch(() => {})
    api('/api/courses/').then(setCourses).catch(() => {})
    api('/api/trainers/').then((t) => setTrainers(t.filter((x) => x.status === 'active'))).catch(() => {})
    loadSubstituteAssignments().catch(() => {})
  }, [api, loadSubstituteAssignments])

  function toggleDay(code) {
    setForm((f) => ({
      ...f,
      class_days: f.class_days.includes(code) ? f.class_days.filter((d) => d !== code) : [...f.class_days, code],
    }))
  }

  const selectedStudent = students.find((s) => String(s.id) === form.student)
  const selectedCourse = courses.find((c) => String(c.id) === form.course)
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

    const selectedTrainer = trainers.find((t) => String(t.id) === form.trainer)
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
          ...(selectedStudent?.source_type === 'B2C' ? {
            payment_type: form.payment_type,
            discount_percent: form.discount_percent || '0',
          } : {}),
        },
      })
      setForm(EMPTY_FORM)
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
        <button onClick={() => setShowForm(true)} className="text-sm rounded-lg bg-brand-blue text-white px-4 py-2 hover:bg-blue-800">
          + New enrollment
        </button>
      </div>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <Modal open={showForm} onClose={() => setShowForm(false)} title="New enrollment" maxWidthClass="max-w-2xl">
        <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <SearchableSelect
              required
              placeholder="Search student…"
              value={form.student}
              onChange={(v) => setForm({ ...form, student: v, payment_type: '', discount_percent: '0' })}
              options={students.map((s) => ({ value: s.id, label: `${s.name} (${s.student_id})` }))}
            />
            <SearchableSelect
              required
              placeholder="Search course…"
              value={form.course}
              onChange={(v) => setForm({ ...form, course: v })}
              options={courses.map((c) => ({ value: c.id, label: c.name }))}
            />
            <SearchableSelect
              required
              placeholder="Search trainer…"
              value={form.trainer}
              onChange={(v) => setForm({ ...form, trainer: v })}
              options={trainers.map((t) => ({ value: t.id, label: t.name }))}
            />
            <input
              required
              type="time"
              value={form.class_time}
              onChange={(e) => setForm({ ...form, class_time: e.target.value })}
              className="input"
            />
            <div>
              <label className="block text-xs text-gray-500 mb-1">Batch count (total classes)</label>
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
            <div className="sm:col-span-2">
              <p className="text-sm text-gray-500 mb-1">Class days</p>
              <div className="flex flex-wrap gap-2">
                {DAY_OPTIONS.map((d) => (
                  <button
                    key={d.code}
                    type="button"
                    onClick={() => toggleDay(d.code)}
                    className={`px-3 py-1.5 rounded-lg text-sm border ${
                      form.class_days.includes(d.code)
                        ? 'bg-brand-blue text-white border-brand-blue'
                        : 'bg-white text-gray-600 border-gray-200 hover:border-brand-blue'
                    }`}
                  >
                    {d.label}
                  </button>
                ))}
              </div>
            </div>
            {selectedStudent?.source_type === 'B2C' && (
              <>
                <p className="sm:col-span-2 text-xs text-gray-400 -mb-1">Payment plan</p>
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
                <div className="input bg-gray-50 text-gray-600 flex items-center justify-between">
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
                    <p className="text-xs text-gray-400 mt-1">
                      Standard total ₹{standardTotal} → after {discountPercent || 0}% off: ₹{discountedTotal} (max 15% discount)
                    </p>
                  )}
                </div>
                <div className="input bg-gray-50 text-gray-600 flex items-center justify-between">
                  <span>Due before class 1</span>
                  <span className="font-medium text-navy">
                    {upfrontPreview != null ? `₹${upfrontPreview}` : '—'}
                  </span>
                </div>
                {form.payment_type && (
                  <p className="sm:col-span-2 text-xs text-gray-400 -mt-2">
                    Upfront amount = {upfrontMilestone} classes × this plan's effective rate (discounted total ÷ total
                    classes), rounded to the nearest rupee.
                  </p>
                )}
              </>
            )}
            {nextBatchNumber && (
              <p className="sm:col-span-2 text-sm text-gray-500">
                This will be created as <strong>Batch {nextBatchNumber}</strong> for this student + course.
              </p>
            )}
            {duplicateOngoingEnrollment && (
              <p className="sm:col-span-2 text-sm text-brand-amber">
                Heads up — {duplicateOngoingEnrollment.student_name} already has an ongoing enrollment in this course
                (Batch {duplicateOngoingEnrollment.batch_number}, with {duplicateOngoingEnrollment.trainer_name}). If
                this is a mistake (e.g. a double submit), cancel and check the Enrollments list first.
              </p>
            )}
            {error && <p className="sm:col-span-2 text-red-600 text-xs">{error}</p>}
            <div className="sm:col-span-2 flex justify-end gap-3">
              <button type="button" onClick={() => setShowForm(false)} className="text-sm text-gray-500 hover:underline">
                Cancel
              </button>
              <button disabled={submitting} type="submit" className="rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800 disabled:opacity-60">
                {submitting ? 'Saving…' : 'Create enrollment'}
              </button>
            </div>
        </form>
      </Modal>

      <Modal open={editId != null} onClose={closeEditSchedule} title="Edit schedule">
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Course</label>
            {editingEnrollment?.classes_completed === 0 ? (
              <SearchableSelect
                placeholder="Search course…"
                value={editCourse}
                onChange={setEditCourse}
                options={courses.map((c) => ({ value: c.id, label: c.name }))}
              />
            ) : (
              <p className="text-sm text-gray-500">
                {editingEnrollment?.course_name} <span className="text-xs text-gray-400">— can't be changed once classes have started.</span>
              </p>
            )}
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Class time</label>
            <input type="time" value={editClassTime} onChange={(ev) => setEditClassTime(ev.target.value)} className="input" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Batch count (total classes)</label>
            <input
              type="number"
              min={editingEnrollment?.classes_completed || 1}
              value={editClassesTotal}
              onChange={(ev) => setEditClassesTotal(ev.target.value)}
              className="input"
            />
            {editingEnrollment?.classes_completed > 0 && (
              <p className="text-xs text-gray-400 mt-1">
                Can't be less than the {editingEnrollment.classes_completed} classes already completed.
              </p>
            )}
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Class days</label>
            <div className="flex flex-wrap gap-2">
              {DAY_OPTIONS.map((d) => (
                <button
                  key={d.code}
                  type="button"
                  onClick={() => toggleEditDay(d.code)}
                  className={`px-3 py-1.5 rounded-lg text-sm border ${
                    editClassDays.includes(d.code)
                      ? 'bg-brand-blue text-white border-brand-blue'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-brand-blue'
                  }`}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>
          {editError && <p className="text-red-600 text-xs">{editError}</p>}
          <div className="flex justify-end gap-3">
            <button type="button" onClick={closeEditSchedule} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button
              disabled={editSaving}
              onClick={() => handleEditSchedule(editId)}
              className="text-sm text-brand-green hover:underline disabled:opacity-60"
            >
              {editSaving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </Modal>

      <Modal open={transferId != null} onClose={closeTransfer} title="Transfer enrollment">
        <div className="space-y-3">
          <p className="text-sm text-gray-500">
            Move <strong>{transferEnrollment?.student_name}</strong>'s {transferEnrollment?.course_name} enrollment to a different trainer.
          </p>
          <SearchableSelect
            placeholder="Search trainer…"
            value={transferTrainer}
            onChange={setTransferTrainer}
            options={trainers.filter((t) => t.id !== transferEnrollment?.trainer).map((t) => ({ value: t.id, label: t.name }))}
          />
          {transferError && <p className="text-red-600 text-xs">{transferError}</p>}
          <div className="flex justify-end gap-3">
            <button type="button" onClick={closeTransfer} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button
              disabled={!transferTrainer || transferring}
              onClick={() => handleTransfer(transferId)}
              className="text-sm text-brand-green hover:underline disabled:opacity-60"
            >
              {transferring ? 'Transferring…' : 'Confirm'}
            </button>
          </div>
        </div>
      </Modal>

      <Modal open={substituteId != null} onClose={closeSubstitute} title="Assign substitute">
        <div className="space-y-3">
          <p className="text-sm text-gray-500">
            Temporary coverage for <strong>{substituteEnrollment?.student_name}</strong>'s {substituteEnrollment?.course_name} classes.
          </p>
          <SearchableSelect
            placeholder="Search substitute trainer…"
            value={substituteTrainer}
            onChange={setSubstituteTrainer}
            options={trainers.filter((t) => t.id !== substituteEnrollment?.trainer).map((t) => ({ value: t.id, label: t.name }))}
          />
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Start date</label>
              <input type="date" value={substituteStart} onChange={(ev) => setSubstituteStart(ev.target.value)} className="input" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">End date</label>
              <input type="date" value={substituteEnd} onChange={(ev) => setSubstituteEnd(ev.target.value)} className="input" />
            </div>
          </div>
          {substituteError && <p className="text-red-600 text-xs">{substituteError}</p>}
          <div className="flex justify-end gap-3">
            <button type="button" onClick={closeSubstitute} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button
              disabled={!substituteTrainer || !substituteStart || !substituteEnd || assigningSubstitute}
              onClick={() => handleAssignSubstitute(substituteId)}
              className="text-sm text-brand-green hover:underline disabled:opacity-60"
            >
              {assigningSubstitute ? 'Assigning…' : 'Confirm'}
            </button>
          </div>
        </div>
      </Modal>

      <Modal open={withdrawId != null} onClose={closeWithdraw} title="Withdraw enrollment">
        <div className="space-y-3">
          <p className="text-sm text-gray-500">
            Withdraw <strong>{withdrawEnrollment?.student_name}</strong> from {withdrawEnrollment?.course_name}.
          </p>
          {students.find((s) => s.id === withdrawEnrollment?.student)?.source_type === 'B2C' && (
            <>
              <input
                type="number"
                step="0.01"
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
          <p className="text-xs text-gray-400">
            Any pending installments will be cancelled. Classes already taught stay on record.
          </p>
          {withdrawError && <p className="text-red-600 text-xs">{withdrawError}</p>}
          <div className="flex justify-end gap-3">
            <button type="button" onClick={closeWithdraw} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button
              disabled={withdrawing}
              onClick={() => handleWithdraw(withdrawId)}
              className="text-sm text-red-600 hover:underline disabled:opacity-60"
            >
              {withdrawing ? 'Withdrawing…' : 'Confirm withdrawal'}
            </button>
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
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`text-sm rounded-lg px-4 py-2 capitalize ${
                tab === t ? 'bg-brand-blue text-white' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <Card className="p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-left">
            <tr>
              <th className="px-4 py-3">#</th>
              <th className="px-4 py-3">Student</th>
              <th className="px-4 py-3">Course</th>
              <th className="px-4 py-3">Trainer</th>
              <th className="px-4 py-3">Schedule</th>
              <th className="px-4 py-3">Batch</th>
              <th className="px-4 py-3">Progress</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Enrolled</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {filteredEnrollments.map((e, i) => (
              <tr key={e.id} className="border-t border-gray-100">
                <td className="px-4 py-3 text-gray-400">{i + 1}</td>
                <td className="px-4 py-3">{e.student_name}</td>
                <td className="px-4 py-3">{e.course_name}</td>
                <td className="px-4 py-3">{e.trainer_name}</td>
                <td className="px-4 py-3 text-gray-500">
                  {formatDays(e.class_days)}{e.class_time && ` · ${formatTime(e.class_time)}`}
                </td>
                <td className="px-4 py-3">{e.batch_number}</td>
                <td className="px-4 py-3">{e.classes_completed}/{e.classes_total}</td>
                <td className="px-4 py-3"><Badge status={e.status} /></td>
                <td className="px-4 py-3">{formatDate(e.start_date)}</td>
                <td className="px-4 py-3 text-right">
                  {(e.status === 'ongoing' || e.status === 'completed') && (
                    <div className="space-y-1">
                      <div className="flex flex-wrap justify-end gap-x-3 gap-y-1">
                        <button onClick={() => openEditSchedule(e)} className="text-brand-blue hover:underline whitespace-nowrap">
                          Edit
                        </button>
                        {e.status === 'ongoing' && (
                          <>
                            <button onClick={() => openTransfer(e.id)} className="text-brand-blue hover:underline whitespace-nowrap">
                              Transfer
                            </button>
                            <button onClick={() => openSubstitute(e.id)} className="text-brand-blue hover:underline whitespace-nowrap">
                              Substitute
                            </button>
                            <button onClick={() => openWithdraw(e.id)} className="text-red-600 hover:underline whitespace-nowrap">
                              Withdraw
                            </button>
                          </>
                        )}
                      </div>
                      {e.status === 'ongoing' && substituteAssignments.filter((sa) => sa.enrollment === e.id).map((sa) => (
                        <div key={sa.id} className="text-xs text-gray-400">
                          {sa.substitute_trainer_name} covering {formatDateRange(sa.start_date, sa.end_date)}
                          {' · '}
                          <button
                            disabled={cancellingSubstituteId === sa.id}
                            onClick={() => setCancelSubstituteTarget(sa.id)}
                            className="text-red-600 hover:underline disabled:opacity-60"
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
              <tr><td colSpan={10} className="px-4 py-6 text-center text-gray-400">
                {search ? 'No enrollments match your search.' : `No ${tab} enrollments.`}
              </td></tr>
            )}
            {loading && (
              <tr><td colSpan={10} className="px-4 py-6 text-center text-gray-400">Loading…</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      {!loading && enrollments.length > 0 && (
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-gray-400">
            Showing {filteredEnrollments.length} {tab} enrollment{filteredEnrollments.length === 1 ? '' : 's'}
            {hasMore && ` (${enrollments.length} of ${enrollmentCount} loaded overall — search covers everything, but the status tab only applies to what's loaded)`}
          </p>
          <div className="flex gap-4">
            {page > 1 && (
              <button onClick={loadLess} className="text-xs text-brand-blue hover:underline">
                Load less
              </button>
            )}
            {hasMore && (
              <button
                disabled={loadingMore}
                onClick={loadMore}
                className="text-xs text-brand-blue hover:underline disabled:opacity-60"
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
