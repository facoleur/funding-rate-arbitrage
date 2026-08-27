import { apiClient, apiRequest } from './client'
import type { components, operations } from './generated/schema'

export type AlertLevel = components['schemas']['AlertLevel']
export type Alert = components['schemas']['AlertResponse']

type AlertQuery = NonNullable<operations['list_alerts_api_alerts_get']['parameters']['query']>

export function fetchAlerts(query?: AlertQuery) {
  return apiRequest(apiClient.GET('/api/alerts', { params: { query } }))
}
