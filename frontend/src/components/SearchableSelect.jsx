import { useEffect, useRef, useState } from 'react'

/** options: [{ value, label }]. value/onChange work like a plain <select>. */
export function SearchableSelect({ options, value, onChange, placeholder = 'Search…', required = false }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const containerRef = useRef(null)

  const selected = options.find((o) => String(o.value) === String(value))

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

  const filtered = query.trim()
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
        <div className="absolute z-10 mt-1 w-full max-h-56 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg">
          {filtered.length === 0 && <div className="px-3 py-2 text-sm text-gray-400">No matches</div>}
          {filtered.map((o) => (
            <button
              type="button"
              key={o.value}
              onClick={() => {
                onChange(String(o.value))
                setOpen(false)
                setQuery('')
              }}
              className="block w-full text-left px-3 py-2 text-sm hover:bg-gray-50"
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
