import { apiClient, apiRequest } from './client'
import type { components } from './generated/schema'

export type ExchangeStatus = components['schemas']['StatusExchangeResponse']
export type AppStatus = components['schemas']['StatusResponse']

export const fetchStatus = () => apiRequest(apiClient.GET('/api/status'))
