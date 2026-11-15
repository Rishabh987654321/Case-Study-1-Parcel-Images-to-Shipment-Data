// Mirrors backend/app/schemas.py and docs/api.md exactly.

export type BatchStatus = 'created' | 'uploading' | 'processing' | 'completed' | 'completed_with_errors' | 'cancelled'

export type RecordStatus = 'OK' | 'FLAGGED' | 'ERROR' | 'PENDING'

// Not an exhaustive closed set on purpose: the pipeline can introduce new flag
// codes (docs/flag_taxonomy.md) and the UI must degrade gracefully (fall back
// to showing the raw code) rather than fail to compile or crash on an unknown one.
export type FlagCode = string

export interface ErrorDetail {
  code: string
  message: string
  details: Record<string, unknown>
}

export interface ErrorResponse {
  error: ErrorDetail
}

export interface LimitsResponse {
  max_file_mb: number
  max_files_per_batch: number
  max_request_mb: number
  allowed_types: string[]
}

export interface ProvidersResponse {
  ocr: string
  scene: string
  scene_available: string[]
}

export interface ConfigResponse {
  limits: LimitsResponse
  providers: ProvidersResponse
  pipeline_version: string
}

export interface HealthResponse {
  status: string
  version: string
}

export interface CreateBatchResult {
  batch_id: string
  status: BatchStatus
}

export interface BatchSummary {
  batch_id: string
  name: string | null
  status: BatchStatus
  finalized: boolean
  created_at: string
  total_images: number
  rejected_count: number
  processed: number
  progress_pct: number
  eta_seconds: number | null
  counts: Record<string, number>
  flag_counts: Record<string, number>
}

export interface UploadAccepted {
  image_id: string
  name: string
  warnings: string[]
}

export interface UploadRejected {
  name: string
  code: string
  message: string
}

export interface UploadResponse {
  accepted: UploadAccepted[]
  rejected: UploadRejected[]
}

export interface DimensionsCm {
  length: number | null
  width: number | null
  height: number | null
}

export interface ResultRecord {
  image_id: string
  image_name: string
  status: RecordStatus
  primary_flag: FlagCode | null
  flag_reason: string | null
  warnings: string[]
  awb: string | null
  awb_source: string | null
  awb_confidence: number | null
  awb_suggestion: string | null
  weight_kg: number | null
  weight_raw: string | null
  dimensions_cm: DimensionsCm | null
  dimensions_raw: string | null
  courier: string | null
  confidence: number
  processing_ms: number
  thumbnail_url: string
}

export interface ResultDetail extends ResultRecord {
  evidence: Record<string, unknown>
  image_url: string
}

export interface PaginatedResponse<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export interface FinalizeResponse {
  status: BatchStatus
}

export interface CancelResponse {
  status: BatchStatus
}

export interface RetryFailedResponse {
  requeued: number
}

export type ExportFilter = 'all' | 'ok' | 'flagged'

export interface RecordsQuery {
  status?: string
  flag?: string
  q?: string
  page?: number
  pageSize?: number
  sort?: string
}
