import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

import type { SortDir } from '../lib/sort'

/**
 * Filtres et tri de la page Book, persistés dans l'URL (partageable, rechargeable).
 *
 * Expose directement `sortCol` / `sortDir` : la version précédente renvoyait le
 * `SortingState` de @tanstack/react-table, que l'appelant reconvertissait aussitôt
 * — l'abstraction était façonnée pour une bibliothèque qui n'était pas utilisée.
 */
export function useBookFilters() {
  const [params, setParams] = useSearchParams()

  const underlying = params.get('u') ?? ''
  const optionType = params.get('t') ?? ''
  const exchange = params.get('ex') ?? ''
  const maxExpiry = params.get('maxexp') ?? ''
  const onlyArb = params.get('arb') === '1'
  const sortCol = params.get('sort') ?? ''
  const sortDir: SortDir = params.get('dir') === 'asc' ? 'asc' : 'desc'

  const patch = useCallback(
    (updates: Record<string, string>) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [k, v] of Object.entries(updates)) {
            if (v) next.set(k, v)
            else next.delete(k)
          }
          return next
        },
        { replace: true },
      )
    },
    [setParams],
  )

  const setSort = useCallback((col: string, dir: SortDir) => patch({ sort: col, dir }), [patch])

  const hasFilters = !!(underlying || optionType || exchange || maxExpiry || onlyArb)

  return {
    underlying,
    optionType,
    exchange,
    maxExpiry,
    onlyArb,
    hasFilters,
    sortCol,
    sortDir,
    setSort,
    setUnderlying: (v: string) => patch({ u: v }),
    setOptionType: (v: string) => patch({ t: v }),
    setExchange: (v: string) => patch({ ex: v }),
    setMaxExpiry: (v: string) => patch({ maxexp: v }),
    setOnlyArb: (v: boolean) => patch({ arb: v ? '1' : '' }),
    resetFilters: () => patch({ u: '', t: '', ex: '', maxexp: '', arb: '' }),
  }
}
