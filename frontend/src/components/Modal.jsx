import { useEffect, useRef } from 'react'

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function Modal({ open, onClose, title, children, maxWidthClass = 'max-w-lg' }) {
  const panelRef = useRef(null)
  const previouslyFocusedRef = useRef(null)
  // Callers pass an inline onClose, a fresh function identity on every parent
  // render (e.g. every keystroke in a controlled form field). Reading it via
  // ref keeps the effect below from depending on that identity — otherwise it
  // tears down and re-runs on every keystroke, re-grabbing focus onto the
  // first focusable element (the ✕ button) and yanking it out of the input.
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

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
        onCloseRef.current()
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
  }, [open])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 sm:items-center">
      <div className="fixed inset-0 bg-navy/50" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? 'modal-title' : undefined}
        tabIndex={-1}
        className={`relative my-8 w-full ${maxWidthClass} rounded-2xl bg-white shadow-xl`}
      >
        {title && (
          <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
            <h3 id="modal-title" className="text-base font-semibold text-navy">{title}</h3>
            <button
              onClick={onClose}
              aria-label="Close"
              className="rounded-full p-1.5 text-text-secondary transition-colors duration-150 ease-out hover:bg-surface-sunken hover:text-navy focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
            >
              ✕
            </button>
          </div>
        )}
        <div className="p-6">{children}</div>
      </div>
    </div>
  )
}
