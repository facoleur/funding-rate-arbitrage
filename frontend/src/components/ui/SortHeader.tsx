import type { SortDir } from '../../lib/sort'
import { Th, type Align } from './table'

/**
 * En-tête de colonne triable. Repose sur `Th` : espacement, bordure et
 * alignement viennent de l'habillage commun, seul l'indicateur de tri est ajouté.
 */
export default function SortHeader<T extends string>({
  col,
  label,
  active,
  dir,
  onSort,
  align = 'left',
  tip,
  divider,
  className = '',
}: {
  col: T
  label: string
  active: boolean
  dir: SortDir
  onSort: (col: T) => void
  align?: Align
  tip?: string
  divider?: boolean
  className?: string
}) {
  return (
    <Th
      align={align}
      divider={divider}
      title={tip}
      onClick={() => onSort(col)}
      className={`cursor-pointer select-none hover:text-zinc-300 ${className}`}
    >
      {label}
      <span className={`ml-1 ${active ? 'text-zinc-300' : 'text-zinc-600'}`}>
        {active ? (dir === 'asc' ? '↑' : '↓') : '↕'}
      </span>
    </Th>
  )
}
