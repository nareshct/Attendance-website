import { useContext } from 'react'
import { ApiWarningContext } from '../context/api-warning-context-object'

export function useApiWarning() {
  const ctx = useContext(ApiWarningContext)
  if (!ctx) throw new Error('useApiWarning must be used within ApiWarningProvider')
  return ctx
}
