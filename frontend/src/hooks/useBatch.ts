import { useQuery } from '@tanstack/react-query'
import { getBatch } from '../api/batches'
import type { BatchSummary } from '../api/types'

const ACTIVE_STATUSES = new Set(['created', 'uploading', 'processing'])

export function isBatchActive(status: string): boolean {
  return ACTIVE_STATUSES.has(status)
}

/** Polls every 2s (docs/architecture.md section 6) while the batch is still
 * uploading/processing; stops automatically once it reaches a terminal status. */
export function useBatch(batchId: string | undefined) {
  return useQuery<BatchSummary>({
    queryKey: ['batch', batchId],
    queryFn: () => getBatch(batchId as string),
    enabled: Boolean(batchId),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return 2000
      return isBatchActive(data.status) ? 2000 : false
    },
  })
}
