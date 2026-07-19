import { apiFetch } from './client'

export type TradeStatus =
  | 'PLACING'
  | 'LEG1_FILLED'
  | 'LEG2_FILLED'
  | 'FILLED'
  | 'HEDGING'
  | 'HEDGED'
  | 'STUCK'
  | 'FAILED'

export type Mode = 'live' | 'paper' | 'backtest'

export interface Order {
  id: number
  exchange: string
  side: 'BUY' | 'SELL'
  kind: string
  requested_price: number
  requested_size: number
  filled_price: number | null
  filled_size: number | null
  status: string
  exchange_order_id: string | null
  placed_at: string
  updated_at: string
}

export interface Trade {
  id: number
  opportunity_id: number
  opened_at: string
  closed_at: string | null
  mode: Mode
  status: TradeStatus
  buy_exchange: string
  sell_exchange: string
  requested_size: number
  buy_fill_price: number | null
  buy_fill_size: number | null
  sell_fill_price: number | null
  sell_fill_size: number | null
  net_pnl_usd: number | null
  slippage_pct: number | null
  fees_usd: number | null
  error: string | null
  orders?: Order[]
}

export function fetchTrades(params?: {
  mode?: Mode
  status?: TradeStatus
  limit?: number
  offset?: number
}) {
  const q = new URLSearchParams()
  if (params?.mode) q.set('mode', params.mode)
  if (params?.status) q.set('status', params.status)
  if (params?.limit != null) q.set('limit', String(params.limit))
  if (params?.offset != null) q.set('offset', String(params.offset))
  return apiFetch<Trade[]>(`/api/trades?${q}`)
}
