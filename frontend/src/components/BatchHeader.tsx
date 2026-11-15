import type { BatchSummary } from '../api/types'
import { formatDateTime, formatEta, shortId } from '../lib/format'
import { BATCH_STATUS_COLORS, flagLabel } from '../lib/flags'
import { Badge } from './Badge'
import { isBatchActive } from '../hooks/useBatch'

export function BatchHeader({
  batch,
  onCancel,
  onRetryFailed,
  onDelete,
}: {
  batch: BatchSummary
  onCancel: () => void
  onRetryFailed: () => void
  onDelete: () => void
}) {
  const active = isBatchActive(batch.status)
  const hasErrors = (batch.counts.ERROR ?? 0) > 0
  const flagEntries = Object.entries(batch.flag_counts).sort((a, b) => b[1] - a[1])

  return (
    <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold text-gray-900">{batch.name || `Batch ${shortId(batch.batch_id)}`}</h1>
          <Badge color={BATCH_STATUS_COLORS[batch.status] ?? 'grey'}>{batch.status.replace(/_/g, ' ')}</Badge>
        </div>
        <div className="flex gap-2">
          {active && (
            <button type="button" onClick={onCancel} className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50">
              Cancel
            </button>
          )}
          {hasErrors && (
            <button type="button" onClick={onRetryFailed} className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50">
              Retry Failed
            </button>
          )}
          <button type="button" onClick={onDelete} className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50">
            Delete
          </button>
        </div>
      </div>
      <p className="text-sm text-gray-500">Created {formatDateTime(batch.created_at)}</p>

      {active && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm text-gray-700">
            <span>
              Processing {batch.processed} / {batch.total_images} images ({batch.progress_pct.toFixed(1)}%)
            </span>
            <span className="text-gray-500">{formatEta(batch.eta_seconds)}</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
            <div className="h-full rounded-full bg-blue-600 transition-all" style={{ width: `${batch.progress_pct}%` }} />
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-green-700">✅ OK: {batch.counts.OK ?? 0}</span>
        <span className="text-amber-700">⚠️ Flagged: {batch.counts.FLAGGED ?? 0}</span>
        <span className="text-red-700">❌ Error: {batch.counts.ERROR ?? 0}</span>
        {batch.rejected_count > 0 && <span className="text-gray-500">({batch.rejected_count} upload rejections)</span>}
      </div>

      {flagEntries.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer select-none text-gray-600">Flag breakdown</summary>
          <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-gray-600">
            {flagEntries.map(([code, count]) => (
              <li key={code}>
                {flagLabel(code)}: {count}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
