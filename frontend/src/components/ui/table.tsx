import {
  createContext,
  useContext,
  type ReactNode,
  type TableHTMLAttributes,
  type TdHTMLAttributes,
  type ThHTMLAttributes,
} from 'react'

/**
 * Habillage commun des tables, calé sur le style dense de la page Book.
 *
 * C'est volontairement une couche *présentationnelle* : elle ne possède ni les
 * colonnes, ni le tri, ni la structure. Chaque page continue d'écrire ses
 * `<tr>`, ses `colSpan`, ses cellules collantes et sa coloration conditionnelle
 * — c'est exactement ce qu'une bibliothèque de table généraliste rendait
 * impossible sur Book (en-tête sur deux rangées, colonnes dynamiques par
 * exchange, première colonne épinglée).
 *
 * Deux détails que cette couche corrige au passage :
 *  - les bordures sont posées sur les **cellules**, jamais sur `<tr>` : en mode
 *    `border-separate` (nécessaire pour les en-têtes et colonnes collantes), la
 *    spec CSS impose d'ignorer les bordures des lignes ;
 *  - l'alignement est une classe portée par la cellule, car `<th>` a un
 *    `text-align: center` du navigateur qu'aucune règle héritée ne surcharge.
 */

export type Align = 'left' | 'center' | 'right'

const ALIGN: Record<Align, string> = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right',
}

/** Permet à une rangée entière de supprimer son trait (en-têtes sur 2 niveaux). */
const DividerContext = createContext(true)

export function DataTable({
  className = '',
  children,
  ...rest
}: TableHTMLAttributes<HTMLTableElement>) {
  return (
    <table className={`w-full border-separate border-spacing-0 text-xs ${className}`} {...rest}>
      {children}
    </table>
  )
}

export function THead({
  sticky = false,
  className = '',
  children,
}: {
  /** Fige l'en-tête en haut de la zone défilante. */
  sticky?: boolean
  className?: string
  children: ReactNode
}) {
  return (
    <thead className={`${sticky ? 'sticky top-0 z-10 bg-zinc-950' : ''} ${className}`}>
      {children}
    </thead>
  )
}

/** Rangée d'en-tête. `divider={false}` pour un niveau intermédiaire. */
export function HeadRow({
  divider = true,
  className = '',
  children,
}: {
  divider?: boolean
  className?: string
  children: ReactNode
}) {
  return (
    <tr className={`text-zinc-500 ${className}`}>
      <DividerContext.Provider value={divider}>{children}</DividerContext.Provider>
    </tr>
  )
}

export function Th({
  align = 'left',
  divider,
  className = '',
  children,
  ...rest
}: ThHTMLAttributes<HTMLTableCellElement> & { align?: Align; divider?: boolean }) {
  const inherited = useContext(DividerContext)
  const showDivider = divider ?? inherited
  return (
    <th
      className={`whitespace-nowrap pb-2 pr-3 ${ALIGN[align]} ${
        showDivider ? 'border-b border-zinc-800' : ''
      } ${className}`}
      {...rest}
    >
      {children}
    </th>
  )
}

/**
 * `pad` est une prop et non une classe à surcharger : deux utilitaires Tailwind
 * concurrents (`pr-1` et `pr-3`) se départagent par l'ordre du CSS généré, pas
 * par l'ordre dans l'attribut — une surcharge par `className` serait silencieusement
 * ignorée.
 */
export type CellPad = 'default' | 'tight'

const PAD: Record<CellPad, string> = {
  default: 'pr-3',
  tight: 'pr-1',
}

export function Td({
  align = 'left',
  divider = true,
  pad = 'default',
  className = '',
  children,
  ...rest
}: TdHTMLAttributes<HTMLTableCellElement> & {
  align?: Align
  divider?: boolean
  pad?: CellPad
}) {
  return (
    <td
      className={`py-1 ${PAD[pad]} ${ALIGN[align]} ${
        divider ? 'border-b border-zinc-800/40' : ''
      } ${className}`}
      {...rest}
    >
      {children}
    </td>
  )
}
