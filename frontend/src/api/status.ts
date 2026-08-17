import { apiFetch } from './client'

export interface ExchangeStatus {
  instruments: number
  last_update: string | null
  live: boolean
  network: 'mainnet' | 'testnet' | null
  rest_base_url: string | null
  ws_url: string | null
}

export interface AppStatus {
  executor: 'RUNNING' | 'KILLED'
  mode: string
  exchanges: Record<string, ExchangeStatus>
}

export function fetchStatus() {
  return apiFetch<AppStatus>('/api/status')
}
