import { NavLink } from 'react-router-dom'

export interface TabItem {
  to: string
  label: string
  /** Passé à NavLink : match exact requis (utile pour l'onglet index d'une section). */
  end?: boolean
}

/** Barre d'onglets routés, à poser en haut d'une page qui regroupe plusieurs sous-vues. */
export default function Tabs({ tabs }: { tabs: TabItem[] }) {
  return (
    <div className="mb-4 flex gap-4 border-b border-zinc-800">
      {tabs.map((t) => (
        <NavLink
          key={t.to}
          to={t.to}
          end={t.end}
          className={({ isActive }) =>
            `-mb-px border-b-2 px-1 pb-2 text-sm transition-colors ${
              isActive
                ? 'border-zinc-100 text-zinc-100'
                : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`
          }
        >
          {t.label}
        </NavLink>
      ))}
    </div>
  )
}
