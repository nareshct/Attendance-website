import { useCallback, useState } from 'react'
import { Button } from '../components/Button'
import { Modal } from '../components/Modal'
import { ApiWarningContext } from './api-warning-context-object'

// Single app-wide popup for the pagination fail-loud guard in api/client.js
// (see unwrapPaginated) — previously each page surfaced this as its own inline
// error banner (or, on some pages, not at all), which was inconsistent and
// easy to miss. Centralizing it here means every list fetch that trips the
// guard, anywhere in the app, shows the same modal. See hooks/useApi.js for
// where this gets triggered.
export function ApiWarningProvider({ children }) {
  const [message, setMessage] = useState('')

  const showApiWarning = useCallback((msg) => {
    setMessage(msg)
  }, [])

  const close = () => setMessage('')

  return (
    <ApiWarningContext.Provider value={{ showApiWarning }}>
      {children}
      <Modal open={!!message} onClose={close} title="Incomplete data">
        <p className="text-sm text-text-secondary mb-4">{message}</p>
        <div className="flex justify-end">
          <Button onClick={close}>OK</Button>
        </div>
      </Modal>
    </ApiWarningContext.Provider>
  )
}
