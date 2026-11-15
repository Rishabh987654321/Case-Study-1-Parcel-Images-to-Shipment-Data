import { useRef, useState } from 'react'
import { readDroppedFiles } from '../lib/readDroppedFiles'

interface DirectoryInputProps {
  webkitdirectory?: string
  directory?: string
}

export function UploadDropzone({ onFilesSelected, disabled }: { onFilesSelected: (files: File[]) => void; disabled?: boolean }) {
  const [dragActive, setDragActive] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)

  const folderInputProps: DirectoryInputProps = { webkitdirectory: '', directory: '' }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragActive(false)
    if (disabled) return
    readDroppedFiles(e.dataTransfer)
      .then(onFilesSelected)
      .catch(() => onFilesSelected(Array.from(e.dataTransfer.files)))
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    if (files.length > 0) onFilesSelected(files)
    e.target.value = ''
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDragActive(true)
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && fileInputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (!disabled && (e.key === 'Enter' || e.key === ' ')) fileInputRef.current?.click()
      }}
      aria-disabled={disabled}
      className={`flex min-h-[300px] flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
        disabled ? 'cursor-not-allowed border-gray-200 bg-gray-50 opacity-60' : 'cursor-pointer border-gray-300 bg-white hover:border-blue-400 hover:bg-blue-50'
      } ${dragActive ? 'border-blue-500 bg-blue-50' : ''}`}
    >
      <svg className="h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
        />
      </svg>
      <div>
        <p className="text-base font-medium text-gray-700">Drop parcel images here or click to browse</p>
        <p className="mt-1 text-sm text-gray-500">JPG or PNG images</p>
      </div>
      <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          disabled={disabled}
          onClick={() => fileInputRef.current?.click()}
          className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Choose images
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => folderInputRef.current?.click()}
          className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Choose a folder
        </button>
      </div>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".jpg,.jpeg,.png,image/jpeg,image/png"
        onChange={handleInputChange}
        className="hidden"
      />
      <input ref={folderInputRef} type="file" multiple onChange={handleInputChange} className="hidden" {...folderInputProps} />
    </div>
  )
}
