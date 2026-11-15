export function UploadProgress({ uploaded, total, onCancel }: { uploaded: number; total: number; onCancel?: () => void }) {
  const pct = total > 0 ? Math.round((uploaded / total) * 100) : 0
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm text-gray-700">
        <span>
          Uploading {uploaded} / {total} images...
        </span>
        {onCancel && (
          <button type="button" onClick={onCancel} className="text-xs font-medium text-red-600 hover:underline">
            Cancel upload
          </button>
        )}
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
        <div className="h-full rounded-full bg-blue-600 transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
