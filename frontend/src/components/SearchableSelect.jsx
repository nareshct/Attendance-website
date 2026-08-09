import { useEffect, useRef, useState } from 'react'

/**
 * value/onChange work like a plain <select> — onChange also receives the matching
 * option object as a second argument, so callers that need more than id/label (e.g. a
 * trainer's rates, a course's price) don't have to keep their own full list around just
 * to look the selection back up.
 *
 * Two ways to supply choices:
 * - `options`: a plain [{value, label, ...}] array, filtered client-side as you type —
 *   the original behavior, for small/fixed lists.
 * - `loadOptions(query)`: an async function returning [{value, label, ...}], called
 *   (debounced) as you type instead of `options` — for anything backed by a paginated
 *   endpoint, so the dropdown never needs the whole list loaded at once. Pass
 *   `selectedLabel` alongside it so the closed input can show the current value's label
 *   before any search has actually returned it (e.g. an edit form that opens with a
 *   value already selected).
 */
export function SearchableSelect({
  options, loadOptions, selectedLabel,
  value, onChange, placeholder = 'Search…', required = false,
}) {
  const isAsync = typeof loadOptions === 'function'

  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [asyncOptions, setAsyncOptions] = useState([])
  const [searching, setSearching] = useState(false)
  const containerRef = useRef(null)
  const debounceRef = useRef(null)
  const requestIdRef = useRef(0)

  const selected = isAsync
    ? asyncOptions.find((o) => String(o.value) === String(value)) || (value ? { value, label: selectedLabel } : null)
    : options.find((o) => String(o.value) === String(value))

  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false)
        setQuery('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Debounced so rapid typing doesn't fire a request per keystroke — mirrors every
  // other server-side search box in this app. Fires once on open (empty query) too, so
  // a freshly-opened picker shows some starting options instead of an empty list.
  useEffect(() => {
    if (!isAsync || !open) return
    clearTimeout(debounceRef.current)
    const requestId = ++requestIdRef.current
    debounceRef.current = setTimeout(() => {
      setSearching(true)
      loadOptions(query.trim())
        .then((results) => {
          if (requestId === requestIdRef.current) setAsyncOptions(results)
        })
        .finally(() => {
          if (requestId === requestIdRef.current) setSearching(false)
        })
    }, 300)
    return () => clearTimeout(debounceRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, open, isAsync])

  const filtered = isAsync
    ? asyncOptions
    : query.trim()
      ? options.filter((o) => o.label.toLowerCase().includes(query.trim().toLowerCase()))
      : options

  return (
    <div ref={containerRef} className="relative">
      {required && (
        <input
          type="text"
          required
          value={value || ''}
          onChange={() => {}}
          tabIndex={-1}
          aria-hidden="true"
          className="sr-only"
        />
      )}
      <input
        type="text"
        placeholder={placeholder}
        aria-label={placeholder}
        value={open ? query : selected ? selected.label : ''}
        onFocus={() => {
          setOpen(true)
          setQuery('')
        }}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        className="input"
        autoComplete="off"
      />
      {open && (
        <div className="absolute z-10 mt-1.5 w-full max-h-56 overflow-y-auto rounded-xl border border-gray-200 bg-white shadow-md">
          {isAsync && searching && <div className="px-3 py-2 text-sm text-text-secondary">Searching…</div>}
          {!(isAsync && searching) && filtered.length === 0 && (
            <div className="px-3 py-2 text-sm text-text-secondary">No matches</div>
          )}
          {!(isAsync && searching) && filtered.map((o) => (
            <button
              type="button"
              key={o.value}
              onClick={() => {
                onChange(String(o.value), o)
                setOpen(false)
                setQuery('')
              }}
              className="block w-full text-left px-3 py-2 text-sm text-navy transition-colors duration-150 ease-out hover:bg-primary-tint"
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
