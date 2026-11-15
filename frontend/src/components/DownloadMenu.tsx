import { getExportUrl } from '../api/export'

export function DownloadMenu({ batchId, isComplete, hasResults }: { batchId: string; isComplete: boolean; hasResults: boolean }) {
  if (!hasResults) {
    return <p className="text-sm text-gray-500">There are no results to download yet.</p>
  }

  const label = isComplete ? 'Download' : 'Download partial results'

  return (
    <div className="space-y-2">
      {!isComplete && (
        <p className="text-xs text-amber-700">
          Processing is still running. You can download partial results now, or wait for completion.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <a
          href={getExportUrl(batchId, 'all')}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        >
          {label} All (CSV)
        </a>
        <a
          href={getExportUrl(batchId, 'ok')}
          className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Download OK Only
        </a>
        <a
          href={getExportUrl(batchId, 'flagged')}
          className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Download Flagged Only
        </a>
      </div>
    </div>
  )
}
