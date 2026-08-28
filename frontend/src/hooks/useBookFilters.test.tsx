import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { useBookFilters } from './useBookFilters'

function wrapperFor(initialUrl: string) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <MemoryRouter initialEntries={[initialUrl]}>{children}</MemoryRouter>
  }
}

function renderFilters(initialUrl = '/book') {
  return renderHook(() => useBookFilters(), { wrapper: wrapperFor(initialUrl) })
}

describe('useBookFilters', () => {
  it('part vide, tri décroissant par défaut', () => {
    const { result } = renderFilters()
    expect(result.current.underlying).toBe('')
    expect(result.current.onlyArb).toBe(false)
    expect(result.current.sortCol).toBe('')
    expect(result.current.sortDir).toBe('desc')
    expect(result.current.hasFilters).toBe(false)
  })

  it('relit un état complet depuis l’URL', () => {
    const { result } = renderFilters(
      '/book?u=ETH&t=P&ex=derive&maxexp=2026-12-31&arb=1&sort=apr&dir=asc',
    )
    expect(result.current.underlying).toBe('ETH')
    expect(result.current.optionType).toBe('P')
    expect(result.current.exchange).toBe('derive')
    expect(result.current.maxExpiry).toBe('2026-12-31')
    expect(result.current.onlyArb).toBe(true)
    expect(result.current.sortCol).toBe('apr')
    expect(result.current.sortDir).toBe('asc')
    expect(result.current.hasFilters).toBe(true)
  })

  it('écrit puis relit un filtre', () => {
    const { result } = renderFilters()
    act(() => result.current.setUnderlying('BTC'))
    expect(result.current.underlying).toBe('BTC')
    expect(result.current.hasFilters).toBe(true)
  })

  it('fait l’aller-retour sur le tri', () => {
    const { result } = renderFilters()
    act(() => result.current.setSort('netReturn', 'asc'))
    expect(result.current.sortCol).toBe('netReturn')
    expect(result.current.sortDir).toBe('asc')

    act(() => result.current.setSort('netReturn', 'desc'))
    expect(result.current.sortDir).toBe('desc')
  })

  it('décocher « arb seulement » retire le paramètre au lieu de le vider', () => {
    const { result } = renderFilters('/book?arb=1')
    expect(result.current.onlyArb).toBe(true)
    act(() => result.current.setOnlyArb(false))
    expect(result.current.onlyArb).toBe(false)
    expect(result.current.hasFilters).toBe(false)
  })

  it('reset efface les filtres mais conserve le tri', () => {
    const { result } = renderFilters('/book?u=BTC&t=C&arb=1&sort=apr&dir=asc')
    act(() => result.current.resetFilters())
    expect(result.current.hasFilters).toBe(false)
    expect(result.current.underlying).toBe('')
    expect(result.current.sortCol).toBe('apr')
    expect(result.current.sortDir).toBe('asc')
  })
})
