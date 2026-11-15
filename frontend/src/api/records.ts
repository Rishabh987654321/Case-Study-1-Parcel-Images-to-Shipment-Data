import { apiClient } from './client'
import type { PaginatedResponse, RecordsQuery, ResultDetail, ResultRecord } from './types'

export async function getRecords(batchId: string, params: RecordsQuery): Promise<PaginatedResponse<ResultRecord>> {
  const { data } = await apiClient.get<PaginatedResponse<ResultRecord>>(`/batches/${batchId}/records`, {
    params: {
      status: params.status,
      flag: params.flag,
      q: params.q,
      page: params.page ?? 1,
      page_size: params.pageSize ?? 50,
      sort: params.sort ?? 'upload_order',
    },
  })
  return data
}

export async function getRecordDetail(batchId: string, imageId: string): Promise<ResultDetail> {
  const { data } = await apiClient.get<ResultDetail>(`/batches/${batchId}/records/${imageId}`)
  return data
}
