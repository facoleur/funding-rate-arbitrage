import { NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useSSE } from '../hooks/useSSE'
import { fetchStatus } from '../api/status'

const links = [
  { to: '/', label: 'Opportunités', end: true },
  { to: '/trades', label: 'Trades' },
  { to: '/positions', label: 'Positions' },
  { to: '/book', label: 'Book' },
  { to: '/executor', label: 'Executor' },
]

function Dot({ on, pulse }: { on: boolean; pulse?: boolean }) {
  return (
    <span
      className={`h-1.5 w-1.5 rounded-full flex-shrink-0 ${
        on ? 'bg-emerald-500' : 'bg-red-500'
      } ${pulse ? 'animate-pulse' : ''}`}
    />
  )
}

export default function Layout() {
  const sseStatus = useSSE()
  const { data: appStatus } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
    refetchInterval: 10_000,
    retry: false,
  })

  const executorRunning = appStatus?.executor === 'RUNNING'
  const mode = appStatus?.mode

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100">
      <aside className="flex w-44 flex-col border-r border-zinc-800 bg-zinc-900 py-4">
        <div className="px-4 mb-6">
          <span className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
            Option Arb
          </span>
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
          {/* SSE */}
          <div className="flex items-center gap-2">
            <Dot
              on={sseStatus === 'connected'}
              pulse={sseStatus === 'connecting'}
            />
            <span className="text-xs text-zinc-500">SSE</span>
          </div>

          {/* Executor */}
          {appStatus && (
            <div className="flex items-center gap-2">
              <Dot on={executorRunning} />
              <span className={`text-xs ${executorRunning ? 'text-zinc-400' : 'text-red-400'}`}>
                {executorRunning ? 'Executor' : 'KILLED'}
                {mode && <span className="text-zinc-600"> · {mode}</span>}
              </span>
            </div>
          )}

          {/* WS par exchange */}
          {appStatus &&
            Object.entries(appStatus.exchanges).map(([name, ex]) => (
              <div key={name} className="flex items-center gap-2">
                <Dot on={ex.live} />
                <span className="text-xs text-zinc-600">
                  {name}
                  <span className="ml-1 text-zinc-700">{ex.instruments}</span>
                </span>
              </div>
            ))}
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
