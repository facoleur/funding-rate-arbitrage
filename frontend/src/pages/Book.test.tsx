import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import Book from './Book'
import { fetchTickers, type BookRow } from '../api/tickers'

vi.mock('../api/tickers', () => ({ fetchTickers: vi.fn() }))

function quote(bid: number, ask: number) {
  return {
    bid_price: bid,
    bid_size: 3,
    ask_price: ask,
    ask_size: 2,
    underlying_price: 1000,
    taker_fee_rate: 0.0003,
    updated_at: new Date().toISOString(),
    is_stale: false,
  }
}

const ROW = {
  instrument: 'BTC-20270101-30000-C',
  underlying: 'BTC',
  expiry: '2027-01-01T00:00:00Z',
  days_to_expiry: 30,
  strike: 30000,
  option_type: 'C',
  exchanges: { derive: quote(100, 101), deribit: quote(110, 112) },
  price_spread_pct: 8.9,
  buy_exchange: 'derive',
  sell_exchange: 'deribit',
  tradeable_size: 2,
  buy_premium_usd: 202,
  sell_premium_usd: 220,
  estimated_short_margin_usd: 200,
  capital_required_usd: 402,
  gross_profit_usd: 18,
  fees_usd: 0.13,
  net_profit_usd: 17.87,
  net_return_pct: 4.45,
  apr_pct: 54.1,
  eligible: true,
  updated_at: new Date().toISOString(),
} as unknown as BookRow

function renderBook() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/book']}>
        <Book />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Largeur d'une rangée en colonnes, colSpan compris. */
function width(row: HTMLTableRowElement): number {
  return [...row.cells].reduce((n, c) => n + (c.colSpan || 1), 0)
}

beforeEach(() => {
  vi.mocked(fetchTickers).mockResolvedValue([ROW])
})

describe('Book — structure de la table', () => {
  it('garde un en-tête sur deux rangées, groupé par exchange', async () => {
    renderBook()
    await screen.findByText('BTC-20270101-30000-C')

    const head = document.querySelector('thead')!
    const [labels, sublabels] = [...head.rows]

    expect(head.rows).toHaveLength(2)
    // Un groupe de 2 colonnes (bid + ask) par exchange.
    // Portée limitée au <thead> : « derive » apparaît aussi dans le filtre exchange.
    expect(within(head).getByText('derive').closest('th')!.colSpan).toBe(2)
    expect(within(head).getByText('deribit').closest('th')!.colSpan).toBe(2)
    expect(sublabels.textContent).toContain('bid')
    expect(sublabels.textContent).toContain('ask')
    // Les deux rangées couvrent exactement la même largeur.
    expect(width(labels)).toBe(width(sublabels))
  })

  it('aligne le corps sur la largeur de l’en-tête', async () => {
    renderBook()
    await screen.findByText('BTC-20270101-30000-C')

    const head = document.querySelector('thead')!
    const body = document.querySelector('tbody')!
    expect(width(body.rows[0])).toBe(width(head.rows[0]))
  })

  it('épingle la première colonne, en-tête comme corps', async () => {
    renderBook()
    const cell = await screen.findByText('BTC-20270101-30000-C')

    expect(cell.closest('td')!.className).toContain('sticky left-0')
    expect(screen.getByText(/^Instrument/).className).toContain('sticky left-0')
  })

  it('rend une paire bid/ask par exchange', async () => {
    renderBook()
    await screen.findByText('BTC-20270101-30000-C')

    // 2 exchanges → 4 cellules de cotation, plus les colonnes fixes.
    expect(screen.getByText('100.00')).toBeDefined()
    expect(screen.getByText('101.00')).toBeDefined()
    expect(screen.getByText('110.00')).toBeDefined()
    expect(screen.getByText('112.00')).toBeDefined()
  })

  it('atténue une ligne non éligible selon le verdict du backend', async () => {
    vi.mocked(fetchTickers).mockResolvedValue([{ ...ROW, eligible: false }])
    renderBook()
    const cell = await screen.findByText('BTC-20270101-30000-C')

    expect(cell.closest('tr')!.className).toContain('opacity-50')
  })
})
