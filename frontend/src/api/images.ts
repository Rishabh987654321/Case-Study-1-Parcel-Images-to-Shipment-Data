import { apiClient } from './client'
import type { UploadResponse } from './types'

export async function uploadChunk(batchId: string, files: File[]): Promise<UploadResponse> {
  const form = new FormData()
  for (const file of files) form.append('files', file)
  const { data } = await apiClient.post<UploadResponse>(`/batches/${batchId}/images`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export function getThumbnailUrl(imageId: string): string {
  return `/api/images/${imageId}/thumbnail`
}

export function getOriginalUrl(imageId: string): string {
  return `/api/images/${imageId}/original`
}
