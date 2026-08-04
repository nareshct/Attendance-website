import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { downloadFile } from '../../api/client'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { Modal } from '../../components/Modal'
import { TrendChart } from '../../components/TrendChart'
import { useAuth } from '../../hooks/useAuth'
import { useApi } from '../../hooks/useApi'
import { formatDate, formatDateRange } from '../../utils/date'

const EMPTY_CONTACT = { name: '', role: '', phone: '', email: '' }

export default function ClientDetailPage() {
  const { id } = useParams()
  const api = useApi()
  const { auth } = useAuth()
  const [downloadingId, setDownloadingId] = useState(null)
  const [client, setClient] = useState(null)
  const [students, setStudents] = useState([])
  const [invoices, setInvoices] = useState([])
  const [currentCycle, setCurrentCycle] = useState(null)
  const [history, setHistory] = useState([])
  const [courses, setCourses] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const [editingProfile, setEditingProfile] = useState(false)
  const [profileForm, setProfileForm] = useState(null)
  const [profileError, setProfileError] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)

  const [showRateForm, setShowRateForm] = useState(false)
  const [rateForm, setRateForm] = useState({ course: '', rate_per_class: '' })
  const [submitting, setSubmitting] = useState(false)
  const [deletingRateId, setDeletingRateId] = useState(null)

  const [showContactForm, setShowContactForm] = useState(false)
  const [contactForm, setContactForm] = useState(EMPTY_CONTACT)
  const [savingContact, setSavingContact] = useState(false)
  const [deletingContactId, setDeletingContactId] = useState(null)

  const loadClient = useCallback(async () => {
    setClient(await api(`/api/clients/${id}/`))
  }, [api, id])

  const loadInvoices = useCallback(() => {
    return api(`/api/client-invoices/?client=${id}`).then(setInvoices)
  }, [api, id])

  const loadCurrentCycle = useCallback(() => {
    return api(`/api/clients/${id}/earnings/`).then(setCurrentCycle)
  }, [api, id])

  const loadHistory = useCallback(() => {
    return api(`/api/clients/${id}/earnings_history/?limit=12`).then(setHistory)
  }, [api, id])

  useEffect(() => {
    loadClient().catch((err) => setError(err.message))
    api(`/api/students/?client=${id}`).then(setStudents).catch(() => {})
    api('/api/courses/').then(setCourses).catch(() => {})
    loadInvoices().catch(() => {})
    loadCurrentCycle().catch(() => {})
    loadHistory().catch(() => {})
  }, [api, id, loadClient, loadInvoices, loadCurrentCycle, loadHistory])

  async function handleDownloadInvoice(invoiceId) {
    setDownloadingId(invoiceId)
    setError('')
    try {
      await downloadFile(`/api/client-invoices/${invoiceId}/pdf/`, auth.token)
    } catch (err) {
      setError(err.message)
    } finally {
      setDownloadingId(null)
    }
  }

  async function handleMarkReceived(invoiceId) {
    setBusy(true)
    setError('')
    try {
      await api(`/api/client-invoices/${invoiceId}/mark_received/`, { method: 'POST' })
      await loadInvoices()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleAddRate(e) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await api('/api/client-rates/', {
        method: 'POST',
        body: { client: Number(id), course: Number(rateForm.course), rate_per_class: rateForm.rate_per_class },
      })
      setRateForm({ course: '', rate_per_class: '' })
      setShowRateForm(false)
      await loadClient()
      await loadCurrentCycle()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const [rateDeleteTarget, setRateDeleteTarget] = useState(null)

  async function handleDeleteRate() {
    const rateId = rateDeleteTarget
    setDeletingRateId(rateId)
    setError('')
    try {
      await api(`/api/client-rates/${rateId}/`, { method: 'DELETE' })
      setRateDeleteTarget(null)
      await loadClient()
      await loadCurrentCycle()
    } catch (err) {
      setError(err.message)
    } finally {
      setDeletingRateId(null)
    }
  }

  async function handleAddContact(e) {
    e.preventDefault()
    setSavingContact(true)
    setError('')
    try {
      await api('/api/client-contacts/', { method: 'POST', body: { client: Number(id), ...contactForm } })
      setContactForm(EMPTY_CONTACT)
      setShowContactForm(false)
      await loadClient()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingContact(false)
    }
  }

  const [contactDeleteTarget, setContactDeleteTarget] = useState(null)

  async function handleDeleteContact() {
    const contactId = contactDeleteTarget
    setDeletingContactId(contactId)
    setError('')
    try {
      await api(`/api/client-contacts/${contactId}/`, { method: 'DELETE' })
      setContactDeleteTarget(null)
      await loadClient()
    } catch (err) {
      setError(err.message)
    } finally {
      setDeletingContactId(null)
    }
  }

  function openEditProfile() {
    setProfileForm({
      company_name: client.company_name,
      contact_phone: client.contact_phone,
      contact_email: client.contact_email,
      rate_per_class: client.rate_per_class ?? '',
    })
    setProfileError('')
    setEditingProfile(true)
  }

  function closeEditProfile() {
    setEditingProfile(false)
    setProfileForm(null)
    setProfileError('')
    setShowContactForm(false)
    setContactForm(EMPTY_CONTACT)
    setShowRateForm(false)
    setRateForm({ course: '', rate_per_class: '' })
  }

  async function handleSaveProfile(e) {
    e.preventDefault()
    setSavingProfile(true)
    setProfileError('')
    try {
      await api(`/api/clients/${id}/`, { method: 'PATCH', body: profileForm })
      closeEditProfile()
      await loadClient()
      await loadCurrentCycle()
    } catch (err) {
      setProfileError(err.message)
    } finally {
      setSavingProfile(false)
    }
  }

  if (error) return <p className="text-red-600 text-sm">{error}</p>
  if (!client) return <p className="text-gray-400 text-sm">Loading…</p>

  const ratedCourseIds = new Set(client.course_rates.map((r) => r.course))
  const availableCourses = courses.filter((c) => !ratedCourseIds.has(c.id))

  return (
    <div>
      <Link to="/admin/clients" className="text-sm text-brand-blue hover:underline">&larr; Back to clients</Link>

      <div className="flex flex-wrap items-center justify-between gap-3 mt-3 mb-6">
        <h1 className="text-2xl font-semibold text-navy">{client.company_name}</h1>
        {!editingProfile && (
          <button onClick={openEditProfile} className="text-sm rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800">
            Edit details
          </button>
        )}
      </div>

      <Card className="mb-6">
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div><dt className="text-gray-500">Contact phone</dt><dd>{client.contact_phone}</dd></div>
          <div><dt className="text-gray-500">Contact email</dt><dd>{client.contact_email || '—'}</dd></div>
          <div><dt className="text-gray-500">Rate per class</dt><dd>{client.rate_per_class != null ? `₹${client.rate_per_class}` : '—'}</dd></div>
          <div><dt className="text-gray-500">Students</dt><dd>{students.length}</dd></div>
        </dl>

        {client.contacts.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <div className="text-xs text-gray-500 mb-2">Additional contacts</div>
            <ul className="space-y-1 text-sm">
              {client.contacts.map((c) => (
                <li key={c.id}>
                  {c.name}
                  {c.role && <span className="text-gray-500"> — {c.role}</span>}
                  {c.phone && <span className="text-gray-500"> · {c.phone}</span>}
                  {c.email && <span className="text-gray-500"> · {c.email}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}

        {client.course_rates.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <div className="text-xs text-gray-500 mb-2">Course-specific overrides</div>
            <ul className="space-y-1 text-sm">
              {client.course_rates.map((r) => (
                <li key={r.id}>{r.course_name} <span className="text-gray-500">· ₹{r.rate_per_class}</span></li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      <Modal open={editingProfile} onClose={closeEditProfile} title="Edit client details" maxWidthClass="max-w-2xl">
        <form onSubmit={handleSaveProfile} className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Company name</label>
            <input required value={profileForm?.company_name ?? ''} onChange={(e) => setProfileForm({ ...profileForm, company_name: e.target.value })} className="input" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Contact phone</label>
            <input required value={profileForm?.contact_phone ?? ''} onChange={(e) => setProfileForm({ ...profileForm, contact_phone: e.target.value })} className="input" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Contact email</label>
            <input value={profileForm?.contact_email ?? ''} onChange={(e) => setProfileForm({ ...profileForm, contact_email: e.target.value })} className="input" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Rate per class (₹)</label>
            <input required type="number" step="0.01" value={profileForm?.rate_per_class ?? ''} onChange={(e) => setProfileForm({ ...profileForm, rate_per_class: e.target.value })} className="input" />
          </div>
          {profileError && <p className="sm:col-span-3 text-red-600 text-xs">{profileError}</p>}
          <div className="sm:col-span-3 flex justify-end gap-3">
            <button type="button" onClick={closeEditProfile} className="text-sm text-gray-500 hover:underline">
              Cancel
            </button>
            <button disabled={savingProfile} type="submit" className="text-sm text-brand-green hover:underline disabled:opacity-60">
              {savingProfile ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>

        <div className="mt-6 pt-6 border-t border-gray-100">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-navy">Additional contacts</h3>
            <button type="button" onClick={() => setShowContactForm((v) => !v)} className="text-xs text-brand-blue hover:underline">
              {showContactForm ? 'Cancel' : '+ Add contact'}
            </button>
          </div>

          {showContactForm && (
            <form onSubmit={handleAddContact} className="grid grid-cols-1 sm:grid-cols-4 gap-3 mb-4">
              <input required placeholder="Name" value={contactForm.name} onChange={(e) => setContactForm({ ...contactForm, name: e.target.value })} className="input" />
              <input placeholder="Role (e.g. Billing)" value={contactForm.role} onChange={(e) => setContactForm({ ...contactForm, role: e.target.value })} className="input" />
              <input placeholder="Phone" value={contactForm.phone} onChange={(e) => setContactForm({ ...contactForm, phone: e.target.value })} className="input" />
              <input placeholder="Email" value={contactForm.email} onChange={(e) => setContactForm({ ...contactForm, email: e.target.value })} className="input" />
              <button disabled={savingContact} type="submit" className="sm:col-span-4 rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800 disabled:opacity-60">
                {savingContact ? 'Saving…' : 'Save contact'}
              </button>
            </form>
          )}

          {client.contacts.length > 0 ? (
            <ul className="space-y-2">
              {client.contacts.map((c) => (
                <li key={c.id} className="flex items-center justify-between text-sm">
                  <span>
                    {c.name}
                    {c.role && <span className="text-gray-500"> — {c.role}</span>}
                    {c.phone && <span className="text-gray-500"> · {c.phone}</span>}
                    {c.email && <span className="text-gray-500"> · {c.email}</span>}
                  </span>
                  <button
                    disabled={deletingContactId === c.id}
                    onClick={() => setContactDeleteTarget(c.id)}
                    className="text-xs text-red-600 hover:underline disabled:opacity-60"
                  >
                    {deletingContactId === c.id ? 'Deleting…' : 'Delete'}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400">No additional contacts yet.</p>
          )}
        </div>

        <div className="mt-6 pt-6 border-t border-gray-100">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-semibold text-navy">Course-specific overrides</h3>
            <button type="button" onClick={() => setShowRateForm((v) => !v)} className="text-xs text-brand-blue hover:underline">
              {showRateForm ? 'Cancel' : '+ Add override'}
            </button>
          </div>

          {showRateForm && (
            <form onSubmit={handleAddRate} className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
              <select required value={rateForm.course} onChange={(e) => setRateForm({ ...rateForm, course: e.target.value })} className="input">
                <option value="">Select course…</option>
                {availableCourses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <input required type="number" step="0.01" placeholder="Rate per class (₹)" value={rateForm.rate_per_class} onChange={(e) => setRateForm({ ...rateForm, rate_per_class: e.target.value })} className="input" />
              <button disabled={submitting} type="submit" className="rounded-lg bg-brand-green text-white px-4 py-2 hover:bg-green-800 disabled:opacity-60">
                {submitting ? 'Saving…' : 'Save rate'}
              </button>
            </form>
          )}

          {client.course_rates.length > 0 ? (
            <ul className="space-y-2">
              {client.course_rates.map((r) => (
                <li key={r.id} className="flex items-center justify-between text-sm">
                  <span>{r.course_name} <span className="text-gray-500">· ₹{r.rate_per_class}</span></span>
                  <button
                    disabled={deletingRateId === r.id}
                    onClick={() => setRateDeleteTarget(r.id)}
                    className="text-xs text-red-600 hover:underline disabled:opacity-60"
                  >
                    {deletingRateId === r.id ? 'Deleting…' : 'Delete'}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400">No overrides — every course uses the default rate.</p>
          )}
        </div>
      </Modal>

      {client.rate_per_class == null && (
        <p className="text-sm text-brand-amber mb-3">Set a rate per class above to calculate billing and earnings for this client.</p>
      )}
      {history.length > 1 && (
        <Card className="mb-6">
          <h2 className="text-lg font-semibold text-navy mb-3">Earnings trend</h2>
          <TrendChart
            xLabels={history.map((h) => formatDate(h.cycle_start).slice(0, 5))}
            series={[
              { label: 'Class count', color: '#2563eb', values: history.map((h) => Number(h.total_classes)) },
              { label: 'Our earning', color: '#16a34a', values: history.map((h) => Number(h.our_earning)), prefix: '₹' },
            ]}
          />
          <div className="flex justify-end gap-6 mt-3 text-sm">
            <div className="text-right">
              <div className="text-xs text-gray-500">Total class count</div>
              <div className="font-semibold text-navy">{history.reduce((sum, h) => sum + Number(h.total_classes), 0)}</div>
            </div>
            <div className="text-right">
              <div className="text-xs text-gray-500">Total earning</div>
              <div className="font-semibold text-brand-green">₹{history.reduce((sum, h) => sum + Number(h.our_earning), 0)}</div>
            </div>
          </div>
        </Card>
      )}

      <h2 className="text-lg font-semibold text-navy mb-3">Payment history</h2>
      <Card className="p-0 overflow-x-auto mb-6">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-left">
            <tr>
              <th className="px-4 py-3">Cycle</th>
              <th className="px-4 py-3">Classes</th>
              <th className="px-4 py-3">Amount</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3"></th>
              <th className="px-4 py-3"></th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {currentCycle && (
              <tr className="border-t border-gray-100 bg-gray-50/50">
                <td className="px-4 py-3">{formatDateRange(currentCycle.cycle_start, currentCycle.cycle_end)}</td>
                <td className="px-4 py-3">{currentCycle.current_classes}</td>
                <td className="px-4 py-3">
                  ₹{currentCycle.current_cycle_billed}
                  {currentCycle.carried_forward_count > 0 && (
                    <div className="text-xs text-brand-amber">
                      incl. ₹{currentCycle.carried_forward_amount} from {currentCycle.carried_forward_count} late-approved class{currentCycle.carried_forward_count === 1 ? '' : 'es'}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3"><Badge status="open" /></td>
                <td className="px-4 py-3"></td>
                <td className="px-4 py-3"></td>
                <td className="px-4 py-3"></td>
              </tr>
            )}
            {invoices.map((inv) => (
              <tr key={inv.id} className="border-t border-gray-100">
                <td className="px-4 py-3">{formatDateRange(inv.cycle_start, inv.cycle_end)}</td>
                <td className="px-4 py-3">{inv.total_classes}</td>
                <td className="px-4 py-3">
                  ₹{inv.total_amount}
                  {Number(inv.carried_forward_amount) > 0 && (
                    <div className="text-xs text-gray-400">(incl. ₹{inv.carried_forward_amount} carried forward)</div>
                  )}
                </td>
                <td className="px-4 py-3">
                  <Badge status={inv.is_overdue ? 'overdue' : inv.status} />
                </td>
                <td className="px-4 py-3 text-red-600">
                  {inv.is_overdue && `${inv.days_overdue}d overdue`}
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    disabled={downloadingId === inv.id}
                    onClick={() => handleDownloadInvoice(inv.id)}
                    className="text-xs text-gray-500 hover:text-brand-blue disabled:opacity-60"
                  >
                    {downloadingId === inv.id ? 'Downloading…' : 'Download PDF'}
                  </button>
                </td>
                <td className="px-4 py-3 text-right">
                  {inv.status === 'pending' && (
                    <button disabled={busy} onClick={() => handleMarkReceived(inv.id)} className="text-xs text-brand-blue hover:underline disabled:opacity-60">
                      Mark as received
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {invoices.length === 0 && !currentCycle && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-gray-400">No closed billing cycles for this client yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <h2 className="text-lg font-semibold text-navy mb-3">Students</h2>
      <Card className="p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-left">
            <tr>
              <th className="px-4 py-3">#</th>
              <th className="px-4 py-3">Student ID</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Grade</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {students.map((s, i) => (
              <tr key={s.id} className="border-t border-gray-100">
                <td className="px-4 py-3 text-gray-400">{i + 1}</td>
                <td className="px-4 py-3 font-mono text-xs">{s.student_id}</td>
                <td className="px-4 py-3">
                  <Link
                    to={`/admin/students/${s.id}`}
                    state={{ from: `/admin/clients/${id}`, fromLabel: `Back to ${client.company_name}` }}
                    className="text-brand-blue hover:underline"
                  >
                    {s.name}
                  </Link>
                </td>
                <td className="px-4 py-3">Std {s.grade}</td>
                <td className="px-4 py-3"><Badge status={s.status} /></td>
              </tr>
            ))}
            {students.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-gray-400">No students for this client yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <ConfirmDialog
        open={contactDeleteTarget != null}
        onClose={() => setContactDeleteTarget(null)}
        onConfirm={handleDeleteContact}
        title="Delete contact"
        message="Delete this contact?"
        confirmLabel="Delete"
        busyLabel="Deleting…"
        danger
        busy={deletingContactId === contactDeleteTarget}
      />

      <ConfirmDialog
        open={rateDeleteTarget != null}
        onClose={() => setRateDeleteTarget(null)}
        onConfirm={handleDeleteRate}
        title="Delete rate override"
        message="Delete this course rate override? This client will fall back to their default rate for that course."
        confirmLabel="Delete"
        busyLabel="Deleting…"
        danger
        busy={deletingRateId === rateDeleteTarget}
      />
    </div>
  )
}
