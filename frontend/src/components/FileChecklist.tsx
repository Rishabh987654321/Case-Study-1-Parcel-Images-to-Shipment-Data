import type { UploadFileItem } from '../lib/uploadTypes'

const ICONS: Record<UploadFileItem['status'], string> = {
  waiting: '⏳',
  uploading: '🔄',
  accepted: '✅',
  accepted_warning: '⚠️',
  rejected: '❌',
}

export function FileChecklist({ items }: { items: UploadFileItem[] }) {
  if (items.length === 0) return null
  return (
    <ul className="max-h-72 divide-y divide-gray-100 overflow-y-auto rounded-md border border-gray-200 bg-white text-sm">
      {items.map((item) => (
        <li key={item.id} className="flex items-start gap-2 px-3 py-2">
          <span aria-hidden="true">{ICONS[item.status]}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium text-gray-800">{item.file.name}</span>
            {item.message && (
              <span className={`block text-xs ${item.status === 'rejected' ? 'text-red-600' : 'text-amber-600'}`}>{item.message}</span>
            )}
          </span>
        </li>
      ))}
    </ul>
  )
}
