import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useSSE } from '../hooks/useSSE'
import AuthBanner from './AuthBanner'
import { fetchStatus } from '../api/status'

const links = [
  { to: '/', label: 'Opportunités', end: true },
  { to: '/trades', label: 'Trades' },
  { to: '/positions', label: 'Positions' },
  { to: '/book', label: 'Book' },
  { to: '/history', label: 'Historique' },
  { to: '/funding', label: 'Funding' },
  { to: '/executor', label: 'Executor' },
]

const STORAGE_KEY = 'sidebar-collapsed'

function Dot({ on, pulse }: { on: boolean; pulse?: boolean }) {
  return (
    <span
      className={`h-1.5 w-1.5 rounded-full flex-shrink-0 ${
        on ? 'bg-emerald-500' : 'bg-red-500'
      } ${pulse ? 'animate-pulse' : ''}`}
    />
  )
}

function ToggleButton({ collapsed, onClick }: { collapsed: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex-shrink-0 rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 transition-colors"
      title={collapsed ? 'Ouvrir la sidebar' : 'Fermer la sidebar'}
      aria-label={collapsed ? 'Ouvrir la sidebar' : 'Fermer la sidebar'}
    >
      <span className="text-xs leading-none select-none">{collapsed ? '›' : '‹'}</span>
    </button>
  )
}

export default function Layout() {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  })

  const sseStatus = useSSE()
  const { data: appStatus } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
    refetchInterval: 10_000,
    retry: false,
  })

  const executorRunning = appStatus?.executor === 'RUNNING'
  const mode = appStatus?.mode
  const appVersion: string = (import.meta.env.VITE_APP_VERSION as string | undefined) ?? 'local'

  function toggle() {
    setCollapsed((prev) => {
      const next = !prev
      try {
        localStorage.setItem(STORAGE_KEY, String(next))
      } catch {
        // localStorage indisponible (mode privé, quota dépassé, etc.)
      }
      return next
    })
  }

  return (
    <div className="flex h-screen flex-col bg-zinc-950 text-zinc-100">
      <AuthBanner />

      <div className="flex min-h-0 flex-1">
        {/* Bouton flottant quand sidebar cachée */}
        {collapsed && (
          <div className="fixed top-3 left-3 z-50">
            <ToggleButton collapsed={collapsed} onClick={toggle} />
          </div>
        )}

        <aside
          className={`flex flex-col border-r border-zinc-800 bg-zinc-900 py-4 transition-[width] duration-200 ease-in-out overflow-hidden ${
            collapsed ? 'w-0 border-r-0' : 'w-44'
          }`}
        >
          <div className="flex items-center justify-between mb-6 px-4">
            <span className="text-xs font-semibold uppercase tracking-widest text-zinc-500 truncate">
              Option Arb
            </span>
            <ToggleButton collapsed={collapsed} onClick={toggle} />
          </div>

          <nav className="flex flex-col gap-0.5 px-2">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  `rounded px-3 py-1.5 text-sm transition-colors ${
                    isActive
                      ? 'bg-zinc-800 text-zinc-100'
                      : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-auto px-4 space-y-2">
            <div className="flex items-center gap-2">
              <Dot on={sseStatus === 'connected'} pulse={sseStatus === 'connecting'} />
              <span className="text-xs text-zinc-500">SSE</span>
            </div>

            {appStatus && (
              <div className="flex items-center gap-2">
                <Dot on={executorRunning} />
                <span className={`text-xs ${executorRunning ? 'text-zinc-400' : 'text-red-400'}`}>
                  {executorRunning ? 'Executor' : 'KILLED'}
                  {mode && <span className="text-zinc-500"> · {mode}</span>}
                </span>
              </div>
            )}

            {appStatus &&
              Object.entries(appStatus.exchanges).map(([name, ex]) => (
                <div
                  key={name}
                  className="flex items-center gap-2"
                  title={[
                    ex.rest_base_url && `REST: ${ex.rest_base_url}`,
                    ex.ws_url && `WS:   ${ex.ws_url}`,
                  ]
                    .filter(Boolean)
                    .join('\n')}
                >
                  <Dot on={ex.live} />
                  {ex.network && (
                    <span
                      className={`text-[9px] font-bold ${
                        ex.network === 'mainnet' ? 'text-amber-400' : 'text-sky-500'
                      }`}
                    >
                      {ex.network === 'mainnet' ? 'MAIN' : 'TEST'}
                    </span>
                  )}
                  <span className="text-xs text-zinc-500">
                    {name}
                    <span className="ml-1 text-zinc-500">{ex.instruments}</span>
                  </span>
                </div>
              ))}

            <div className="pt-1 border-t border-zinc-800">
              <span className="text-[10px] text-zinc-600">{appVersion}</span>
            </div>
          </div>
        </aside>

        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
