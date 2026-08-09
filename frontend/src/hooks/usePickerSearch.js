import { useApi } from './useApi'

// Ready-made async `loadOptions` functions for SearchableSelect's async-search mode —
// backed by each resource's server-side ?search= (see TrainerViewSet/ClientViewSet/
// StudentViewSet/CourseViewSet search_fields) and ?status= filter, so a picker only
// ever needs one bounded page of matches, never the whole list.
//
// Uses `raw: true` + `.results` rather than the normal unwrapped api() call — a picker
// is a bounded preview that narrows as you type, so silently taking just the first page
// (instead of api()'s usual fail-loud "this list has more results" guard, meant for
// pages that claim to show a complete set) is the correct behavior here, not a bug.
export function usePickerSearch() {
  const api = useApi()

  async function trainers(query, { status = 'active' } = {}) {
    const params = new URLSearchParams()
    if (query) params.set('search', query)
    if (status) params.set('status', status)
    const data = await api(`/api/trainers/?${params}`, { raw: true })
    return data.results.map((t) => ({ ...t, value: t.id, label: t.name }))
  }

  async function clients(query, { status = 'active' } = {}) {
    const params = new URLSearchParams()
    if (query) params.set('search', query)
    if (status) params.set('status', status)
    const data = await api(`/api/clients/?${params}`, { raw: true })
    return data.results.map((c) => ({ ...c, value: c.id, label: c.company_name }))
  }

  async function students(query, { status = 'active', client } = {}) {
    const params = new URLSearchParams()
    if (query) params.set('search', query)
    if (status) params.set('status', status)
    if (client) params.set('client', client)
    const data = await api(`/api/students/?${params}`, { raw: true })
    return data.results.map((s) => ({ ...s, value: s.id, label: `${s.name} (${s.student_id})` }))
  }

  async function courses(query) {
    const params = new URLSearchParams()
    if (query) params.set('search', query)
    const data = await api(`/api/courses/?${params}`, { raw: true })
    return data.results.map((c) => ({ ...c, value: c.id, label: c.name }))
  }

  return { trainers, clients, students, courses }
}
