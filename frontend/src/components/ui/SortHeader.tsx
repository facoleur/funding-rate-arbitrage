import type { SortDir } from '../../lib/sort'

/**
 * En-tête de colonne triable. Remplace trois implémentations quasi identiques
 * (`Th` dans Book, `SortTh` dans History, `th()` dans Opportunities).
 */
export default function SortHeader<T extends string>({
  col,
  label,
  active,
  dir,
  onSort,
  right = false,
  tip,
  className = '',
}: {
  col: T
  label: string
  active: boolean
  dir: SortDir
  onSort: (col: T) => void
  right?: boolean
  tip?: string
  /** Espacement et bordures : propres à chaque table, jamais imposés ici. */
  className?: string
}) {
  return (
    <th
      title={tip}
      onClick={() => onSort(col)}
      className={`cursor-pointer select-none hover:text-zinc-300 ${
        right ? 'text-right' : ''
      } ${className}`}
    >
      {label}
      <span className={`ml-1 ${active ? 'text-zinc-300' : 'text-zinc-600'}`}>
        {active ? (dir === 'asc' ? '↑' : '↓') : '↕'}
      </span>
    </th>
  )
}
