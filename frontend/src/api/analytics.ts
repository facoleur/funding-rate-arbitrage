import { apiClient, apiRequest } from './client'
import type { components, operations } from './generated/schema'

export type Backtest = components['schemas']['BacktestResponse']
export type BacktestSummary = components['schemas']['BacktestSummaryResponse']
export type BacktestPoint = components['schemas']['BacktestPointResponse']
export type BacktestPair = components['schemas']['BacktestPairResponse']

type BacktestQuery = NonNullable<
  operations['backtest_api_analytics_backtest_get']['parameters']['query']
>
type BacktestParams = Omit<BacktestQuery, 'network'> & {
  network?: BacktestQuery['network'] | ''
}

export function fetchBacktest(params?: BacktestParams) {
  const query = params ? { ...params, network: params.network || undefined } : undefined
  return apiRequest(apiClient.GET('/api/analytics/backtest', { params: { query } }))
}
