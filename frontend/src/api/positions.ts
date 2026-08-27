import { apiClient, apiRequest } from './client'
import type { components } from './generated/schema'

export type Position = components['schemas']['PositionResponse']
export type ExchangeState = components['schemas']['ExchangeStateResponse']

export const fetchPositions = () => apiRequest(apiClient.GET('/api/positions'))
export const fetchExchanges = () => apiRequest(apiClient.GET('/api/exchanges'))
