import { useToast } from '../lib/toast'

const KIND_CLASSES: Record<string, string> = {
  success: 'bg-green-600',
  error: 'bg-red-600',
  info: 'bg-gray-800',
}

export function ToastContainer() {
  const { toasts, dismissToast } = useToast()

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`pointer-events-auto flex items-center gap-3 rounded-md px-4 py-2 text-sm text-white shadow-lg ${KIND_CLASSES[toast.kind]}`}
        >
          <span>{toast.message}</span>
          <button type="button" onClick={() => dismissToast(toast.id)} className="text-white/70 hover:text-white" aria-label="Dismiss">
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
