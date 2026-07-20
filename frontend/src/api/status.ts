import { apiFetch } from './client'

export interface ExchangeStatus {
  instruments: number
  last_update: string | null
  live: boolean
}

export interface AppStatus {
  executor: 'RUNNING' | 'KILLED'
  mode: string
  exchanges: Record<string, ExchangeStatus>
}

export function fetchStatus() {
  return apiFetch<AppStatus>('/api/status')
}
