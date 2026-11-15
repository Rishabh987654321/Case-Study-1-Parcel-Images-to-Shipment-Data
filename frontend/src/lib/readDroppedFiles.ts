// Drag-and-drop of a whole folder hands us DataTransferItems backed by the
// non-standard (but universally supported in Chromium/Firefox) webkitGetAsEntry
// API rather than plain Files, so folders need a recursive walk.

interface FileSystemEntryLike {
  isFile: boolean
  isDirectory: boolean
  name: string
  file?(cb: (file: File) => void): void
  createReader?(): { readEntries(cb: (entries: FileSystemEntryLike[]) => void): void }
}

function readAllEntries(reader: { readEntries(cb: (entries: FileSystemEntryLike[]) => void): void }): Promise<FileSystemEntryLike[]> {
  return new Promise((resolve) => {
    const all: FileSystemEntryLike[] = []
    const readBatch = () => {
      reader.readEntries((entries) => {
        if (entries.length === 0) {
          resolve(all)
          return
        }
        all.push(...entries)
        readBatch() // readEntries only returns a batch at a time, not everything
      })
    }
    readBatch()
  })
}

async function walkEntry(entry: FileSystemEntryLike): Promise<File[]> {
  if (entry.isFile && entry.file) {
    return new Promise((resolve) => entry.file!((file) => resolve([file])))
  }
  if (entry.isDirectory && entry.createReader) {
    const entries = await readAllEntries(entry.createReader())
    const nested = await Promise.all(entries.map(walkEntry))
    return nested.flat()
  }
  return []
}

export async function readDroppedFiles(dataTransfer: DataTransfer): Promise<File[]> {
  const items = Array.from(dataTransfer.items)
  const hasEntrySupport = items.length > 0 && typeof items[0].webkitGetAsEntry === 'function'

  if (!hasEntrySupport) {
    return Array.from(dataTransfer.files)
  }

  const entries = items
    .map((item) => item.webkitGetAsEntry() as FileSystemEntryLike | null)
    .filter((entry): entry is FileSystemEntryLike => entry !== null)

  const results = await Promise.all(entries.map(walkEntry))
  return results.flat()
}
