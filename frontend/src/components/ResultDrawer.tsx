import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { getOriginalUrl } from '../api/images'
import { getRecordDetail } from '../api/records'
import { Badge } from './Badge'
import { EvidencePanel } from './EvidencePanel'
import { StatusBadge } from './StatusBadge'

export function ResultDrawer({
  batchId,
  imageId,
  onClose,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: {
  batchId: string
  imageId: string | null
  onClose: () => void
  onPrev: () => void
  onNext: () => void
  hasPrev: boolean
  hasNext: boolean
}) {
  const open = imageId !== null

  const { data: record, isLoading } = useQuery({
    queryKey: ['record-detail', batchId, imageId],
    queryFn: () => getRecordDetail(batchId, imageId as string),
    enabled: open,
  })

  useEffect(() => {
    if (!open) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft' && hasPrev) onPrev()
      if (e.key === 'ArrowRight' && hasNext) onNext()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open, hasPrev, hasNext, onClose, onPrev, onNext])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={onClose} role="presentation">
      <div
        className="flex h-full w-full max-w-xl flex-col overflow-y-auto bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <div className="flex items-center gap-2">
            <button type="button" onClick={onPrev} disabled={!hasPrev} className="rounded p-1 text-gray-500 hover:bg-gray-100 disabled:opacity-30">
              ← Prev
            </button>
            <button type="button" onClick={onNext} disabled={!hasNext} className="rounded p-1 text-gray-500 hover:bg-gray-100 disabled:opacity-30">
              Next →
            </button>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 text-gray-500 hover:bg-gray-100">
            ✕
          </button>
        </div>

        <div className="flex-1 space-y-4 px-4 py-4">
          {isLoading || !record ? (
            <div className="flex h-64 items-center justify-center text-gray-400">Loading...</div>
          ) : (
            <>
              <img src={getOriginalUrl(record.image_id)} alt={record.image_name} className="max-h-96 w-full rounded-md border border-gray-200 object-contain" />

              <div className="flex items-center gap-2">
                <StatusBadge status={record.status} flag={record.primary_flag} />
                <span className="truncate text-sm text-gray-500">{record.image_name}</span>
              </div>

              <dl className="space-y-2 text-sm">
                <div>
                  <dt className="font-medium text-gray-700">AWB</dt>
                  <dd className="text-gray-800">
                    {record.awb ? (
                      <>
                        {record.awb}
                        {record.awb_source && <span className="text-gray-500"> — from {record.awb_source}</span>}
                        {record.awb_confidence != null && <span className="text-gray-500">, confidence {record.awb_confidence.toFixed(2)}</span>}
                      </>
                    ) : (
                      <span className="text-gray-400">Not read</span>
                    )}
                  </dd>
                </div>

                {record.awb_suggestion && (
                  <div>
                    <dt className="font-medium text-gray-700">Possible number (unverified)</dt>
                    <dd className="italic text-gray-500">{record.awb_suggestion}</dd>
                  </div>
                )}

                <div>
                  <dt className="font-medium text-gray-700">Weight</dt>
                  <dd className="text-gray-800">
                    {record.weight_kg != null ? `${record.weight_kg} kg` : <span className="text-gray-400">Not printed</span>}
                    {record.weight_raw && <span className="text-gray-500"> — raw: "{record.weight_raw}"</span>}
                  </dd>
                </div>

                <div>
                  <dt className="font-medium text-gray-700">Dimensions</dt>
                  <dd className="text-gray-800">
                    {record.dimensions_cm && (record.dimensions_cm.length != null || record.dimensions_cm.width != null || record.dimensions_cm.height != null) ? (
                      <>
                        {record.dimensions_cm.length ?? '?'} x {record.dimensions_cm.width ?? '?'} x {record.dimensions_cm.height ?? '?'} cm
                      </>
                    ) : (
                      <span className="text-gray-400">Not printed</span>
                    )}
                    {record.dimensions_raw && <span className="text-gray-500"> — raw: "{record.dimensions_raw}"</span>}
                  </dd>
                </div>

                {record.flag_reason && (
                  <div>
                    <dt className="font-medium text-gray-700">Reason</dt>
                    <dd className="text-gray-800">{record.flag_reason}</dd>
                  </div>
                )}

                {record.warnings.length > 0 && (
                  <div>
                    <dt className="font-medium text-gray-700">Warnings</dt>
                    <dd className="mt-1 flex flex-wrap gap-1">
                      {record.warnings.map((w) => (
                        <Badge key={w} color="grey">
                          {w}
                        </Badge>
                      ))}
                    </dd>
                  </div>
                )}
              </dl>

              <EvidencePanel evidence={record.evidence} processingMs={record.processing_ms} />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
