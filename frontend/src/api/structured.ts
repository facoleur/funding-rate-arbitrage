import { apiClient, apiRequest } from './client'
import type { components, operations } from './generated/schema'

export type StructuredOpportunity = components['schemas']['StructuredOpportunityResponse']
export type StructuredLeg = components['schemas']['StructuredLegResponse']
export type StructuredSnapshot = components['schemas']['StructuredSnapshotResponse']

type StructuredQuery = NonNullable<
  operations['list_structured_opportunities_api_structured_opportunities_get']['parameters']['query']
>

export type StructuredSortCol = NonNullable<StructuredQuery['sort_by']>

type StructuredParams = Omit<StructuredQuery, 'network'> & {
  network?: StructuredQuery['network'] | ''
}

export function fetchStructuredOpportunities(params?: StructuredParams) {
  const query = params ? { ...params, network: params.network || undefined } : undefined
  return apiRequest(apiClient.GET('/api/structured-opportunities', { params: { query } }))
}

export function fetchStructuredOpportunity(id: number) {
  return apiRequest(
    apiClient.GET('/api/structured-opportunities/{opp_id}', {
      params: { path: { opp_id: id } },
    }),
  )
}

export function fetchStructuredSnapshots(id: number) {
  return apiRequest(
    apiClient.GET('/api/structured-opportunities/{opp_id}/snapshots', {
      params: { path: { opp_id: id } },
    }),
  )
}
