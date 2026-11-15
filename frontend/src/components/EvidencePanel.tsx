interface BarcodeResult {
  value: string
  symbology: string
  touches_border: boolean
  source_image: string
}

interface OcrLine {
  text: string
  confidence: number
  source: string
}

interface OverlayData {
  detected: boolean
  raw_text: string
  awb: string | null
  weight_raw: string | null
  dimensions_raw: string | null
}

interface QualityMetrics {
  blur_score: number
  brightness: number
  contrast: number
  width: number
  height: number
}

/** The backend's `evidence` field is a loosely-typed JSON blob (the serialized
 * pipeline dataclass tree, see app/pipeline/types.py) - read defensively since
 * its exact shape is an implementation detail, not a stable public contract. */
function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

export function EvidencePanel({ evidence, processingMs }: { evidence: Record<string, unknown>; processingMs: number }) {
  const barcodes = asArray<BarcodeResult>(evidence.barcodes)
  const ocrLines = asArray<OcrLine>(evidence.ocr_lines)
  const overlay = evidence.overlay as OverlayData | undefined
  const quality = evidence.quality as QualityMetrics | undefined

  return (
    <details className="group rounded-md border border-gray-200 bg-gray-50 text-sm" open={false}>
      <summary className="cursor-pointer select-none px-3 py-2 font-medium text-gray-700">How it was read (technical detail)</summary>
      <div className="space-y-4 border-t border-gray-200 px-3 py-3">
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Barcodes found</h4>
          {barcodes.length === 0 ? (
            <p className="text-gray-400">None decoded.</p>
          ) : (
            <ul className="mt-1 space-y-1">
              {barcodes.map((b, i) => (
                <li key={i} className="font-mono text-xs text-gray-700">
                  {b.value} <span className="text-gray-400">({b.symbology}, from {b.source_image}{b.touches_border ? ', touches border' : ''})</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">OCR text lines</h4>
          {ocrLines.length === 0 ? (
            <p className="text-gray-400">No text detected.</p>
          ) : (
            <ul className="mt-1 max-h-40 space-y-1 overflow-y-auto">
              {ocrLines.map((line, i) => (
                <li key={i} className="text-xs text-gray-700">
                  "{line.text}" <span className="text-gray-400">(confidence {line.confidence.toFixed(2)}, {line.source})</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Sorter overlay</h4>
          {overlay?.detected ? (
            <div className="mt-1 space-y-0.5 text-xs text-gray-700">
              <p className="font-mono text-gray-500">{overlay.raw_text}</p>
              <p>
                AWB: {overlay.awb ?? '—'} · Weight: {overlay.weight_raw ?? '—'} · Dimensions: {overlay.dimensions_raw ?? '—'}
              </p>
            </div>
          ) : (
            <p className="text-gray-400">No overlay detected.</p>
          )}
        </div>

        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Quality metrics</h4>
          {quality ? (
            <p className="mt-1 text-xs text-gray-700">
              Blur score {quality.blur_score.toFixed(1)} · Brightness {quality.brightness.toFixed(1)} · {quality.width}x{quality.height}px
            </p>
          ) : (
            <p className="text-gray-400">Not available.</p>
          )}
        </div>

        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Processing time</h4>
          <p className="mt-1 text-xs text-gray-700">{processingMs} ms</p>
        </div>
      </div>
    </details>
  )
}
