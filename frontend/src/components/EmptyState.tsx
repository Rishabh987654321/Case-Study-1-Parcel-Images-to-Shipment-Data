import type { ReactNode } from 'react'

export function EmptyState({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-gray-300 bg-gray-50 px-6 py-16 text-center text-gray-500">
      <p className="max-w-sm text-sm">{title}</p>
      {action}
    </div>
  )
}
