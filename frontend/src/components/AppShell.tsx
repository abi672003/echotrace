import { NavLink, Outlet } from 'react-router-dom'
import { useHealth } from '../api/hooks'
import type { ProviderKeyStatus } from '../api/types'
import { useHideNames } from '../context/HideNamesContext'
import { AdminTokenDialog } from './AdminTokenDialog'

function ProviderDot({ label, status }: { label: string; status: ProviderKeyStatus }) {
  const configured = status === 'configured'
  return (
    <span className="inline-flex items-center gap-1">
      <span
        className={`h-2 w-2 rounded-chip ${configured ? 'bg-organic' : 'bg-unsure'}`}
        aria-hidden="true"
      />
      <span className="text-ink-soft">
        {label}: {configured ? 'Configured' : 'Missing key'}
      </span>
    </span>
  )
}

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return `rounded-control px-3 py-2 text-sm font-semibold ${
    isActive ? 'bg-paper text-ink' : 'text-ink-soft hover:text-ink'
  }`
}

export function AppShell() {
  const { data: health } = useHealth()
  const { hideNames, setHideNames } = useHideNames()

  return (
    <div className="min-h-screen bg-desk font-sans text-ink">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-rule bg-paper px-4 py-3 shadow-sheet">
        <div className="flex items-center gap-4">
          <span className="text-lg font-semibold">EchoTrace</span>
          <nav className="flex items-center gap-1">
            <NavLink to="/" end className={navLinkClass}>
              Dockets
            </NavLink>
            <NavLink to="/check" className={navLinkClass}>
              Check a comment
            </NavLink>
          </nav>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-xs">
          {health && (
            <div className="flex items-center gap-3">
              <ProviderDot label="Regulations.gov" status={health.providers.regulations} />
              <ProviderDot label="Gemini" status={health.providers.gemini} />
              <ProviderDot label="Groq" status={health.providers.groq} />
            </div>
          )}
          <label className="flex items-center gap-2 text-ink-soft">
            <input
              type="checkbox"
              checked={hideNames}
              onChange={(event) => setHideNames(event.target.checked)}
            />
            Hide names
          </label>
          <AdminTokenDialog />
        </div>
      </header>
      <main className="p-4">
        <Outlet />
      </main>
    </div>
  )
}
