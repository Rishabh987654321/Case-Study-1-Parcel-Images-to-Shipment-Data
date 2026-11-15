import type { ResultRecord } from '../api/types'
import { StatusBadge } from './StatusBadge'
import { ThumbCell } from './ThumbCell'

function awbCell(record: ResultRecord) {
  if (record.status === 'OK' && record.awb) {
    return <span className="font-mono text-gray-800">{record.awb}</span>
  }
  if (record.awb_suggestion) {
    return (
      <span className="italic text-gray-400">
        <span className="font-mono">{record.awb_suggestion}</span>{' '}
        <span className="not-italic text-[10px] uppercase tracking-wide text-gray-400">(suggestion, unverified)</span>
      </span>
    )
  }
  return <span className="text-gray-400">—</span>
}

function dimensionsCell(record: ResultRecord) {
  const d = record.dimensions_cm
  if (!d || (d.length == null && d.width == null && d.height == null)) return <span className="text-gray-400">—</span>
  const parts = [d.length, d.width, d.height].map((v) => (v == null ? '?' : v))
  return <span>{parts.join(' x ')}</span>
}

export function ResultsTable({ records, onRowClick }: { records: ResultRecord[]; onRowClick: (record: ResultRecord) => void }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-3 py-2 text-left font-medium text-gray-500">Photo</th>
            <th className="px-3 py-2 text-left font-medium text-gray-500">File name</th>
            <th className="px-3 py-2 text-left font-medium text-gray-500">AWB</th>
            <th className="px-3 py-2 text-left font-medium text-gray-500">Weight (kg)</th>
            <th className="px-3 py-2 text-left font-medium text-gray-500">L x W x H (cm)</th>
            <th className="px-3 py-2 text-left font-medium text-gray-500">Status</th>
            <th className="px-3 py-2 text-left font-medium text-gray-500">Reason</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {records.map((record) => (
            <tr
              key={record.image_id}
              onClick={() => onRowClick(record)}
              className="cursor-pointer hover:bg-blue-50"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter') onRowClick(record)
              }}
            >
              <td className="px-3 py-2">
                <ThumbCell imageId={record.image_id} name={record.image_name} />
              </td>
              <td className="max-w-[220px] truncate px-3 py-2 text-gray-800">{record.image_name}</td>
              <td className="px-3 py-2">{awbCell(record)}</td>
              <td className="px-3 py-2 text-gray-700">{record.weight_kg ?? <span className="text-gray-400">—</span>}</td>
              <td className="px-3 py-2 text-gray-700">{dimensionsCell(record)}</td>
              <td className="px-3 py-2">
                <StatusBadge status={record.status} flag={record.primary_flag} />
              </td>
              <td className="max-w-[280px] px-3 py-2 text-gray-600">{record.flag_reason ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
