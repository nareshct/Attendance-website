import { useEffect, useRef } from 'react'

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function Modal({ open, onClose, title, children, maxWidthClass = 'max-w-lg' }) {
  const panelRef = useRef(null)
  const previouslyFocusedRef = useRef(null)

  useEffect(() => {
    if (!open) return

    previouslyFocusedRef.current = document.activeElement

    function getFocusable() {
      return panelRef.current ? Array.from(panelRef.current.querySelectorAll(FOCUSABLE_SELECTOR)) : []
    }

    // Move focus into the modal on open — the first focusable element, or the
    // panel itself (via tabIndex={-1} below) if it has none.
    const focusable = getFocusable()
    ;(focusable[0] || panelRef.current)?.focus()

    function handleKey(e) {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key !== 'Tab') return

      // Trap Tab/Shift+Tab within the modal so a keyboard user can't tab out
      // into the obscured page behind the overlay.
      const currentlyFocusable = getFocusable()
      if (currentlyFocusable.length === 0) {
        e.preventDefault()
        return
      }
      const first = currentlyFocusable[0]
      const last = currentlyFocusable[currentlyFocusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handleKey)
      document.body.style.overflow = prevOverflow
      previouslyFocusedRef.current?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 sm:items-center">
      <div className="fixed inset-0 bg-black/40" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? 'modal-title' : undefined}
        tabIndex={-1}
        className={`relative my-8 w-full ${maxWidthClass} rounded-xl bg-white shadow-lg`}
      >
        {title && (
          <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
            <h3 id="modal-title" className="text-lg font-semibold text-navy">{title}</h3>
            <button onClick={onClose} aria-label="Close" className="text-gray-400 hover:text-gray-600">
              ✕
            </button>
          </div>
        )}
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}
