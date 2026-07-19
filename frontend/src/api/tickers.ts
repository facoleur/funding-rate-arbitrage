import { apiFetch } from './client'

export interface ExchangeQuote {
  bid_price: number | null
  bid_size: number | null
  ask_price: number | null
  ask_size: number | null
  underlying_price: number | null
  taker_fee_rate: number
  updated_at: string
  is_stale: boolean
}

export interface BookRow {
  instrument: string
  underlying: string
  expiry: string
  strike: number
  option_type: string
  exchanges: Record<string, ExchangeQuote>
  gross_spread_pct: number | null
  net_spread_pct: number | null
  buy_exchange: string | null
  sell_exchange: string | null
  max_profit_usd: number | null
  updated_at: string
}

export function fetchTickers(params?: { underlying?: string; exchange?: string }) {
  const q = new URLSearchParams()
  if (params?.underlying) q.set('underlying', params.underlying)
  if (params?.exchange) q.set('exchange', params.exchange)
  const qs = q.toString()
  return apiFetch<BookRow[]>(`/api/tickers${qs ? '?' + qs : ''}`)
}
