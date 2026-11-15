import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createBatch, finalizeBatch } from '../api/batches'
import { ApiError } from '../api/client'
import type { UploadResponse } from '../api/types'
import { ErrorBanner } from '../components/ErrorBanner'
import { FileChecklist } from '../components/FileChecklist'
import { UploadDropzone } from '../components/UploadDropzone'
import { UploadProgress } from '../components/UploadProgress'
import { useConfig } from '../hooks/useConfig'
import { runChunkedUpload } from '../lib/chunkUpload'
import { setLastBatchId } from '../lib/lastBatch'
import { useToast } from '../lib/toast'
import type { FileItemStatus, UploadFileItem } from '../lib/uploadTypes'
import { precheckFiles } from '../lib/validateFiles'

type Phase = 'select' | 'creating' | 'uploading' | 'finalizing'

function withStatus(items: UploadFileItem[], files: File[], status: FileItemStatus): UploadFileItem[] {
  const fileSet = new Set(files)
  return items.map((item) => (fileSet.has(item.file) ? { ...item, status } : item))
}

function withFailureMessage(items: UploadFileItem[], files: File[], message: string): UploadFileItem[] {
  const fileSet = new Set(files)
  return items.map((item) => (fileSet.has(item.file) ? { ...item, status: 'rejected' as const, message } : item))
}

/** Matches the server's accepted/rejected arrays (identified only by display
 * name) back to the UploadFileItem that was actually sent, by building a
 * per-name queue of this chunk's item ids in original order and consuming it
 * front-to-back - the server preserves relative order within each list. */
function withServerResult(items: UploadFileItem[], chunkFiles: File[], result: UploadResponse): UploadFileItem[] {
  const byName = new Map<string, string[]>()
  for (const file of chunkFiles) {
    const match = items.find((item) => item.file === file)
    if (!match) continue
    const queue = byName.get(file.name) ?? []
    queue.push(match.id)
    byName.set(file.name, queue)
  }

  const updates = new Map<string, Partial<UploadFileItem>>()
  for (const accepted of result.accepted) {
    const id = byName.get(accepted.name)?.shift()
    if (id) {
      updates.set(id, {
        status: accepted.warnings.length > 0 ? 'accepted_warning' : 'accepted',
        imageId: accepted.image_id,
        message: accepted.warnings.join(', ') || undefined,
      })
    }
  }
  for (const rejected of result.rejected) {
    const id = byName.get(rejected.name)?.shift()
    if (id) updates.set(id, { status: 'rejected', message: rejected.message })
  }

  return items.map((item) => (updates.has(item.id) ? { ...item, ...updates.get(item.id) } : item))
}

