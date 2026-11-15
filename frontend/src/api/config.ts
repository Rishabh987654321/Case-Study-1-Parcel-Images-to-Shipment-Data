import { apiClient } from './client'
import type { ConfigResponse, HealthResponse } from './types'

export async function getConfig(): Promise<ConfigResponse> {
  const { data } = await apiClient.get<ConfigResponse>('/config')
  return data
}

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>('/health')
  return data
}
