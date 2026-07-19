import { apiFetch } from './client'

export interface ExecutorState {
  status: 'RUNNING' | 'KILLED'
  kill_switch_file: string
  config: {
    mode: string
    min_apr_pct: number
    min_notional_usd: number
    max_notional_per_trade_usd: number
    max_positions_open: number
    max_daily_loss_usd: number
  }
  counters: {
    open_positions: number
    daily_pnl_usd: number
  }
}

export const fetchExecutorState = () => apiFetch<ExecutorState>('/api/executor/state')
export const killExecutor = () => apiFetch<{ killed: boolean }>('/api/executor/kill', { method: 'POST' })
export const resumeExecutor = () => apiFetch<{ killed: boolean }>('/api/executor/resume', { method: 'POST' })
