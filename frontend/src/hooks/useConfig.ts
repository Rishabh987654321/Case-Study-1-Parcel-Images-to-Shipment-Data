import { useQuery } from '@tanstack/react-query'
import { getConfig } from '../api/config'

export function useConfig() {
  return useQuery({
    queryKey: ['config'],
    queryFn: getConfig,
    staleTime: Infinity,
    retry: 1,
  })
}
