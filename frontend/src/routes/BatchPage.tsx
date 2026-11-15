import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { cancelBatch, deleteBatch, retryFailed } from '../api/batches'
import { BatchHeader } from '../components/BatchHeader'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { DownloadMenu } from '../components/DownloadMenu'
import { EmptyState } from '../components/EmptyState'
import { ErrorBanner } from '../components/ErrorBanner'
import { Pagination } from '../components/Pagination'
import { ResultDrawer } from '../components/ResultDrawer'
import { ResultsTable } from '../components/ResultsTable'
import { StatusFilterBar, type StatusFilter } from '../components/StatusFilterBar'
import { isBatchActive, useBatch } from '../hooks/useBatch'
import { useRecords } from '../hooks/useRecords'
import { useToast } from '../lib/toast'

const PAGE_SIZE = 50

export function BatchPage() {
  const { batchId } = useParams<{ batchId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { addToast } = useToast()

  const [status, setStatus] = useState<StatusFilter>('all')
  const [flag, setFlag] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [selectedImageId, setSelectedImageId] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const { data: batch, isLoading: batchLoading, isError: batchIsError, error: batchError } = useBatch(batchId)

  const active = batch ? isBatchActive(batch.status) : false
  const { data: records, isLoading: recordsLoading } = useRecords(
    batchId,
    { status: status === 'all' ? undefined : status, flag: flag ?? undefined, q: search || undefined, page, pageSize: PAGE_SIZE },
    active,
  )

  function resetToPage1() {
    setPage(1)
  }

  async function handleCancel() {
    if (!batchId) return
    try {
      await cancelBatch(batchId)
      await queryClient.invalidateQueries({ queryKey: ['batch', batchId] })
      addToast('Batch cancelled.', 'info')
    } catch (err) {
      addToast(err instanceof ApiError ? err.message : 'Could not cancel the batch.', 'error')
    }
  }

  async function handleRetryFailed() {
    if (!batchId) return
    try {
      const result = await retryFailed(batchId)
      await queryClient.invalidateQueries({ queryKey: ['batch', batchId] })
      await queryClient.invalidateQueries({ queryKey: ['records', batchId] })
      addToast(`Requeued ${result.requeued} image(s) for retry.`, 'success')
    } catch (err) {
      addToast(err instanceof ApiError ? err.message : 'Could not retry failed images.', 'error')
    }
  }

  async function handleDelete() {
    if (!batchId) return
    setConfirmDelete(false)
    try {
      await deleteBatch(batchId)
      addToast('Batch deleted.', 'success')
      navigate('/history')
    } catch (err) {
      addToast(err instanceof ApiError ? err.message : 'Could not delete the batch.', 'error')
    }
  }

  if (!batchId) return null

  if (batchIsError) {
    const notFound = batchError instanceof ApiError && batchError.code === 'BATCH_NOT_FOUND'
    return (
      <div className="mx-auto max-w-3xl p-6">
        {notFound ? (
          <EmptyState
            title="This batch no longer exists."
            action={
              <button type="button" onClick={() => navigate('/history')} className="text-sm font-medium text-blue-600 hover:underline">
                Go to past batches
              </button>
            }
          />
        ) : (
          <ErrorBanner message={batchError instanceof ApiError ? batchError.message : "Cannot connect to the server. Make sure it's running on port 8000."} />
        )}
      </div>
    )
  }

  if (batchLoading || !batch) {
    return <div className="mx-auto max-w-5xl p-6 text-sm text-gray-500">Loading batch...</div>
  }

  const items = records?.items ?? []
  const currentIndex = selectedImageId ? items.findIndex((r) => r.image_id === selectedImageId) : -1
  // batch.processed (from the API) already includes errors - see docs/api.md's
  // worked example (OK 80 + FLAGGED 36 + ERROR 2 = processed 118) - so this is
  // simply "how many images have reached a terminal per-image outcome so far."
  const hasAnyResultsEver = batch.processed > 0

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <BatchHeader batch={batch} onCancel={handleCancel} onRetryFailed={handleRetryFailed} onDelete={() => setConfirmDelete(true)} />

      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <DownloadMenu batchId={batchId} isComplete={!active} hasResults={(records?.total ?? 0) > 0 || batch.processed > 0} />
      </div>

      {batch.total_images === 0 || (batch.processed === 0 && active) ? (
        <EmptyState title="Processing has started. Results will appear here shortly." />
      ) : (
        <>
          <StatusFilterBar
            counts={batch.counts}
            flagCounts={batch.flag_counts}
            totalCount={batch.processed}
            status={status}
            flag={flag}
            search={search}
            onStatusChange={(s) => {
              setStatus(s)
              setFlag(null)
              resetToPage1()
            }}
            onFlagChange={(f) => {
              setFlag(f)
              resetToPage1()
            }}
            onSearchChange={(q) => {
              setSearch(q)
              resetToPage1()
            }}
          />

          {recordsLoading && items.length === 0 ? (
            <div className="p-6 text-center text-sm text-gray-500">Loading results...</div>
          ) : items.length === 0 ? (
            <EmptyState
              title={hasAnyResultsEver ? 'No results match your filters.' : "Processing hasn't started yet."}
              action={
                hasAnyResultsEver && (
                  <button
                    type="button"
                    onClick={() => {
                      setStatus('all')
                      setFlag(null)
                      setSearch('')
                      resetToPage1()
                    }}
                    className="text-sm font-medium text-blue-600 hover:underline"
                  >
                    Clear filters
                  </button>
                )
              }
            />
          ) : (
            <>
              <ResultsTable records={items} onRowClick={(r) => setSelectedImageId(r.image_id)} />
              <Pagination page={page} pageSize={PAGE_SIZE} total={records?.total ?? 0} onPageChange={setPage} />
            </>
          )}
        </>
      )}

      <ResultDrawer
        batchId={batchId}
        imageId={selectedImageId}
        onClose={() => setSelectedImageId(null)}
        onPrev={() => currentIndex > 0 && setSelectedImageId(items[currentIndex - 1].image_id)}
        onNext={() => currentIndex < items.length - 1 && setSelectedImageId(items[currentIndex + 1].image_id)}
        hasPrev={currentIndex > 0}
        hasNext={currentIndex >= 0 && currentIndex < items.length - 1}
      />

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this batch?"
        message="This permanently removes the batch, its images, and its results. This cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  )
}
