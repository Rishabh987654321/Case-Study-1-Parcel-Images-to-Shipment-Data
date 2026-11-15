import type { ExportFilter } from './types'

export function getExportUrl(batchId: string, only: ExportFilter): string {
  return `/api/batches/${batchId}/export.csv?only=${only}`
}
