import { apiFetch } from './client'

export type OpportunityStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXECUTED' | 'EXPIRED'

export interface Opportunity {
  id: number
  detected_at: string
  mode: 'live' | 'paper' | 'backtest'
  instrument: string
  symbol: string
  expiry: string
  strike: number
  option_type: string
  buy_from: string
  sell_to: string
  top_ask: number
  top_bid: number
  spread_pct: number
  apr_pct: number
  max_notional_usd: number
  status: OpportunityStatus
  rejection_reason: string | null
}

export function fetchOpportunities(params?: {
  status?: OpportunityStatus
  min_apr?: number
  limit?: number
}) {
  const q = new URLSearchParams()
  if (params?.status) q.set('status', params.status)
  if (params?.min_apr != null) q.set('min_apr', String(params.min_apr))
  if (params?.limit != null) q.set('limit', String(params.limit))
  return apiFetch<Opportunity[]>(`/api/opportunities?${q}`)
}