export function UploadPage() {
  const navigate = useNavigate()
  const { addToast } = useToast()
  const { data: config, isLoading: configLoading, isError: configIsError, refetch: refetchConfig } = useConfig()

  const [items, setItems] = useState<UploadFileItem[]>([])
  const [batchName, setBatchName] = useState('')
  const [phase, setPhase] = useState<Phase>('select')
  const [createError, setCreateError] = useState<string | null>(null)
  const [networkFailedFiles, setNetworkFailedFiles] = useState<File[]>([])

  const cancelledRef = useRef(false)
  const batchIdRef = useRef<string | null>(null)
  const anyAcceptedRef = useRef(false)
  const submittedFilesRef = useRef<Set<File>>(new Set())
  const [submittedTotal, setSubmittedTotal] = useState(0)

  function handleFilesSelected(newFiles: File[]) {
    if (!config) return
    const { valid, rejected } = precheckFiles(newFiles, {
      maxFileMb: config.limits.max_file_mb,
      maxFilesPerBatch: Number.POSITIVE_INFINITY,
    })
    const newItems: UploadFileItem[] = valid.map((file) => ({ id: crypto.randomUUID(), file, status: 'waiting' }))
    const rejectedItems: UploadFileItem[] = rejected.map((r) => ({
      id: crypto.randomUUID(),
      file: newFiles.find((f) => f.name === r.name) ?? new File([], r.name),
      status: 'rejected',
      message: r.reason,
    }))

    setItems((current) => {
      const merged = [...current, ...newItems, ...rejectedItems]
      const readyCount = merged.filter((i) => i.status !== 'rejected').length
      if (readyCount <= config.limits.max_files_per_batch) return merged

      let kept = 0
      return merged.map((item) => {
        if (item.status === 'rejected') return item
        kept += 1
        if (kept > config.limits.max_files_per_batch) {
          return {
            ...item,
            status: 'rejected' as const,
            message: `You can upload up to ${config.limits.max_files_per_batch} images at once. The first ${config.limits.max_files_per_batch} were kept.`,
          }
        }
        return item
      })
    })
  }

  async function runUpload(filesToUpload: File[], batchId: string) {
    const failedThisRun: File[] = []

    await runChunkedUpload(batchId, filesToUpload, {
      isCancelled: () => cancelledRef.current,
      onChunkStart: (files) => setItems((current) => withStatus(current, files, 'uploading')),
      onChunkResult: (files, result) => {
        if (result.accepted.length > 0) anyAcceptedRef.current = true
        setItems((current) => withServerResult(current, files, result))
      },
      onChunkFailed: (files, err) => {
        failedThisRun.push(...files)
        const message = err instanceof ApiError ? `Upload failed: ${err.message}` : 'Upload failed after 3 attempts. Check your connection.'
        setItems((current) => withFailureMessage(current, files, message))
      },
    })

    setNetworkFailedFiles(failedThisRun)
    return anyAcceptedRef.current
  }

  async function finalizeAndNavigate(batchId: string) {
    setPhase('finalizing')
    try {
      await finalizeBatch(batchId)
    } catch {
      // Finalize is idempotent and only fails on EMPTY_UPLOAD, which can't
      // happen here (we only get here when at least one file was accepted) -
      // navigate anyway so the user isn't stuck; the batch page shows the truth.
    }
    setLastBatchId(batchId)
    navigate(`/batches/${batchId}`)
  }

  async function handleUpload() {
    setPhase('creating')
    setCreateError(null)
    let batchId: string
    try {
      const created = await createBatch(batchName.trim() || undefined)
      batchId = created.batch_id
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : 'Could not create the batch. Please try again.')
      setPhase('select')
      return
    }
    batchIdRef.current = batchId
    cancelledRef.current = false
    anyAcceptedRef.current = false
    setPhase('uploading')

    const filesToUpload = items.filter((i) => i.status === 'waiting').map((i) => i.file)
    submittedFilesRef.current = new Set(filesToUpload)
    setSubmittedTotal(filesToUpload.length)
    const anyAccepted = await runUpload(filesToUpload, batchId)

    if (!anyAccepted) {
      setPhase('select')
      addToast('None of the selected files were accepted by the server.', 'error')
      return
    }

    await finalizeAndNavigate(batchId)
  }

  async function handleRetryFailed() {
    const batchId = batchIdRef.current
    if (!batchId || networkFailedFiles.length === 0) return
    cancelledRef.current = false
    setPhase('uploading')
    const retryFiles = networkFailedFiles
    setNetworkFailedFiles([])
    setItems((current) => withStatus(current, retryFiles, 'waiting'))
    const anyAccepted = await runUpload(retryFiles, batchId)
    if (anyAccepted) {
      await finalizeAndNavigate(batchId)
    } else {
      setPhase('select')
    }
  }

  function handleCancelUpload() {
    cancelledRef.current = true
  }

  const readyItems = items.filter((i) => i.status === 'waiting')
  const rejectedItems = items.filter((i) => i.status === 'rejected')
  const isUploading = phase === 'uploading' || phase === 'finalizing' || phase === 'creating'
  const resolvedSubmittedCount = items.filter(
    (i) => submittedFilesRef.current.has(i.file) && i.status !== 'waiting' && i.status !== 'uploading',
  ).length

  if (configIsError) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <ErrorBanner message="Cannot connect to the server. Make sure it's running on port 8000." onRetry={() => refetchConfig()} />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-6">
      <h1 className="text-xl font-semibold text-gray-900">Upload parcel images</h1>

      {createError && <ErrorBanner message={createError} onRetry={handleUpload} />}

      <input
        type="text"
        value={batchName}
        onChange={(e) => setBatchName(e.target.value)}
        placeholder="Batch name (optional)"
        disabled={isUploading}
        className="w-full max-w-sm rounded-md border border-gray-300 px-3 py-1.5 text-sm disabled:bg-gray-50"
      />

      {configLoading && <p className="text-sm text-gray-500">Loading upload limits...</p>}
      <UploadDropzone onFilesSelected={handleFilesSelected} disabled={configLoading || isUploading} />

      {items.length > 0 && phase === 'select' && (
        <p className="text-sm text-gray-600">
          {readyItems.length} image{readyItems.length === 1 ? '' : 's'} ready to upload
          {rejectedItems.length > 0 && `, ${rejectedItems.length} rejected`}
        </p>
      )}

      {readyItems.length === 0 && rejectedItems.length > 0 && phase === 'select' && (
        <ErrorBanner message="None of the selected files are valid images. Please select JPG or PNG files." />
      )}

      {isUploading && (
        <UploadProgress uploaded={resolvedSubmittedCount} total={submittedTotal} onCancel={phase === 'uploading' ? handleCancelUpload : undefined} />
      )}

      {networkFailedFiles.length > 0 && phase === 'select' && (
        <ErrorBanner message={`${networkFailedFiles.length} file(s) didn't upload after 3 attempts.`} onRetry={handleRetryFailed} />
      )}

      {items.length > 0 && <FileChecklist items={items} />}

      <button
        type="button"
        onClick={handleUpload}
        disabled={readyItems.length === 0 || isUploading}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {phase === 'creating' && 'Creating batch...'}
        {phase === 'uploading' && 'Uploading...'}
        {phase === 'finalizing' && 'Finishing up...'}
        {phase === 'select' && `Upload${readyItems.length > 0 ? ` (${readyItems.length})` : ''}`}
      </button>
    </div>
  )
}
