import { apiClient, apiRequest } from './client'
import type { components } from './generated/schema'

export type ExecutorState = components['schemas']['ExecutorStateResponse']

export const fetchExecutorState = () => apiRequest(apiClient.GET('/api/executor/state'))
export const killExecutor = () => apiRequest(apiClient.POST('/api/executor/kill'))
export const resumeExecutor = () => apiRequest(apiClient.POST('/api/executor/resume'))
