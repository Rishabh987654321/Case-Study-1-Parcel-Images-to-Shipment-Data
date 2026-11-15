export function formatBytes(bytes: number): string {
  const mb = bytes / (1024 * 1024)
  return `${mb.toFixed(mb >= 10 ? 0 : 1)} MB`
}

export function formatEta(etaSeconds: number | null): string {
  if (etaSeconds === null) return 'Calculating...'
  if (etaSeconds <= 0) return 'Almost done'
  if (etaSeconds < 60) return `~${Math.round(etaSeconds)} seconds left`
  const minutes = Math.round(etaSeconds / 60)
  return `~${minutes} minute${minutes === 1 ? '' : 's'} left`
}

export function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export function shortId(id: string): string {
  return id.slice(0, 8)
}
