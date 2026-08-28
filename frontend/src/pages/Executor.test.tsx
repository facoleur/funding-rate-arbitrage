import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import Executor from './Executor'
import { fetchExecutorState, killExecutor } from '../api/executor'
import { fetchAlerts } from '../api/alerts'

vi.mock('../api/executor', () => ({
  fetchExecutorState: vi.fn(),
  killExecutor: vi.fn(),
  resumeExecutor: vi.fn(),
}))
vi.mock('../api/alerts', () => ({ fetchAlerts: vi.fn() }))

const STATE = {
  status: 'RUNNING',
  kill_switch_file: '/data/EXECUTOR_DISABLED',
  config: {
    mode: 'paper',
    min_apr_pct: 10,
    min_buy_premium_usd: 20,
    min_leg_premium_liquidity_usd: 100,
    max_days_to_expiry: 60,
    min_net_profit_usd: 3,
    min_net_return_pct: 0.3,
    max_buy_premium_per_trade_usd: 500,
    ioc_slippage_limit_pct: 2,
    max_positions_open: 10,
    max_daily_loss_usd: 100,
  },
  counters: { open_positions: 2, daily_pnl_usd: -12.5 },
} as Awaited<ReturnType<typeof fetchExecutorState>>

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Executor />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.mocked(fetchExecutorState).mockResolvedValue(STATE)
  vi.mocked(fetchAlerts).mockResolvedValue([])
  vi.mocked(killExecutor).mockResolvedValue({ killed: true })
})

describe('Executor — garde-fou du kill-switch', () => {
  it('le bouton Kill ouvre une confirmation sans rien déclencher', async () => {
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Kill' }))

    expect(await screen.findByRole('dialog', { hidden: true })).toBeDefined()
    expect(killExecutor).not.toHaveBeenCalled()
  })

  it('annuler la confirmation ne déclenche jamais le kill', async () => {
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Kill' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Annuler' }))

    expect(killExecutor).not.toHaveBeenCalled()
  })

  it('confirmer déclenche le kill une seule fois', async () => {
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Kill' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Confirmer' }))

    expect(killExecutor).toHaveBeenCalledTimes(1)
  })
})
