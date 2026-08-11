import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiUpload, downloadFile } from '../../api/client'
import { ActiveStudentsModal } from '../../components/ActiveStudentsModal'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
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
  const [enrollments, setEnrollments] = useState([])
  const [showActiveStudents, setShowActiveStudents] = useState(false)
  const [invoices, setInvoices] = useState([])
  const [currentCycle, setCurrentCycle] = useState(null)
  const [history, setHistory] = useState([])
  const [courses, setCourses] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const [editingProfile, setEditingProfile] = useState(false)
  const [profileForm, setProfileForm] = useState(null)
  const [logoFile, setLogoFile] = useState(null)
  const [profileError, setProfileError] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)

  const [showRateForm, setShowRateForm] = useState(false)
  const [rateForm, setRateForm] = useState({ course: '', rate_per_class: '' })
  const [submitting, setSubmitting] = useState(false)
  const [deletingRateId, setDeletingRateId] = useState(null)
  const [rateError, setRateError] = useState('')

  const [showContactForm, setShowContactForm] = useState(false)
  const [contactForm, setContactForm] = useState(EMPTY_CONTACT)
  const [savingContact, setSavingContact] = useState(false)
  const [deletingContactId, setDeletingContactId] = useState(null)
  const [contactError, setContactError] = useState('')
  const [editingContactId, setEditingContactId] = useState(null)

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
    api(`/api/enrollments/?client=${id}`).then(setEnrollments).catch(() => {})
    api('/api/courses/').then(setCourses).catch(() => {})
    loadInvoices().catch((err) => setError(err.message))
    loadCurrentCycle().catch((err) => setError(err.message))
    loadHistory().catch((err) => setError(err.message))
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
    setRateError('')
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
      setRateError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const [rateDeleteTarget, setRateDeleteTarget] = useState(null)

  async function handleDeleteRate() {
    const rateId = rateDeleteTarget
    setDeletingRateId(rateId)
    setRateError('')
    try {
      await api(`/api/client-rates/${rateId}/`, { method: 'DELETE' })
      setRateDeleteTarget(null)
      await loadClient()
      await loadCurrentCycle()
    } catch (err) {
      setRateError(err.message)
    } finally {
      setDeletingRateId(null)
    }
  }

  const [editingRateId, setEditingRateId] = useState(null)
  const [editingRateAmount, setEditingRateAmount] = useState('')

  function openEditRate(rate) {
    setEditingRateId(rate.id)
    setEditingRateAmount(rate.rate_per_class)
    setRateError('')
  }

  async function handleSaveRateEdit(rateId) {
    setSubmitting(true)
    setRateError('')
    try {
      await api(`/api/client-rates/${rateId}/`, { method: 'PATCH', body: { rate_per_class: editingRateAmount } })
      setEditingRateId(null)
      await loadClient()
      await loadCurrentCycle()
    } catch (err) {
      setRateError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  function openEditContact(contact) {
    setContactForm({ name: contact.name, role: contact.role, phone: contact.phone, email: contact.email })
    setEditingContactId(contact.id)
    setContactError('')
    setShowContactForm(true)
  }

  async function handleAddContact(e) {
    e.preventDefault()
    setSavingContact(true)
    setContactError('')
    try {
      if (editingContactId) {
        await api(`/api/client-contacts/${editingContactId}/`, { method: 'PATCH', body: contactForm })
      } else {
        await api('/api/client-contacts/', { method: 'POST', body: { client: Number(id), ...contactForm } })
      }
      setContactForm(EMPTY_CONTACT)
      setEditingContactId(null)
      setShowContactForm(false)
      await loadClient()
    } catch (err) {
      setContactError(err.message)
    } finally {
      setSavingContact(false)
    }
  }

  const [contactDeleteTarget, setContactDeleteTarget] = useState(null)

  async function handleDeleteContact() {
    const contactId = contactDeleteTarget
    setDeletingContactId(contactId)
    setContactError('')
    try {
      await api(`/api/client-contacts/${contactId}/`, { method: 'DELETE' })
      setContactDeleteTarget(null)
      await loadClient()
    } catch (err) {
      setContactError(err.message)
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
      tagline: client.tagline ?? '',
    })
    setLogoFile(null)
    setProfileError('')
    setContactError('')
    setRateError('')
    setEditingProfile(true)
  }

  function closeEditProfile() {
    setEditingProfile(false)
    setProfileForm(null)
    setLogoFile(null)
    setProfileError('')
    setShowContactForm(false)
    setContactForm(EMPTY_CONTACT)
    setContactError('')
    setEditingContactId(null)
    setShowRateForm(false)
    setRateForm({ course: '', rate_per_class: '' })
    setRateError('')
    setEditingRateId(null)
  }

  async function handleSaveProfile(e) {
    e.preventDefault()
    setSavingProfile(true)
    setProfileError('')
    try {
      const data = new FormData()
      Object.entries(profileForm).forEach(([key, value]) => data.append(key, value))
      if (logoFile) data.append('logo', logoFile)
      await apiUpload(`/api/clients/${id}/`, data, auth.token, 'PATCH')
      closeEditProfile()
      await loadClient()
      await loadCurrentCycle()
    } catch (err) {
      setProfileError(err.message)
    } finally {
      setSavingProfile(false)
    }
  }

  if (error && !client) return <p className="text-error text-sm">{error}</p>
  if (!client) return <p className="text-text-tertiary text-sm">Loading…</p>

  const ratedCourseIds = new Set(client.course_rates.map((r) => r.course))
  const availableCourses = courses.filter((c) => !ratedCourseIds.has(c.id))
  const ongoingEnrollments = enrollments.filter((e) => e.status === 'ongoing')

  return (
    <div>
      <Link to="/admin/clients" className="text-sm font-medium text-primary hover:underline focus-ring">&larr; Back to clients</Link>

      <div className="flex flex-wrap items-center justify-between gap-3 mt-3 mb-6">
        <div className="flex items-center gap-3">
          {client.logo && <img src={client.logo} alt="" className="w-10 h-10 rounded-lg object-contain bg-white border border-gray-200" />}
          <div>
            <h1 className="text-2xl font-semibold text-navy">{client.company_name}</h1>
            {client.tagline && <p className="text-xs text-text-secondary">{client.tagline}</p>}
          </div>
        </div>
        {!editingProfile && <Button variant="success" onClick={openEditProfile}>Edit details</Button>}
      </div>

      {error && <p className="text-error text-sm mb-4">{error}</p>}

      <Card className="mb-6">
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div><dt className="text-text-secondary">Contact phone</dt><dd>{client.contact_phone}</dd></div>
          <div><dt className="text-text-secondary">Contact email</dt><dd>{client.contact_email || '—'}</dd></div>
          <div><dt className="text-text-secondary">Rate per class</dt><dd>{client.rate_per_class != null ? `₹${client.rate_per_class}` : '—'}</dd></div>
          <div>
            <dt className="text-text-secondary">Active students</dt>
            <dd className="flex items-center gap-2">
              <span>{ongoingEnrollments.length}</span>
              {ongoingEnrollments.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowActiveStudents(true)}
                  className="text-xs font-medium text-primary hover:underline focus-ring"
                >
                  Details
                </button>
              )}
            </dd>
          </div>
        </dl>

        {client.contacts.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <div className="text-xs text-text-secondary mb-2">Additional contacts</div>
            <ul className="space-y-1 text-sm">
              {client.contacts.map((c) => (
                <li key={c.id}>
                  {c.name}
                  {c.role && <span className="text-text-secondary"> — {c.role}</span>}
                  {c.phone && <span className="text-text-secondary"> · {c.phone}</span>}
                  {c.email && <span className="text-text-secondary"> · {c.email}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}

        {client.course_rates.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <div className="text-xs text-text-secondary mb-2">Course-specific overrides</div>
            <ul className="space-y-1 text-sm">
              {client.course_rates.map((r) => (
                <li key={r.id}>{r.course_name} <span className="text-text-secondary">· ₹{r.rate_per_class}</span></li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      <Modal open={editingProfile} onClose={closeEditProfile} title="Edit client details" maxWidthClass="max-w-2xl">
        <form onSubmit={handleSaveProfile} className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-text-secondary mb-1">Company name</label>
            <input required value={profileForm?.company_name ?? ''} onChange={(e) => setProfileForm({ ...profileForm, company_name: e.target.value })} className="input" />
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">Contact phone</label>
            <input required value={profileForm?.contact_phone ?? ''} onChange={(e) => setProfileForm({ ...profileForm, contact_phone: e.target.value })} className="input" />
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">Contact email</label>
            <input value={profileForm?.contact_email ?? ''} onChange={(e) => setProfileForm({ ...profileForm, contact_email: e.target.value })} className="input" />
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">Rate per class (₹)</label>
            <input required type="number" step="0.01" min="0" value={profileForm?.rate_per_class ?? ''} onChange={(e) => setProfileForm({ ...profileForm, rate_per_class: e.target.value })} className="input" />
          </div>
          <div className="sm:col-span-2">
            <label className="block text-xs text-text-secondary mb-1">Tagline</label>
            <input placeholder="e.g. Excellence in Coding Education" value={profileForm?.tagline ?? ''} onChange={(e) => setProfileForm({ ...profileForm, tagline: e.target.value })} className="input" />
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">Logo</label>
            <div className="flex items-center gap-2">
              {client.logo && !logoFile && <img src={client.logo} alt="" className="w-9 h-9 rounded-lg object-contain bg-white border border-gray-200" />}
              <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => setLogoFile(e.target.files[0] || null)} className="input" />
            </div>
          </div>
          {profileError && <p className="sm:col-span-3 text-error text-xs">{profileError}</p>}
          <div className="sm:col-span-3 flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={closeEditProfile}>
              Cancel
            </Button>
            <Button type="submit" variant="success" disabled={savingProfile}>
              {savingProfile ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </form>

        <div className="mt-6 pt-6 border-t border-gray-100">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-navy">Additional contacts</h3>
            <button
              type="button"
              onClick={() => {
                setShowContactForm((v) => !v)
                setContactForm(EMPTY_CONTACT)
                setEditingContactId(null)
                setContactError('')
              }}
              className="text-xs font-medium text-primary hover:underline focus-ring"
            >
              {showContactForm ? 'Cancel' : '+ Add contact'}
            </button>
          </div>

          {showContactForm && (
            <form onSubmit={handleAddContact} className="grid grid-cols-1 sm:grid-cols-4 gap-3 mb-4">
              <input required placeholder="Name" value={contactForm.name} onChange={(e) => setContactForm({ ...contactForm, name: e.target.value })} className="input" />
              <input placeholder="Role (e.g. Billing)" value={contactForm.role} onChange={(e) => setContactForm({ ...contactForm, role: e.target.value })} className="input" />
              <input placeholder="Phone" value={contactForm.phone} onChange={(e) => setContactForm({ ...contactForm, phone: e.target.value })} className="input" />
              <input placeholder="Email" value={contactForm.email} onChange={(e) => setContactForm({ ...contactForm, email: e.target.value })} className="input" />
              {contactError && <p className="sm:col-span-4 text-error text-xs">{contactError}</p>}
              <Button disabled={savingContact} type="submit" variant="success" className="sm:col-span-4">
                {savingContact ? 'Saving…' : editingContactId ? 'Update contact' : 'Save contact'}
              </Button>
            </form>
          )}

          {client.contacts.length > 0 ? (
            <ul className="space-y-2">
              {client.contacts.map((c) => (
                <li key={c.id} className="flex items-center justify-between text-sm">
                  <span>
                    {c.name}
                    {c.role && <span className="text-text-secondary"> — {c.role}</span>}
                    {c.phone && <span className="text-text-secondary"> · {c.phone}</span>}
                    {c.email && <span className="text-text-secondary"> · {c.email}</span>}
                  </span>
                  <span className="space-x-3">
                    <button onClick={() => openEditContact(c)} className="text-xs font-medium text-primary hover:underline focus-ring">
                      Edit
                    </button>
                    <button
                      disabled={deletingContactId === c.id}
                      onClick={() => {
                        setContactDeleteTarget(c.id)
                        setContactError('')
                      }}
                      className="text-xs font-medium text-error hover:underline disabled:opacity-60 focus-ring"
                    >
                      {deletingContactId === c.id ? 'Deleting…' : 'Delete'}
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-text-tertiary">No additional contacts yet.</p>
          )}
        </div>

        <div className="mt-6 pt-6 border-t border-gray-100">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-semibold text-navy">Course-specific overrides</h3>
            <button
              type="button"
              onClick={() => {
                setShowRateForm((v) => !v)
                setRateError('')
              }}
              className="text-xs font-medium text-primary hover:underline focus-ring"
            >
              {showRateForm ? 'Cancel' : '+ Add override'}
            </button>
          </div>

          {showRateForm && (
            <form onSubmit={handleAddRate} className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
              <select required value={rateForm.course} onChange={(e) => setRateForm({ ...rateForm, course: e.target.value })} className="input">
                <option value="">Select course…</option>
                {availableCourses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <input required type="number" step="0.01" min="0" placeholder="Rate per class (₹)" value={rateForm.rate_per_class} onChange={(e) => setRateForm({ ...rateForm, rate_per_class: e.target.value })} className="input" />
              <Button disabled={submitting} type="submit" variant="success">
                {submitting ? 'Saving…' : 'Save rate'}
              </Button>
              {rateError && <p className="sm:col-span-3 text-error text-xs">{rateError}</p>}
            </form>
          )}

          {client.course_rates.length > 0 ? (
            <ul className="space-y-2">
              {client.course_rates.map((r) => (
                <li key={r.id} className="flex items-center justify-between text-sm">
                  <span>{r.course_name} <span className="text-text-secondary">· ₹{r.rate_per_class}</span></span>
                  <span className="space-x-3">
                    <button onClick={() => openEditRate(r)} className="text-xs font-medium text-primary hover:underline focus-ring">
                      Edit
                    </button>
                    <button
                      disabled={deletingRateId === r.id}
                      onClick={() => {
                        setRateDeleteTarget(r.id)
                        setRateError('')
                      }}
                      className="text-xs font-medium text-error hover:underline disabled:opacity-60 focus-ring"
                    >
                      {deletingRateId === r.id ? 'Deleting…' : 'Delete'}
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-text-tertiary">No overrides — every course uses the default rate.</p>
          )}
        </div>
      </Modal>

      <Modal open={editingRateId != null} onClose={() => setEditingRateId(null)} title="Edit rate override">
        {(() => {
          const target = client.course_rates.find((r) => r.id === editingRateId)
          if (!target) return null
          return (
            <div className="space-y-3">
              <p className="text-sm text-text-secondary">{target.course_name}</p>
              <input
                type="number"
                step="0.01"
                min="0"
                autoFocus
                value={editingRateAmount}
                onChange={(e) => setEditingRateAmount(e.target.value)}
                className="input"
              />
              {rateError && <p className="text-error text-xs">{rateError}</p>}
              <div className="flex justify-end gap-3">
                <Button type="button" variant="ghost" onClick={() => setEditingRateId(null)}>
                  Cancel
                </Button>
                <Button type="button" variant="success" disabled={submitting} onClick={() => handleSaveRateEdit(target.id)}>
                  {submitting ? 'Saving…' : 'Save'}
                </Button>
              </div>
            </div>
          )
        })()}
      </Modal>

      {client.rate_per_class == null && (
        <p className="text-sm text-warning mb-3">Set a rate per class above to calculate billing and earnings for this client.</p>
      )}
      {history.length > 1 && (
        <Card className="mb-6">
          <h2 className="text-lg font-semibold text-navy mb-3">Earnings trend</h2>
          <TrendChart
            xLabels={history.map((h) => formatDate(h.cycle_start).slice(0, 5))}
            series={[
              { label: 'Class count', color: '#4338CA', values: history.map((h) => Number(h.total_classes)) },
              { label: 'Our earning', color: '#176B41', values: history.map((h) => Number(h.our_earning)), prefix: '₹' },
            ]}
          />
          <div className="flex justify-end gap-6 mt-3 text-sm">
            <div className="text-right">
              <div className="text-xs text-text-secondary">Total class count</div>
              <div className="font-semibold text-navy tabular-nums">{history.reduce((sum, h) => sum + Number(h.total_classes), 0)}</div>
            </div>
            <div className="text-right">
              <div className="text-xs text-text-secondary">Total earning</div>
              <div className="font-semibold text-success tabular-nums">₹{history.reduce((sum, h) => sum + Number(h.our_earning), 0)}</div>
            </div>
          </div>
        </Card>
      )}

      <h2 className="text-lg font-semibold text-navy mb-3">Payment history</h2>
      <Card className="p-0 overflow-x-auto mb-6">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">Cycle</th>
              <th className="table-head-cell">Classes</th>
              <th className="table-head-cell">Amount</th>
              <th className="table-head-cell">Status</th>
              <th className="table-head-cell"></th>
              <th className="table-head-cell"></th>
              <th className="table-head-cell"></th>
            </tr>
          </thead>
          <tbody>
            {currentCycle && (
              <tr className="table-row bg-warning-tint/50">
                <td className="table-cell">{formatDateRange(currentCycle.cycle_start, currentCycle.cycle_end)}</td>
                <td className="table-cell tabular-nums">{currentCycle.current_classes}</td>
                <td className="table-cell tabular-nums">
                  ₹{currentCycle.current_cycle_billed}
                  {currentCycle.carried_forward_count > 0 && (
                    <div className="text-xs text-warning">
                      incl. ₹{currentCycle.carried_forward_amount} from {currentCycle.carried_forward_count} late-approved class{currentCycle.carried_forward_count === 1 ? '' : 'es'}
                    </div>
                  )}
                </td>
                <td className="table-cell"><Badge status="open" /></td>
                <td className="table-cell"></td>
                <td className="table-cell"></td>
                <td className="table-cell"></td>
              </tr>
            )}
            {invoices.map((inv) => (
              <tr key={inv.id} className="table-row">
                <td className="table-cell">{formatDateRange(inv.cycle_start, inv.cycle_end)}</td>
                <td className="table-cell tabular-nums">{inv.total_classes}</td>
                <td className="table-cell tabular-nums">
                  ₹{inv.total_amount}
                  {Number(inv.carried_forward_amount) > 0 && (
                    <div className="text-xs text-text-tertiary">(incl. ₹{inv.carried_forward_amount} carried forward)</div>
                  )}
                </td>
                <td className="table-cell">
                  <Badge status={inv.is_overdue ? 'overdue' : inv.status} />
                </td>
                <td className="table-cell text-error">
                  {inv.is_overdue && `${inv.days_overdue}d overdue`}
                </td>
                <td className="table-cell text-right">
                  <button
                    disabled={downloadingId === inv.id}
                    onClick={() => handleDownloadInvoice(inv.id)}
                    className="text-xs font-medium text-text-secondary hover:text-primary disabled:opacity-60 focus-ring"
                  >
                    {downloadingId === inv.id ? 'Downloading…' : 'Download PDF'}
                  </button>
                </td>
                <td className="table-cell text-right">
                  {inv.status === 'pending' && (
                    <button disabled={busy} onClick={() => handleMarkReceived(inv.id)} className="text-xs font-medium text-primary hover:underline disabled:opacity-60 focus-ring">
                      Mark as received
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {invoices.length === 0 && !currentCycle && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-text-tertiary">No closed billing cycles for this client yet.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <h2 className="text-lg font-semibold text-navy mb-3">Students</h2>
      <Card className="p-0 overflow-x-auto">
        <table className="table">
          <thead className="table-head-row">
            <tr>
              <th className="table-head-cell">#</th>
              <th className="table-head-cell">Student ID</th>
              <th className="table-head-cell">Name</th>
              <th className="table-head-cell">Grade</th>
              <th className="table-head-cell">Status</th>
            </tr>
          </thead>
          <tbody>
            {students.map((s, i) => (
              <tr key={s.id} className="table-row">
                <td className="table-cell text-text-tertiary">{i + 1}</td>
                <td className="table-cell font-mono text-xs">{s.student_id}</td>
                <td className="table-cell">
                  <Link
                    to={`/admin/students/${s.id}`}
                    state={{ from: `/admin/clients/${id}`, fromLabel: `Back to ${client.company_name}` }}
                    className="font-medium text-primary hover:underline focus-ring"
                  >
                    {s.name}
                  </Link>
                </td>
                <td className="table-cell">Std {s.grade}</td>
                <td className="table-cell"><Badge status={s.status} /></td>
              </tr>
            ))}
            {students.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">No students for this client yet.</td></tr>
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
        error={contactError}
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
        error={rateError}
      />

      <ActiveStudentsModal
        open={showActiveStudents}
        onClose={() => setShowActiveStudents(false)}
        title={`${client.company_name} — active students`}
        rows={ongoingEnrollments.map((e) => ({
          id: e.id,
          studentId: e.student,
          studentName: e.student_name,
          courseName: e.course_name,
          classesCompleted: e.classes_completed,
          classesTotal: e.classes_total,
        }))}
      />
    </div>
  )
}
