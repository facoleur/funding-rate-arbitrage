import { apiClient, apiRequest } from './client'
import type { components, operations } from './generated/schema'

export type FundingPoint = components['schemas']['FundingHistoryResponse']

type FundingQuery = NonNullable<
  operations['funding_history_api_funding_get']['parameters']['query']
>

export function fetchFunding(query?: FundingQuery) {
  return apiRequest(apiClient.GET('/api/funding', { params: { query } }))
}
