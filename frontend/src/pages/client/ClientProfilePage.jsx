import { useEffect, useState } from 'react'
import { Card } from '../../components/Card'
import { useApi } from '../../hooks/useApi'

export default function ClientProfilePage() {
  const api = useApi()
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    api('/api/my-client-profile/')
      .then((data) => {
        if (!cancelled) setProfile(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [api])

  if (error) return <p className="text-error text-sm">{error}</p>
  if (!profile) return <p className="text-text-tertiary text-sm">Loading…</p>

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        {profile.logo && <img src={profile.logo} alt="" className="w-10 h-10 rounded-lg object-contain bg-white border border-gray-200" />}
        <div>
          <h1 className="text-2xl font-semibold text-navy">{profile.company_name}</h1>
          {profile.tagline && <p className="text-xs text-text-secondary">{profile.tagline}</p>}
        </div>
      </div>

      <Card className="mb-6">
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
          <div><dt className="text-text-secondary">Contact phone</dt><dd>{profile.contact_phone}</dd></div>
          <div><dt className="text-text-secondary">Contact email</dt><dd>{profile.contact_email || '—'}</dd></div>
          <div><dt className="text-text-secondary">Rate per class</dt><dd>{profile.rate_per_class != null ? `₹${profile.rate_per_class}` : '—'}</dd></div>
        </dl>

        {profile.course_rates.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <div className="text-xs text-text-secondary mb-2">Course-specific rates</div>
            <ul className="space-y-1 text-sm">
              {profile.course_rates.map((r) => (
                <li key={r.id}>{r.course_name} <span className="text-text-secondary">· ₹{r.rate_per_class}</span></li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      {profile.contacts.length > 0 && (
        <Card>
          <h2 className="text-sm font-semibold text-navy mb-3">Contacts</h2>
          <ul className="space-y-1 text-sm">
            {profile.contacts.map((c) => (
              <li key={c.id}>
                {c.name}
                {c.role && <span className="text-text-secondary"> — {c.role}</span>}
                {c.phone && <span className="text-text-secondary"> · {c.phone}</span>}
                {c.email && <span className="text-text-secondary"> · {c.email}</span>}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
