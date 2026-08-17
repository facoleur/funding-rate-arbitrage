import { apiFetch } from './client'

export interface FundingPoint {
  ts: number         // ms epoch
  rate_8h: number    // % per 8h (positive = longs pay shorts)
  rate_ann: number   // % annualisé
  index_price: number
}

export function fetchFunding(params?: { instrument?: string; days?: number }) {
  const q = new URLSearchParams()
  if (params?.instrument) q.set('instrument', params.instrument)
  if (params?.days != null) q.set('days', String(params.days))
  return apiFetch<FundingPoint[]>(`/api/funding?${q}`)
}
