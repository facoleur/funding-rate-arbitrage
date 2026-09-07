import type { ReactNode } from 'react'

/**
 * Barre d'outils standard des pages liste : compteur de lignes + contrôles de
 * filtre. Extrait du copier-coller entre Opportunités/Live, Structured/Live et
 * les pages Historique. Le titre de section vit dans le layout, pas ici.
 */
export default function PageToolbar({
  count,
  label = 'lignes',
  children,
}: {
  count: number
  label?: string
  children?: ReactNode
}) {
  return (
    <div className="mb-3 flex flex-shrink-0 flex-wrap items-center gap-3">
      <span className="text-xs text-zinc-500">
        {count} {label}
      </span>
      {children}
    </div>
  )
}
