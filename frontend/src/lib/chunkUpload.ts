import { uploadChunk } from '../api/images'
import type { UploadResponse } from '../api/types'

export const CHUNK_SIZE = 10
export const MAX_PARALLEL_CHUNKS = 3
export const MAX_ATTEMPTS = 3

export interface ChunkUploadCallbacks {
  onChunkStart: (files: File[]) => void
  onChunkResult: (files: File[], result: UploadResponse) => void
  onChunkFailed: (files: File[], error: unknown) => void
  isCancelled: () => boolean
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function uploadChunkWithRetry(batchId: string, files: File[], callbacks: ChunkUploadCallbacks): Promise<void> {
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      callbacks.onChunkStart(files)
      const result = await uploadChunk(batchId, files)
      callbacks.onChunkResult(files, result)
      return
    } catch (err) {
      if (attempt >= MAX_ATTEMPTS) {
        callbacks.onChunkFailed(files, err)
        return
      }
      await sleep(2 ** attempt * 500) // 1s, 2s, 4s
    }
  }
}

/** Splits files into chunks of CHUNK_SIZE and uploads them with up to
 * MAX_PARALLEL_CHUNKS requests in flight at once (docs/api.md section 3). */
export async function runChunkedUpload(batchId: string, files: File[], callbacks: ChunkUploadCallbacks): Promise<void> {
  const chunks: File[][] = []
  for (let i = 0; i < files.length; i += CHUNK_SIZE) chunks.push(files.slice(i, i + CHUNK_SIZE))

  let nextIndex = 0
  async function worker(): Promise<void> {
    while (nextIndex < chunks.length) {
      if (callbacks.isCancelled()) return
      const chunk = chunks[nextIndex]
      nextIndex += 1
      await uploadChunkWithRetry(batchId, chunk, callbacks)
    }
  }

  const workerCount = Math.min(MAX_PARALLEL_CHUNKS, chunks.length)
  await Promise.all(Array.from({ length: workerCount }, () => worker()))
}
