import { useEffect, useState } from 'react'
import { downloadFile } from '../../api/client'
import { Card } from '../../components/Card'
import { SearchableSelect } from '../../components/SearchableSelect'
import { useAuth } from '../../hooks/useAuth'
import { useApi } from '../../hooks/useApi'
import { formatDateRange } from '../../utils/date'

export default function ReportsPage() {
  const api = useApi()
  const { auth } = useAuth()

  const [trainers, setTrainers] = useState([])
  const [cycles, setCycles] = useState([])
  const [clients, setClients] = useState([])

  const [payoutFilters, setPayoutFilters] = useState({ trainer: '', cycle: '' })
  const [selectedClient, setSelectedClient] = useState('')
  const [attendanceRange, setAttendanceRange] = useState({ start: '', end: '' })
  const [attendanceReportFilters, setAttendanceReportFilters] = useState({ trainer: '', start: '', end: '' })

  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  useEffect(() => {
    api('/api/trainers/').then(setTrainers).catch(() => {})
    api('/api/billing-cycles/').then(setCycles).catch(() => {})
    api('/api/clients/').then(setClients).catch(() => {})
  }, [api])

  async function handleDownload(key, path) {
    setBusy(key)
    setError('')
    try {
      await downloadFile(path, auth.token)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-2">Reports</h1>
      <p className="text-sm text-gray-500 mb-6">Export CSV reports for payouts, attendance, or a B2B client.</p>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <h2 className="font-medium text-navy mb-1">Payouts</h2>
          <p className="text-sm text-gray-500 mb-4">Optionally filter by trainer and/or cycle.</p>
          <div className="space-y-2 mb-4">
            <SearchableSelect
              placeholder="All trainers"
              value={payoutFilters.trainer}
              onChange={(v) => setPayoutFilters({ ...payoutFilters, trainer: v })}
              options={[{ value: '', label: 'All trainers' }, ...trainers.map((t) => ({ value: t.id, label: t.name }))]}
            />
            <SearchableSelect
              placeholder="All cycles"
              value={payoutFilters.cycle}
              onChange={(v) => setPayoutFilters({ ...payoutFilters, cycle: v })}
              options={[
                { value: '', label: 'All cycles' },
                ...cycles.map((c) => ({ value: c.id, label: formatDateRange(c.cycle_start, c.cycle_end) })),
              ]}
            />
          </div>
          <button
            disabled={busy === 'payouts'}
            onClick={() => {
              const params = new URLSearchParams()
              if (payoutFilters.trainer) params.set('trainer', payoutFilters.trainer)
              if (payoutFilters.cycle) params.set('cycle', payoutFilters.cycle)
              handleDownload('payouts', `/api/reports/payouts/?${params.toString()}`)
            }}
            className="text-sm rounded-lg bg-brand-blue text-white px-4 py-2 hover:bg-blue-800 disabled:opacity-60"
          >
            {busy === 'payouts' ? 'Exporting…' : 'Export CSV'}
          </button>
        </Card>

        <Card>
          <h2 className="font-medium text-navy mb-1">Attendance</h2>
          <p className="text-sm text-gray-500 mb-4">Every class with trainer info. Optionally filter by trainer and/or date range.</p>
          <div className="space-y-2 mb-3">
            <SearchableSelect
              placeholder="All trainers"
              value={attendanceReportFilters.trainer}
              onChange={(v) => setAttendanceReportFilters({ ...attendanceReportFilters, trainer: v })}
              options={[{ value: '', label: 'All trainers' }, ...trainers.map((t) => ({ value: t.id, label: t.name }))]}
            />
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="date"
                value={attendanceReportFilters.start}
                onChange={(e) => setAttendanceReportFilters({ ...attendanceReportFilters, start: e.target.value })}
                className="input flex-1 min-w-[140px]"
              />
              <span className="text-gray-400 text-sm">to</span>
              <input
                type="date"
                value={attendanceReportFilters.end}
                onChange={(e) => setAttendanceReportFilters({ ...attendanceReportFilters, end: e.target.value })}
                className="input flex-1 min-w-[140px]"
              />
            </div>
          </div>
          <button
            disabled={busy === 'attendance'}
            onClick={() => {
              const params = new URLSearchParams()
              if (attendanceReportFilters.trainer) params.set('trainer', attendanceReportFilters.trainer)
              if (attendanceReportFilters.start) params.set('start', attendanceReportFilters.start)
              if (attendanceReportFilters.end) params.set('end', attendanceReportFilters.end)
              handleDownload('attendance', `/api/reports/attendance/?${params.toString()}`)
            }}
            className="text-sm rounded-lg bg-brand-blue text-white px-4 py-2 hover:bg-blue-800 disabled:opacity-60"
          >
            {busy === 'attendance' ? 'Exporting…' : 'Export CSV'}
          </button>
        </Card>

        <Card>
          <h2 className="font-medium text-navy mb-1">By client (B2B)</h2>
          <p className="text-sm text-gray-500 mb-4">Enrollment summary, or full attendance history, for a client's students.</p>
          <div className="mb-4">
            <SearchableSelect
              placeholder="Search client…"
              value={selectedClient}
              onChange={setSelectedClient}
              options={clients.map((c) => ({ value: c.id, label: c.company_name }))}
            />
          </div>
          <button
            disabled={!selectedClient || busy === 'client'}
            onClick={() => handleDownload('client', `/api/reports/client/${selectedClient}/`)}
            className="text-sm rounded-lg bg-brand-blue text-white px-4 py-2 hover:bg-blue-800 disabled:opacity-60 mb-4"
          >
            {busy === 'client' ? 'Exporting…' : 'Export enrollments'}
          </button>

          <div className="pt-4 border-t border-gray-100">
            <p className="text-xs text-gray-500 mb-2">Attendance export — optional date range (leave blank for all-time):</p>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <input
                type="date"
                value={attendanceRange.start}
                onChange={(e) => setAttendanceRange({ ...attendanceRange, start: e.target.value })}
                className="input flex-1 min-w-[140px]"
              />
              <span className="text-gray-400 text-sm">to</span>
              <input
                type="date"
                value={attendanceRange.end}
                onChange={(e) => setAttendanceRange({ ...attendanceRange, end: e.target.value })}
                className="input flex-1 min-w-[140px]"
              />
            </div>
            <button
              disabled={!selectedClient || busy === 'client-attendance'}
              onClick={() => {
                const params = new URLSearchParams()
                if (attendanceRange.start) params.set('start', attendanceRange.start)
                if (attendanceRange.end) params.set('end', attendanceRange.end)
                const query = params.toString()
                handleDownload('client-attendance', `/api/reports/client/${selectedClient}/attendance/${query ? `?${query}` : ''}`)
              }}
              className="text-sm rounded-lg border border-brand-blue text-brand-blue px-4 py-2 hover:bg-blue-50 disabled:opacity-60"
            >
              {busy === 'client-attendance' ? 'Exporting…' : 'Export attendance'}
            </button>
          </div>
        </Card>
      </div>
    </div>
  )
}
