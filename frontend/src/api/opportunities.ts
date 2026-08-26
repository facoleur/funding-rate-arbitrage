import { apiFetch } from './client'

export type OpportunityStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXECUTED' | 'EXPIRED'

export interface Opportunity {
  id: number
  detected_at: string
  mode: 'live' | 'paper' | 'backtest'
  network: 'mainnet' | 'testnet'
  instrument: string
  symbol: string
  expiry: string
  days_to_expiry: number
  strike: number
  option_type: string
  buy_from: string
  sell_to: string
  top_ask: number
  top_bid: number
  walked_ask: number | null
  walked_bid: number | null
  walked_size: number | null
  spread_pct: number
  fee_pct: number
  apr_pct: number
  max_notional_usd: number
  capital_deployed_usd: number
  net_profit_usd: number
  fees_usd: number
  gross_profit_usd: number
  status: OpportunityStatus
  rejection_reason: string | null
}

export interface OpportunityStats {
  buy_from: string
  sell_to: string
  pair: string
  count: number
  total_net_profit_usd: number
  total_fees_usd: number
  avg_apr_pct: number
  best_net_profit_usd: number
}

export type SortCol = 'detected_at' | 'apr_pct' | 'spread_pct' | 'net_profit_usd' | 'max_notional_usd' | 'fees_usd'

export function fetchOpportunities(params?: {
  status?: OpportunityStatus
  min_apr?: number
  min_profit?: number
  symbol?: string
  buy_from?: string
  sell_to?: string
  days?: number
  network?: 'mainnet' | 'testnet' | ''
  sort_by?: SortCol
  sort_dir?: 'asc' | 'desc'
  limit?: number
  offset?: number
}) {
  const q = new URLSearchParams()
  if (params?.status) q.set('status', params.status)
  if (params?.min_apr != null) q.set('min_apr', String(params.min_apr))
  if (params?.min_profit != null) q.set('min_profit', String(params.min_profit))
  if (params?.symbol) q.set('symbol', params.symbol)
  if (params?.buy_from) q.set('buy_from', params.buy_from)
  if (params?.sell_to) q.set('sell_to', params.sell_to)
  if (params?.days != null) q.set('days', String(params.days))
  if (params?.network) q.set('network', params.network)
  if (params?.sort_by) q.set('sort_by', params.sort_by)
  if (params?.sort_dir) q.set('sort_dir', params.sort_dir)
  if (params?.limit != null) q.set('limit', String(params.limit))
  if (params?.offset != null) q.set('offset', String(params.offset))
  return apiFetch<Opportunity[]>(`/api/opportunities?${q}`)
}

export function fetchOpportunityStats(params?: {
  days?: number
  symbol?: string
  network?: 'mainnet' | 'testnet' | ''
}) {
  const q = new URLSearchParams()
  if (params?.days != null) q.set('days', String(params.days))
  if (params?.symbol) q.set('symbol', params.symbol)
  if (params?.network) q.set('network', params.network)
  return apiFetch<OpportunityStats[]>(`/api/opportunities/stats?${q}`)
}
