const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

// Not a real HTTP status — a sentinel ApiError.status set by unwrapPaginated below,
// used by hooks/useApi.js to recognize this specific failure and show a single
// app-wide popup for it (see context/ApiWarningProvider.jsx) instead of each page
// rendering its own inline error text.
export const PAGINATION_GUARD_STATUS = 599

// DRF's PageNumberPagination wraps list responses as {count, next, previous, results}.
// Most pages just expect a bare array from a list endpoint, so unwrap it here in one
// place rather than touching every page — see DEFAULT_PAGINATION_CLASS in
// backend/config/settings.py. PAGE_SIZE is set high enough that no current list exceeds
// one page, so this is a no-op today. Pass `raw: true` to get the full envelope back
// (count/next/previous) instead — used by pages with their own "Load more" control, see
// usePaginatedList().
//
// If a list ever does grow past one page, silently returning just page 1 here would
// make every count/total on that page quietly wrong with no error — worse than a
// crash. Fail loudly instead, so it gets caught and either paginated properly or
// switched to `raw: true` + usePaginatedList().
function unwrapPaginated(data) {
  if (data && typeof data === 'object' && !Array.isArray(data) && Array.isArray(data.results) && 'count' in data) {
    if (data.next) {
      throw new ApiError(
        'This list has more results than the app fetched (it only reads the first page) — numbers on this page would be incomplete.',
        PAGINATION_GUARD_STATUS,
      )
    }
    return data.results
  }
  return data
}

export async function apiRequest(path, { method = 'GET', body, token, raw = false } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Token ${token}`

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const data = await response.json()
      if (data.detail) {
        detail = data.detail
      } else if (typeof data === 'object' && data !== null) {
        const firstKey = Object.keys(data)[0]
        const firstVal = data[firstKey]
        detail = firstKey ? `${firstKey}: ${Array.isArray(firstVal) ? firstVal[0] : firstVal}` : JSON.stringify(data)
      }
    } catch {
      // response body wasn't JSON — fall back to statusText
    }
    throw new ApiError(detail, response.status)
  }

  if (response.status === 204) return null
  const data = await response.json()
  return raw ? data : unwrapPaginated(data)
}

export async function downloadFile(path, token) {
  const headers = {}
  if (token) headers.Authorization = `Token ${token}`

  const response = await fetch(`${API_BASE_URL}${path}`, { headers })
  if (!response.ok) {
    throw new ApiError(response.statusText, response.status)
  }

  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="?([^"]+)"?/)
  const filename = match ? match[1] : 'export.csv'

  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

export async function apiUpload(path, formData, token, method = 'POST') {
  const headers = {}
  if (token) headers.Authorization = `Token ${token}`

  const response = await fetch(`${API_BASE_URL}${path}`, { method, headers, body: formData })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const data = await response.json()
      if (data.detail) {
        detail = data.detail
      } else if (typeof data === 'object' && data !== null) {
        const firstKey = Object.keys(data)[0]
        const firstVal = data[firstKey]
        detail = firstKey ? `${firstKey}: ${Array.isArray(firstVal) ? firstVal[0] : firstVal}` : JSON.stringify(data)
      }
    } catch {
      // response body wasn't JSON — fall back to statusText
    }
    throw new ApiError(detail, response.status)
  }

  return response.json()
}

export function login(username, password) {
  return apiRequest('/api/auth/login/', { method: 'POST', body: { username, password } })
}

export function logout(token) {
  return apiRequest('/api/auth/logout/', { method: 'POST', token })
}

export function changePassword(token, currentPassword, newPassword) {
  return apiRequest('/api/auth/change-password/', {
    method: 'POST',
    token,
    body: { current_password: currentPassword, new_password: newPassword },
  })
}

export function getMe(token) {
  return apiRequest('/api/auth/me/', { token })
}

export function updateEmail(token, email) {
  return apiRequest('/api/auth/update-email/', { method: 'POST', token, body: { email } })
}

export function requestPasswordReset(username) {
  return apiRequest('/api/auth/password-reset/', { method: 'POST', body: { username } })
}

export function confirmPasswordReset(uid, token, newPassword) {
  return apiRequest('/api/auth/password-reset/confirm/', {
    method: 'POST',
    body: { uid, token, new_password: newPassword },
  })
}

export function getParentView(token) {
  return apiRequest(`/api/parent-view/${token}/`)
}
