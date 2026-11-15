import type { ReactNode } from 'react'
import type { BadgeColor } from '../lib/flags'

const COLOR_CLASSES: Record<BadgeColor, string> = {
  green: 'bg-green-100 text-green-800 border-green-300',
  grey: 'bg-gray-100 text-gray-700 border-gray-300',
  amber: 'bg-amber-100 text-amber-800 border-amber-300',
  orange: 'bg-orange-100 text-orange-800 border-orange-300',
  yellow: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  red: 'bg-red-100 text-red-800 border-red-300',
}

export function Badge({ color, children }: { color: BadgeColor; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${COLOR_CLASSES[color]}`}>
      {children}
    </span>
  )
}
