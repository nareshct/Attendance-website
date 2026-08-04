import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../hooks/useApi'

const TYPE_ROUTES = {
  student: (id) => `/admin/students/${id}`,
  trainer: (id) => `/admin/trainers/${id}`,
  client: (id) => `/admin/clients/${id}`,
}

const TYPE_LABELS = {
  student: 'Student',
  trainer: 'Trainer',
  client: 'Client',
}

export function GlobalSearch() {
  const api = useApi()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const containerRef = useRef(null)

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([])
      return
    }
    const handle = setTimeout(() => {
      api(`/api/search/?q=${encodeURIComponent(query.trim())}`).then(setResults).catch(() => {})
    }, 250)
    return () => clearTimeout(handle)
  }, [query, api])

  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  function goTo(result) {
    setQuery('')
    setResults([])
    setOpen(false)
    navigate(TYPE_ROUTES[result.type](result.id))
  }

  const showDropdown = open && query.trim().length >= 2

  return (
    <div ref={containerRef} className="relative w-full max-w-xs">
      <input
        type="text"
        placeholder="Search students, trainers, clients…"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setOpen(false)
        }}
        className="input input-sm"
      />
      {showDropdown && (
        <div className="absolute left-0 right-0 mt-1.5 bg-white border border-gray-200 rounded-xl shadow-md z-20 max-h-80 overflow-y-auto">
          {results.length === 0 ? (
            <p className="px-3 py-2 text-sm text-text-secondary">No matches.</p>
          ) : (
            results.map((r) => (
              <button
                key={`${r.type}-${r.id}`}
                type="button"
                onClick={() => goTo(r)}
                className="block w-full text-left px-3 py-2 text-sm transition-colors duration-150 ease-out hover:bg-primary-tint border-b border-gray-50 last:border-b-0"
              >
                <span className="font-medium text-navy">{r.label}</span>
                <span className="text-text-secondary ml-2 text-xs">
                  {TYPE_LABELS[r.type]} · {r.sublabel}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
