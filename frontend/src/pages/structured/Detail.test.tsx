import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import StructuredDetail from './Detail'
import { fetchStructuredOpportunity, fetchStructuredSnapshots } from '../../api/structured'

// recharts needs a real layout box; stub it so the test targets our own logic.
vi.mock('recharts', () => {
  const Passthrough = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>
  const Noop = () => null
  return {
    ResponsiveContainer: Passthrough,
    LineChart: Passthrough,
    Line: Noop,
    XAxis: Noop,
    YAxis: Noop,
    CartesianGrid: Noop,
    Tooltip: Noop,
    ReferenceDot: Noop,
    ReferenceLine: Noop,
  }
})

vi.mock('../../api/structured', () => ({
  fetchStructuredOpportunity: vi.fn(),
  fetchStructuredSnapshots: vi.fn(),
}))

const OPP = {
  id: 1,
  strategy_type: 'BOX',
  underlying: 'BTC',
  expiry: '2026-12-25T08:00:00Z',
  strikes: [100, 120],
  legs: [],
  is_fixed_payoff: true,
  settlement_risk: false,
  min_payoff: 20,
  max_payoff: 20,
  entry_cost: 19,
  max_fees: 0,
  min_profit: 1,
  max_profit: 1,
  max_size: 5,
  capital_required_usd: 95,
  max_total_profit_usd: 2,
  spot: 110,
  mode: 'paper',
  network: 'mainnet',
  detected_at: '2026-09-06T12:00:00Z',
  updated_at: '2026-09-06T12:05:00Z',
  last_seen_at: '2026-09-06T12:05:00Z',
  samples_count: 3,
  peak_total_profit_usd: 8,
  peak_min_profit: 1.6,
  closed_at: null,
  close_reason: null,
  live_status: 'LIVE',
  lifetime_sec: 300,
  decay_pct: 75,
} as Awaited<ReturnType<typeof fetchStructuredOpportunity>>

function mkSnap(ts: string, entry: number, total: number, c1Exchange = 'derive') {
  const mk = (instrument: string, side: 'buy' | 'sell', price: number, exchange = 'derive') => ({
    exchange,
    instrument,
    side,
    price,
    qty: 5,
    taker_fee_rate: 0,
  })
  return {
    ts,
    entry_cost: entry,
    max_fees: 0,
    min_profit: (120 - 100 - entry) / 1,
    max_size: 5,
    capital_required_usd: 95,
    max_total_profit_usd: total,
    legs: [
      mk('BTC-20260327-100-C', 'buy', 21, c1Exchange),
      mk('BTC-20260327-100-P', 'sell', 9),
      mk('BTC-20260327-120-C', 'sell', 9),
      mk('BTC-20260327-120-P', 'buy', 16),
    ],
    underlying_price: 110,
  }
}

const SNAPS = [
  mkSnap('2026-09-06T12:00:00Z', 12, 8),
  mkSnap('2026-09-06T12:02:00Z', 16, 4),
  mkSnap('2026-09-06T12:05:00Z', 19, 1, 'aevo'),
] as Awaited<ReturnType<typeof fetchStructuredSnapshots>>

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/structured/1']}>
        <Routes>
          <Route path="/structured/:id" element={<StructuredDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.mocked(fetchStructuredOpportunity).mockResolvedValue(OPP)
  vi.mocked(fetchStructuredSnapshots).mockResolvedValue(SNAPS)
})

describe('StructuredDetail', () => {
  it('shows lifecycle summary and defaults the scrubber to the last snapshot', async () => {
    renderPage()
    expect(await screen.findByText(/BOX · BTC/)).toBeTruthy()
    expect(screen.getByText(/lifetime/)).toBeTruthy()
    expect(screen.getByText(/−75%/)).toBeTruthy()

    const slider = screen.getByLabelText('snapshot') as HTMLInputElement
    expect(slider.value).toBe('2') // last of 3
    expect(screen.getByText('Snapshot 3 / 3')).toBeTruthy()
    // stats strip reflects the last snapshot's entry cost
    expect(screen.getByText('19.0000')).toBeTruthy()
  })

  it('scrubbing the slider updates the shown snapshot', async () => {
    renderPage()
    const slider = (await screen.findByLabelText('snapshot')) as HTMLInputElement

    fireEvent.change(slider, { target: { value: '0' } })

    expect(slider.value).toBe('0')
    expect(screen.getByText('Snapshot 1 / 3')).toBeTruthy()
    expect(screen.getByText('12.0000')).toBeTruthy() // first snapshot entry_cost
  })
})
