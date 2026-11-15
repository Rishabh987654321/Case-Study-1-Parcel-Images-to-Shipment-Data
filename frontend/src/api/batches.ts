import { apiClient } from './client'
import type { BatchSummary, CancelResponse, CreateBatchResult, FinalizeResponse, PaginatedResponse, RetryFailedResponse } from './types'

export async function createBatch(name?: string): Promise<CreateBatchResult> {
  const { data } = await apiClient.post<CreateBatchResult>('/batches', name ? { name } : {})
  return data
}

export async function getBatch(batchId: string): Promise<BatchSummary> {
  const { data } = await apiClient.get<BatchSummary>(`/batches/${batchId}`)
  return data
}

export async function listBatches(page = 1, pageSize = 20): Promise<PaginatedResponse<BatchSummary>> {
  const { data } = await apiClient.get<PaginatedResponse<BatchSummary>>('/batches', { params: { page, page_size: pageSize } })
  return data
}

export async function finalizeBatch(batchId: string): Promise<FinalizeResponse> {
  const { data } = await apiClient.post<FinalizeResponse>(`/batches/${batchId}/finalize`)
  return data
}

export async function cancelBatch(batchId: string): Promise<CancelResponse> {
  const { data } = await apiClient.post<CancelResponse>(`/batches/${batchId}/cancel`)
  return data
}

export async function retryFailed(batchId: string): Promise<RetryFailedResponse> {
  const { data } = await apiClient.post<RetryFailedResponse>(`/batches/${batchId}/retry-failed`)
  return data
}

export async function deleteBatch(batchId: string): Promise<void> {
  await apiClient.delete(`/batches/${batchId}`)
}
