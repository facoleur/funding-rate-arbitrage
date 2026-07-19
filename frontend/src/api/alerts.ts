import { apiFetch } from './client'

export type AlertLevel = 'info' | 'warn' | 'error'

export interface Alert {
  id: number
  level: AlertLevel
  channel: string
  message: string
  sent_at: string
  meta: string | null
}

export function fetchAlerts(params?: { level?: AlertLevel; limit?: number }) {
  const q = new URLSearchParams()
  if (params?.level) q.set('level', params.level)
  if (params?.limit != null) q.set('limit', String(params.limit))
  return apiFetch<Alert[]>(`/api/alerts?${q}`)
}
