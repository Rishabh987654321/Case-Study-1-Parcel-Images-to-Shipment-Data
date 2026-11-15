// Plain-language labels and colours per docs/design.md section 2. Any flag
// code not in this table (future pipeline additions) falls back to showing
// the raw code rather than failing to render.

export type BadgeColor = 'green' | 'grey' | 'amber' | 'orange' | 'yellow' | 'red'

export const FLAG_LABELS: Record<string, string> = {
  NO_PARCEL: 'No parcel in photo',
  MULTIPLE_PARCELS: 'More than one parcel',
  PARTIAL_PARCEL: 'Parcel partly out of frame',
  LABEL_BLOCKED: 'Label covered',
  LABEL_UNREADABLE: "Label can't be read",
  LABEL_NOT_FOUND: 'Label not found',
  LOW_CONFIDENCE_READ: 'Unsure, needs a check',
  CONFLICTING_READS: "Numbers don't agree",
  AMBIGUOUS_AWB: 'Unclear which number is the AWB',
  IMAGE_QUALITY_POOR: 'Photo too blurry or dark',
  IMAGE_CORRUPT: 'Could not process (damaged file)',
  PROCESSING_ERROR: 'Could not process (processing error)',
}

export const FLAG_COLORS: Record<string, BadgeColor> = {
  NO_PARCEL: 'grey',
  MULTIPLE_PARCELS: 'amber',
  PARTIAL_PARCEL: 'amber',
  LABEL_BLOCKED: 'orange',
  LABEL_UNREADABLE: 'orange',
  LABEL_NOT_FOUND: 'grey',
  LOW_CONFIDENCE_READ: 'yellow',
  CONFLICTING_READS: 'yellow',
  AMBIGUOUS_AWB: 'yellow',
  IMAGE_QUALITY_POOR: 'orange',
  IMAGE_CORRUPT: 'red',
  PROCESSING_ERROR: 'red',
}

export function flagLabel(code: string | null | undefined): string {
  if (!code) return ''
  return FLAG_LABELS[code] ?? code
}

export function flagColor(code: string | null | undefined): BadgeColor {
  if (!code) return 'grey'
  return FLAG_COLORS[code] ?? 'grey'
}

export const STATUS_COLORS: Record<string, BadgeColor> = {
  OK: 'green',
  FLAGGED: 'yellow',
  ERROR: 'red',
  PENDING: 'grey',
}

export const BATCH_STATUS_COLORS: Record<string, BadgeColor> = {
  created: 'grey',
  uploading: 'grey',
  processing: 'amber',
  completed: 'green',
  completed_with_errors: 'yellow',
  cancelled: 'red',
}
