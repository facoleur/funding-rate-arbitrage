import { apiClient, apiRequest } from './client'
import type { components, operations } from './generated/schema'

export type TradeStatus = components['schemas']['TradeStatus']
export type Mode = components['schemas']['Mode']
export type Order = components['schemas']['OrderResponse']
export type Trade = components['schemas']['TradeResponse']

type TradeQuery = NonNullable<operations['list_trades_api_trades_get']['parameters']['query']>

export function fetchTrades(query?: TradeQuery) {
  return apiRequest(apiClient.GET('/api/trades', { params: { query } }))
}
