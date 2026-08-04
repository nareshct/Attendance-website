import { Button } from './Button'
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
      {error && <p className="text-error text-sm mt-3">{error}</p>}
      <div className="flex justify-end gap-3 mt-6">
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="button" variant={danger ? 'danger' : 'success'} disabled={busy} onClick={onConfirm}>
          {busy ? busyLabel : confirmLabel}
        </Button>
      </div>
    </Modal>
  )
}
