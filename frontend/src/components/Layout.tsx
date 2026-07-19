import { NavLink, Outlet } from 'react-router-dom'
import { useSSE } from '../hooks/useSSE'

const links = [
  { to: '/', label: 'Opportunités', end: true },
  { to: '/trades', label: 'Trades' },
  { to: '/positions', label: 'Positions' },
  { to: '/book', label: 'Book' },
  { to: '/executor', label: 'Executor' },
]

export default function Layout() {
  const sseStatus = useSSE()

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
        <div className="mt-auto px-4 flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${
              sseStatus === 'connected'
                ? 'bg-emerald-500'
                : sseStatus === 'connecting'
                  ? 'bg-yellow-500 animate-pulse'
                  : 'bg-red-500'
            }`}
          />
          <span className="text-xs text-zinc-500">SSE</span>
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
