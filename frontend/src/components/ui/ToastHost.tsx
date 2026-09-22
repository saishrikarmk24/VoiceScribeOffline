import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react'

import { useUiStore } from '@/store/uiStore'
import { cn } from '@/utils/cn'

const TONES = {
  info: 'border-navy-200 bg-white text-navy-800',
  success: 'border-green-200 bg-green-50 text-green-900',
  warning: 'border-amber-300 bg-amber-50 text-amber-900',
  error: 'border-rose-300 bg-rose-50 text-rose-900',
} as const

const ICONS = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
} as const

export function ToastHost() {
  const { toasts, dismissToast } = useUiStore()
  if (toasts.length === 0) return null

  return (
    <div className="pointer-events-none fixed bottom-6 right-6 z-50 flex w-80 flex-col gap-2">
      {toasts.map((toast) => {
        const Icon = ICONS[toast.kind]
        return (
          <div
            key={toast.id}
            role="status"
            className={cn(
              'pointer-events-auto flex animate-slide-in items-start gap-2 rounded border px-3 py-2.5 text-xs shadow-raised',
              TONES[toast.kind],
            )}
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{toast.title}</p>
              {toast.detail ? <p className="mt-0.5 leading-relaxed opacity-90">{toast.detail}</p> : null}
            </div>
            <button
              type="button"
              onClick={() => dismissToast(toast.id)}
              className="shrink-0 rounded p-0.5 hover:bg-black/5"
              aria-label="Dismiss notification"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
