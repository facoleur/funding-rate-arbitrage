import { apiClient, apiRequest } from './client'
import type { components, operations } from './generated/schema'

export type ExchangeQuote = components['schemas']['TickerExchangeResponse']
export type BookRow = components['schemas']['TickerResponse']

type TickerQuery = NonNullable<operations['list_tickers_api_tickers_get']['parameters']['query']>

export function fetchTickers(query?: TickerQuery) {
  return apiRequest(apiClient.GET('/api/tickers', { params: { query } }))
}
