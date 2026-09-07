import { apiClient, apiRequest } from './client'
import type { components, operations } from './generated/schema'

export type OpportunityStatus = components['schemas']['OpportunityStatus']
export type LiveStatus = components['schemas']['LiveStatus']
export type Opportunity = components['schemas']['OpportunityResponse']
export type OpportunitySnapshot = components['schemas']['OpportunitySnapshotResponse']
/** Économie déjà arbitrée par l'API entre valeurs vérifiées et détectées. */
export type OpportunityEconomics = components['schemas']['OpportunityEconomicsResponse']
export type OpportunityStats = components['schemas']['OpportunityStatsResponse']

type OpportunityQuery = NonNullable<
  operations['list_opportunities_api_opportunities_get']['parameters']['query']
>
type OpportunityStatsQuery = NonNullable<
  operations['opportunity_stats_api_opportunities_stats_get']['parameters']['query']
>

export type SortCol = NonNullable<OpportunityQuery['sort_by']>
type OpportunityParams = Omit<OpportunityQuery, 'network'> & {
  network?: OpportunityQuery['network'] | ''
}
type OpportunityStatsParams = Omit<OpportunityStatsQuery, 'network'> & {
  network?: OpportunityStatsQuery['network'] | ''
}

export function fetchOpportunities(params?: OpportunityParams) {
  const query = params ? { ...params, network: params.network || undefined } : undefined
  return apiRequest(apiClient.GET('/api/opportunities', { params: { query } }))
}

export function fetchOpportunityStats(params?: OpportunityStatsParams) {
  const query = params ? { ...params, network: params.network || undefined } : undefined
  return apiRequest(apiClient.GET('/api/opportunities/stats', { params: { query } }))
}

export function fetchOpportunity(id: number) {
  return apiRequest(
    apiClient.GET('/api/opportunities/{opp_id}', { params: { path: { opp_id: id } } }),
  )
}

export function fetchOpportunitySnapshots(id: number) {
  return apiRequest(
    apiClient.GET('/api/opportunities/{opp_id}/snapshots', {
      params: { path: { opp_id: id } },
    }),
  )
}
