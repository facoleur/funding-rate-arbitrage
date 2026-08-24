import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { OnChangeFn, SortingState } from '@tanstack/react-table'

export interface BookFilters {
  underlying: string
  optionType: string
  exchange: string
  maxExpiry: string
  onlyArb: boolean
}

export function useBookFilters() {
  const [params, setParams] = useSearchParams()

  const underlying = params.get('u') ?? ''
  const optionType = params.get('t') ?? ''
  const exchange   = params.get('ex') ?? ''
  const maxExpiry  = params.get('maxexp') ?? ''
  const onlyArb    = params.get('arb') === '1'
  const sortId     = params.get('sort') ?? ''
  const sortDesc   = params.get('dir') !== 'asc'

  const sorting: SortingState = sortId ? [{ id: sortId, desc: sortDesc }] : []

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

  const onSortingChange: OnChangeFn<SortingState> = useCallback(
    (updater) => {
      const next = typeof updater === 'function' ? updater(sorting) : updater
      const [first] = next
      patch(first ? { sort: first.id, dir: first.desc ? 'desc' : 'asc' } : { sort: '', dir: '' })
    },
    [sorting, patch],
  )

  const hasFilters = !!(underlying || optionType || exchange || maxExpiry || onlyArb)

  return {
    underlying,
    optionType,
    exchange,
    maxExpiry,
    onlyArb,
    hasFilters,
    sorting,
    onSortingChange,
    setUnderlying: (v: string) => patch({ u: v }),
    setOptionType: (v: string) => patch({ t: v }),
    setExchange:   (v: string) => patch({ ex: v }),
    setMaxExpiry:  (v: string) => patch({ maxexp: v }),
    setOnlyArb:    (v: boolean) => patch({ arb: v ? '1' : '' }),
    resetFilters:  () => patch({ u: '', t: '', ex: '', maxexp: '', arb: '' }),
  }
}
