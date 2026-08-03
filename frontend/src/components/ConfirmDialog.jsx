import { Modal } from './Modal'

// In-app replacement for window.confirm() — matches the rest of the app's
// modal styling instead of the browser's unstyleable native dialog.
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title = 'Are you sure?',
  message,
  confirmLabel = 'Confirm',
  busyLabel = 'Working…',
  danger = false,
  busy = false,
  error = '',
}) {
  return (
    <Modal open={open} onClose={onClose} title={title} maxWidthClass="max-w-md">
      <p className="text-sm text-gray-600">{message}</p>
      {error && <p className="text-red-600 text-sm mt-3">{error}</p>}
      <div className="flex justify-end gap-3 mt-5">
        <button type="button" onClick={onClose} className="text-sm text-gray-500 hover:underline">
          Cancel
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onConfirm}
          className={`text-sm rounded-lg px-4 py-2 text-white disabled:opacity-60 ${
            danger ? 'bg-red-600 hover:bg-red-700' : 'bg-brand-green hover:bg-green-800'
          }`}
        >
          {busy ? busyLabel : confirmLabel}
        </button>
      </div>
    </Modal>
  )
}
