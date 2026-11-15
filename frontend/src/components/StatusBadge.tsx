import type { RecordStatus } from '../api/types'
import { STATUS_COLORS } from '../lib/flags'
import { Badge } from './Badge'

export function StatusBadge({ status, flag }: { status: RecordStatus; flag?: string | null }) {
  const color = STATUS_COLORS[status] ?? 'grey'
  const label = status === 'FLAGGED' && flag ? flag : status
  return <Badge color={color}>{label}</Badge>
}
