export type SortDir = 'asc' | 'desc'

/** Comparateur générique sur deux valeurs déjà extraites. */
export function compareValues(a: number | string, b: number | string, dir: SortDir): number {
  const cmp = a < b ? -1 : a > b ? 1 : 0
  return dir === 'asc' ? cmp : -cmp
}

/** Valeur de repli pour trier une colonne nullable : les trous finissent en bas. */
export function nullLast(v: number | null | undefined): number {
  return v ?? -Infinity
}
