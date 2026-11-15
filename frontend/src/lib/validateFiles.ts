export interface ValidationLimits {
  maxFileMb: number
  maxFilesPerBatch: number
}

export interface RejectedFile {
  name: string
  reason: string
}

export interface PrecheckResult {
  valid: File[]
  rejected: RejectedFile[]
}

const VALID_EXTENSIONS = ['.jpg', '.jpeg', '.png']

function hasValidExtension(name: string): boolean {
  const lower = name.toLowerCase()
  return VALID_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

/** Mirrors the server's validation closely enough to give instant feedback
 * (docs/design.md section 6 message catalogue) - the server is still the
 * source of truth and re-validates by content, not just extension. */
export function precheckFiles(files: File[], limits: ValidationLimits): PrecheckResult {
  const rejected: RejectedFile[] = []
  let valid: File[] = []

  for (const file of files) {
    if (!hasValidExtension(file.name)) {
      rejected.push({ name: file.name, reason: `"${file.name}" isn't a JPG or PNG image, so it was skipped.` })
      continue
    }
    const maxBytes = limits.maxFileMb * 1024 * 1024
    if (file.size > maxBytes) {
      const mb = (file.size / (1024 * 1024)).toFixed(1)
      rejected.push({ name: file.name, reason: `"${file.name}" is larger than ${limits.maxFileMb} MB (${mb} MB) and was skipped.` })
      continue
    }
    valid.push(file)
  }

  if (valid.length > limits.maxFilesPerBatch) {
    const overflow = valid.slice(limits.maxFilesPerBatch)
    valid = valid.slice(0, limits.maxFilesPerBatch)
    for (const file of overflow) {
      rejected.push({
        name: file.name,
        reason: `You can upload up to ${limits.maxFilesPerBatch} images at once. The first ${limits.maxFilesPerBatch} were kept.`,
      })
    }
  }

  return { valid, rejected }
}
