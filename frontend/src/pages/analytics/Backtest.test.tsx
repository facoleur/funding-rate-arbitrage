import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import Backtest from './Backtest'
import { fetchBacktest, type Backtest as BacktestData } from '../../api/analytics'

vi.mock('../../api/analytics', () => ({ fetchBacktest: vi.fn() }))

const RESULT = {
  summary: {
    start: '2026-08-01T00:00:00Z',
    end: '2026-09-01T00:00:00Z',
    period_days: 31,
    capital_budget_usd: null,
    peak_capital_usd: 12000,
    avg_capital_usd: 4000,
    capital_efficiency_pct: 33.3,
    total_net_profit_usd: 850,
    unrealized_net_profit_usd: 0,
    total_fees_usd: 12,
    return_on_peak_pct: 7.08,
    return_on_budget_pct: null,
    annualized_pct: 83.4,
    n_candidates: 40,
    n_taken: 25,
    n_skipped_dedup: 12,
    n_skipped_budget: 0,
    n_open: 0,
    win_rate_pct: 96,
    avg_hold_days: 4.2,
  },
  series: [
    { ts: '2026-08-01T00:00:00Z', capital_in_use_usd: 0, cumulative_profit_usd: 0 },
    { ts: '2026-08-10T00:00:00Z', capital_in_use_usd: 12000, cumulative_profit_usd: 0 },
    { ts: '2026-09-01T00:00:00Z', capital_in_use_usd: 0, cumulative_profit_usd: 850 },
  ],
  by_pair: [
    {
      pair: 'derive → deribit',
      buy_from: 'derive',
      sell_to: 'deribit',
      n_taken: 25,
      net_profit_usd: 850,
      peak_capital_usd: 12000,
    },
  ],
} as unknown as BacktestData

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/analytics/backtest']}>
        <Backtest />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.mocked(fetchBacktest).mockResolvedValue(RESULT)
})

describe('Backtest', () => {
  it('affiche le capital requis, le profit et la ventilation par paire', async () => {
    renderPage()

    await screen.findByText('Capital requis (pic)')
    expect(screen.getByText('Rendement annualisé')).toBeTruthy()
    expect(screen.getByText('83.4%')).toBeTruthy()
    expect(screen.getAllByText('$12.00k').length).toBeGreaterThan(0)
    // ventilation par paire rendue
    expect(screen.getByText('derive')).toBeTruthy()
    expect(screen.getByText('deribit')).toBeTruthy()
  })

  it('passe le budget et le toggle de dédup à l’API', async () => {
    renderPage()
    await screen.findByText('Capital requis (pic)')

    expect(vi.mocked(fetchBacktest)).toHaveBeenCalledWith(
      expect.objectContaining({ one_position_per_instrument: true }),
    )
  })
})
