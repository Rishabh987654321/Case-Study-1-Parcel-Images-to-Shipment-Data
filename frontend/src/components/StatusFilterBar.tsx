import { flagLabel } from '../lib/flags'

export type StatusFilter = 'all' | 'OK' | 'FLAGGED' | 'ERROR'

const TABS: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'OK', label: 'OK' },
  { key: 'FLAGGED', label: 'Flagged' },
  { key: 'ERROR', label: 'Error' },
]

export function StatusFilterBar({
  counts,
  flagCounts,
  totalCount,
  status,
  flag,
  search,
  onStatusChange,
  onFlagChange,
  onSearchChange,
}: {
  counts: Record<string, number>
  flagCounts: Record<string, number>
  totalCount: number
  status: StatusFilter
  flag: string | null
  search: string
  onStatusChange: (status: StatusFilter) => void
  onFlagChange: (flag: string | null) => void
  onSearchChange: (q: string) => void
}) {
  function countFor(key: StatusFilter): number {
    if (key === 'all') return totalCount
    return counts[key] ?? 0
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 bg-white p-3">
      <div className="flex gap-1">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => onStatusChange(tab.key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              status === tab.key ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            {tab.label} ({countFor(tab.key)})
          </button>
        ))}
      </div>

      {status === 'FLAGGED' && (
        <select
          value={flag ?? ''}
          onChange={(e) => onFlagChange(e.target.value || null)}
          className="rounded-md border border-gray-300 px-2 py-1.5 text-sm text-gray-700"
        >
          <option value="">Any flag</option>
          {Object.entries(flagCounts)
            .sort((a, b) => b[1] - a[1])
            .map(([code, count]) => (
              <option key={code} value={code}>
                {flagLabel(code)} ({count})
              </option>
            ))}
        </select>
      )}

      <input
        type="search"
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Search by AWB or file name"
        className="ml-auto w-full max-w-xs rounded-md border border-gray-300 px-3 py-1.5 text-sm"
      />
    </div>
  )
}
