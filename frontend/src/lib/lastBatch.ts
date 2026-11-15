const KEY = 'parcel-reader:last-batch-id'

export function getLastBatchId(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function setLastBatchId(batchId: string): void {
  try {
    localStorage.setItem(KEY, batchId)
  } catch {
    // localStorage unavailable (private mode, etc.) - not a feature worth failing over
  }
}

export function clearLastBatchId(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // ignore
  }
}
