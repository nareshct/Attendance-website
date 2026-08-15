import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { GlobalSearch } from './GlobalSearch'

export default function Layout({ title, navItems, accentClass }) {
  const { auth, logout } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="h-screen flex bg-gray-50 overflow-hidden">
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-30 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}
      <aside
        className={`w-64 shrink-0 ${accentClass} text-white flex flex-col h-full overflow-y-auto fixed inset-y-0 left-0 z-40 transform transition-transform duration-200 ease-out lg:static lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="p-5 text-base font-semibold border-b border-white/10 truncate">
          {auth.role === 'trainer' || auth.role === 'client' ? `Hello, ${auth.name || auth.username}` : title}
        </div>
        <nav className="flex-1 p-3 space-y-0.5">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                `block rounded-lg border-l-2 px-3.5 py-2.5 text-sm transition-colors duration-150 ease-out ${
                  isActive
                    ? 'border-white bg-white/15 font-medium text-white'
                    : 'border-transparent text-white/80 hover:bg-white/10 hover:text-white'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-white/10 text-sm space-y-2">
          <div className="truncate text-white/80">{auth.username}</div>
          <NavLink
            to={`/${auth.role}/change-password`}
            onClick={() => setMobileOpen(false)}
            className="block w-full rounded-lg bg-white/10 px-3 py-2 hover:bg-white/20 transition-colors duration-150 ease-out text-center"
          >
            Account settings
          </NavLink>
          <button
            onClick={logout}
            className="w-full rounded-lg bg-white/10 px-3 py-2 hover:bg-white/20 transition-colors duration-150 ease-out"
          >
            Log out
          </button>
        </div>
      </aside>
      <div className="flex-1 h-full flex flex-col overflow-hidden">
        <div className="lg:hidden flex items-center gap-3 px-4 py-3 border-b border-gray-200 bg-white shrink-0">
          <button
            onClick={() => setMobileOpen(true)}
            className="p-2 -ml-2 rounded-lg transition-colors duration-150 ease-out hover:bg-surface-sunken"
            aria-label="Open menu"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6 text-navy">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />
            </svg>
          </button>
          <span className="font-semibold text-navy truncate">{title}</span>
        </div>
        <main className="flex-1 overflow-y-auto p-6">
          {auth.role === 'admin' && (
            <div className="flex justify-end mb-4">
              <GlobalSearch />
            </div>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  )
}
