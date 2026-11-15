import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getRecords } from '../api/records'
import type { RecordsQuery } from '../api/types'

export function useRecords(batchId: string | undefined, params: RecordsQuery, pollActive: boolean) {
  return useQuery({
    queryKey: ['records', batchId, params],
    queryFn: () => getRecords(batchId as string, params),
    enabled: Boolean(batchId),
    placeholderData: keepPreviousData,
    refetchInterval: pollActive ? 2000 : false,
  })
}
