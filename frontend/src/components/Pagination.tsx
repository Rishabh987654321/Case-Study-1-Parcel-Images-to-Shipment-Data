export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  if (totalPages <= 1) return null

  const pages = new Set<number>([1, totalPages, page - 1, page, page + 1].filter((p) => p >= 1 && p <= totalPages))
  const sorted = Array.from(pages).sort((a, b) => a - b)

  return (
    <div className="flex items-center justify-center gap-1 text-sm">
      <button
        type="button"
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        className="rounded px-2 py-1 text-gray-600 hover:bg-gray-100 disabled:opacity-30"
      >
        &lt;
      </button>
      {sorted.map((p, i) => (
        <span key={p} className="flex items-center gap-1">
          {i > 0 && sorted[i - 1] !== p - 1 && <span className="px-1 text-gray-400">...</span>}
          <button
            type="button"
            onClick={() => onPageChange(p)}
            className={`rounded px-2.5 py-1 ${p === page ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-100'}`}
          >
            {p}
          </button>
        </span>
      ))}
      <button
        type="button"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
        className="rounded px-2 py-1 text-gray-600 hover:bg-gray-100 disabled:opacity-30"
      >
        &gt;
      </button>
    </div>
  )
}
