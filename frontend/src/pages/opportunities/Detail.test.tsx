import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import OpportunityDetail from './Detail'
import { fetchOpportunity, fetchOpportunitySnapshots } from '../../api/opportunities'

vi.mock('recharts', () => {
  const Passthrough = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>
  const Noop = () => null
  return {
    ResponsiveContainer: Passthrough,
    LineChart: Passthrough,
    ComposedChart: Passthrough,
    Line: Noop,
    Area: Noop,
    XAxis: Noop,
    YAxis: Noop,
    CartesianGrid: Noop,
    Tooltip: Noop,
    ReferenceDot: Noop,
  }
})

vi.mock('../../api/opportunities', () => ({
  fetchOpportunity: vi.fn(),
  fetchOpportunitySnapshots: vi.fn(),
}))

const OPP = {
  id: 7,
  instrument: 'BTC-20260101-30000-C',
  symbol: 'BTC',
  buy_from: 'derive',
  sell_to: 'deribit',
  detected_at: '2026-09-06T12:00:00Z',
  net_profit_usd: 20,
  apr_pct: 40,
  status: 'PENDING',
  live_status: 'LIVE',
  samples_count: 3,
  peak_net_profit_usd: 80,
  peak_apr_pct: 100,
  closed_at: null,
  close_reason: null,
  lifetime_sec: 300,
  decay_pct: 75,
} as unknown as Awaited<ReturnType<typeof fetchOpportunity>>

function mkSnap(ts: string, ask: number, bid: number, net: number) {
  return {
    ts,
    top_ask: ask,
    top_bid: bid,
    tradeable_size: 10,
    buy_premium_usd: ask * 10,
    sell_premium_usd: bid * 10,
    capital_required_usd: 1000,
    fees_usd: 0.5,
    net_profit_usd: net,
    net_return_pct: 1,
    apr_pct: 40,
    price_spread_pct: 5,
    underlying_price: 1000,
  }
}

const SNAPS = [
  mkSnap('2026-09-06T12:00:00Z', 100, 120, 80),
  mkSnap('2026-09-06T12:02:00Z', 100, 110, 40),
  mkSnap('2026-09-06T12:05:00Z', 100, 102, 8),
] as Awaited<ReturnType<typeof fetchOpportunitySnapshots>>

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/opportunites/7']}>
        <Routes>
          <Route path="/opportunites/:id" element={<OpportunityDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.mocked(fetchOpportunity).mockResolvedValue(OPP)
  vi.mocked(fetchOpportunitySnapshots).mockResolvedValue(SNAPS)
})

describe('OpportunityDetail', () => {
  it('renders lifecycle summary and defaults the scrubber to the last snapshot', async () => {
    renderPage()
    expect(await screen.findByText('BTC-20260101-30000-C')).toBeTruthy()
    expect(screen.getByText(/−75%/)).toBeTruthy()
    expect(screen.getByText('exec: PENDING')).toBeTruthy()

    const slider = screen.getByLabelText('snapshot') as HTMLInputElement
    expect(slider.value).toBe('2')
    expect(screen.getByText('Snapshot 3 / 3')).toBeTruthy()
    expect(screen.getByText('102.0000')).toBeTruthy() // last snapshot bid
  })

  it('scrubbing updates the shown snapshot', async () => {
    renderPage()
    const slider = (await screen.findByLabelText('snapshot')) as HTMLInputElement
    fireEvent.change(slider, { target: { value: '0' } })
    expect(screen.getByText('Snapshot 1 / 3')).toBeTruthy()
    expect(screen.getByText('120.0000')).toBeTruthy() // first snapshot bid
  })
})
