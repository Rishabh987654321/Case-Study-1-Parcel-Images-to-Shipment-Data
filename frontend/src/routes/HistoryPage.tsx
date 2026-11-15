import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { deleteBatch, listBatches } from '../api/batches'
import { ApiError } from '../api/client'
import type { BatchSummary } from '../api/types'
import { BatchesTable } from '../components/BatchesTable'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState } from '../components/EmptyState'
import { ErrorBanner } from '../components/ErrorBanner'
import { Pagination } from '../components/Pagination'
import { getLastBatchId } from '../lib/lastBatch'
import { shortId } from '../lib/format'
import { useToast } from '../lib/toast'

const PAGE_SIZE = 20

export function HistoryPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [page, setPage] = useState(1)
  const [pendingDelete, setPendingDelete] = useState<BatchSummary | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['batches', page],
    queryFn: () => listBatches(page, PAGE_SIZE),
  })

  const lastBatchId = getLastBatchId()

  async function handleConfirmDelete() {
    if (!pendingDelete) return
    const batchId = pendingDelete.batch_id
    setPendingDelete(null)
    try {
      await deleteBatch(batchId)
      await queryClient.invalidateQueries({ queryKey: ['batches'] })
      addToast('Batch deleted.', 'success')
    } catch (err) {
      addToast(err instanceof ApiError ? err.message : 'Could not delete the batch.', 'error')
    }
  }

  if (isError) {
    return (
      <div className="mx-auto max-w-5xl p-6">
        <ErrorBanner message="Cannot connect to the server. Make sure it's running on port 8000." onRetry={() => refetch()} />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Past batches</h1>
        {lastBatchId && (
          <button type="button" onClick={() => navigate(`/batches/${lastBatchId}`)} className="text-sm font-medium text-blue-600 hover:underline">
            Continue with last batch (Batch {shortId(lastBatchId)})
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="p-6 text-center text-sm text-gray-500">Loading...</div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="No batches yet. Upload some parcel images to get started."
          action={
            <Link to="/upload" className="text-sm font-medium text-blue-600 hover:underline">
              Go to upload
            </Link>
          }
        />
      ) : (
        <>
          <BatchesTable batches={data.items} onDelete={setPendingDelete} />
          <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPageChange={setPage} />
        </>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete this batch?"
        message="This permanently removes the batch, its images, and its results. This cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
