export type FileItemStatus = 'waiting' | 'uploading' | 'accepted' | 'accepted_warning' | 'rejected'

export interface UploadFileItem {
  id: string
  file: File
  status: FileItemStatus
  message?: string
  imageId?: string
}
