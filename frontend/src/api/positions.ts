import { apiFetch } from './client'

export interface Position {
  id: number
  exchange: string
  instrument: string
  size: number
  avg_price: number
  opened_at: string
  last_seen_at: string
}

export interface ExchangeState {
  exchange: string
  balance_usd: number
  margin_used_usd: number
  ws_status: 'CONNECTED' | 'RECONNECTING' | 'UNHEALTHY'
  rest_status: 'OK' | 'RATE_LIMITED' | 'DOWN'
  updated_at: string
}

export const fetchPositions = () => apiFetch<Position[]>('/api/positions')
export const fetchExchanges = () => apiFetch<ExchangeState[]>('/api/exchanges')
