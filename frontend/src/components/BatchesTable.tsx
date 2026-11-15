import { useNavigate } from 'react-router-dom'
import type { BatchSummary } from '../api/types'
import { formatDateTime, shortId } from '../lib/format'
import { Badge } from './Badge'
import { BATCH_STATUS_COLORS } from '../lib/flags'

export function BatchesTable({ batches, onDelete }: { batches: BatchSummary[]; onDelete: (batch: BatchSummary) => void }) {
  const navigate = useNavigate()

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-3 py-2 text-left font-medium text-gray-500">Batch</th>
            <th className="px-3 py-2 text-left font-medium text-gray-500">Created</th>
            <th className="px-3 py-2 text-left font-medium text-gray-500">Images</th>
            <th className="px-3 py-2 text-left font-medium text-gray-500">OK / Flagged / Error</th>
            <th className="px-3 py-2 text-left font-medium text-gray-500">Status</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {batches.map((batch) => (
            <tr key={batch.batch_id} onClick={() => navigate(`/batches/${batch.batch_id}`)} className="cursor-pointer hover:bg-blue-50">
              <td className="px-3 py-2 font-medium text-gray-800">{batch.name || `Batch ${shortId(batch.batch_id)}`}</td>
              <td className="px-3 py-2 text-gray-600">{formatDateTime(batch.created_at)}</td>
              <td className="px-3 py-2 text-gray-600">{batch.total_images}</td>
              <td className="px-3 py-2 text-gray-600">
                {batch.counts.OK ?? 0} / {batch.counts.FLAGGED ?? 0} / {batch.counts.ERROR ?? 0}
              </td>
              <td className="px-3 py-2">
                <Badge color={BATCH_STATUS_COLORS[batch.status] ?? 'grey'}>{batch.status.replace(/_/g, ' ')}</Badge>
              </td>
              <td className="px-3 py-2 text-right">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    onDelete(batch)
                  }}
                  className="text-xs font-medium text-red-600 hover:underline"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
