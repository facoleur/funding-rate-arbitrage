import createClient from 'openapi-fetch'

import type { paths } from './generated/schema'

type ApiResult<T> =
  | { data: T; error?: never; response: Response }
  | { data?: never; error: unknown; response: Response }

export const apiClient = createClient<paths>({ baseUrl: '' })

function describeError(error: unknown): string {
  if (typeof error === 'string') return error
  if (error && typeof error === 'object' && 'detail' in error) {
    const detail = error.detail
    return typeof detail === 'string' ? detail : JSON.stringify(detail)
  }
  if (error == null) return ''
  try {
    return JSON.stringify(error)
  } catch {
    return String(error)
  }
}

export async function apiRequest<T>(request: Promise<ApiResult<T>>): Promise<T> {
  const result = await request
  if (result.error !== undefined) {
    const status = `${result.response.status} ${result.response.statusText}`.trim()
    const detail = describeError(result.error)
    throw new Error(detail ? `${status}: ${detail}` : status)
  }
  if (result.data === undefined) {
    throw new Error(`${result.response.status}: API response did not contain JSON data`)
  }
  return result.data
}
