import type { ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from 'lucide-react'

import { CONFIDENCE_TOOLTIP } from '@/constants'
import { cn } from '@/utils/cn'
import { formatConfidence } from '@/utils/format'

export function Panel({
  title,
  icon,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title: string
  icon?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={cn('flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xs text-slate-900 dark:text-slate-100', className)}>
      <header className="flex items-center justify-between gap-2 border-b border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/60 px-4 py-2.5">
        <h2 className="flex items-center gap-2 text-2xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
          {icon}
          {title}
        </h2>
        {actions ? <div className="flex items-center gap-1.5">{actions}</div> : null}
      </header>
      <div className={cn('min-h-0 flex-1 overflow-y-auto', bodyClassName)}>{children}</div>
    </section>
  )
}

export function Badge({
  children,
  className,
  title,
}: {
  children: ReactNode
  className?: string
  title?: string
}) {
  return (
    <span className={cn('badge rounded-full px-2.5 py-0.5 font-bold', className)} title={title}>
      {children}
    </span>
  )
}

export function StatusDot({ className, pulse = false }: { className?: string; pulse?: boolean }) {
  return (
    <span
      className={cn('inline-block h-2 w-2 shrink-0 rounded-full', pulse && 'animate-pulse-dot', className)}
      aria-hidden
    />
  )
}

export function ConfidenceMeter({
  value,
  label,
  className,
}: {
  value: number
  label?: string
  className?: string
}) {
  const percentage = Math.round(Math.min(Math.max(value, 0), 1) * 100)
  const tone = percentage >= 85 ? 'bg-teal-500' : percentage >= 65 ? 'bg-amber-500' : 'bg-rose-500'
  return (
    <span
      className={cn('inline-flex items-center gap-1.5 text-2xs text-slate-500', className)}
      title={CONFIDENCE_TOOLTIP}
    >
      <span className="relative h-1.5 w-10 overflow-hidden rounded-full bg-slate-100">
        <span className={cn('absolute inset-y-0 left-0 rounded-full', tone)} style={{ width: `${percentage}%` }} />
      </span>
      <span className="mono">{formatConfidence(value)}</span>
      {label ? <span className="uppercase tracking-wide">{label}</span> : null}
    </span>
  )
}

export function EmptyState({
  icon,
  title,
  detail,
  action,
}: {
  icon?: ReactNode
  title: string
  detail?: string
  action?: ReactNode
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      {icon ? <div className="text-slate-300">{icon}</div> : null}
      <p className="text-sm font-semibold text-slate-700">{title}</p>
      {detail ? <p className="max-w-sm text-xs leading-relaxed text-slate-400">{detail}</p> : null}
      {action}
    </div>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn('h-4 w-4 animate-spin text-teal-600', className)} aria-hidden />
}

export function InlineAlert({
  kind = 'info',
  title,
  children,
  onDismiss,
  action,
}: {
  kind?: 'info' | 'warning' | 'error' | 'success'
  title: string
  children?: ReactNode
  onDismiss?: () => void
  action?: ReactNode
}) {
  const tones = {
    info: 'border-[#BAE6FD] bg-[#D9EDF8] text-[#0369A1]',
    warning: 'border-[#FDE68A] bg-[#FEF0C3] text-[#78350F]',
    error: 'border-[#F9C8D4] bg-[#FCE1E8] text-[#831843]',
    success: 'border-[#BCE1D6] bg-[#D8ECE5] text-[#134E4A]',
  } as const
  const icons = {
    info: <Info className="h-4 w-4" aria-hidden />,
    warning: <AlertTriangle className="h-4 w-4" aria-hidden />,
    error: <AlertTriangle className="h-4 w-4" aria-hidden />,
    success: <CheckCircle2 className="h-4 w-4" aria-hidden />,
  } as const

  return (
    <div className={cn('flex items-start gap-2.5 rounded-2xl border px-3.5 py-2.5 text-xs', tones[kind])} role="status">
      <span className="mt-0.5 shrink-0">{icons[kind]}</span>
      <div className="min-w-0 flex-1">
        <p className="font-bold">{title}</p>
        {children ? <div className="mt-0.5 leading-relaxed font-normal">{children}</div> : null}
      </div>
      {action}
      {onDismiss ? (
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 rounded-full p-1 text-current/70 hover:bg-black/5 hover:text-current"
          aria-label="Dismiss"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </div>
  )
}

export function StatCard({
  label,
  value,
  detail,
  icon,
  tone = 'default',
}: {
  label: string
  value: ReactNode
  detail?: string
  icon?: ReactNode
  tone?: 'default' | 'mint' | 'rose' | 'butter' | 'lavender' | 'sky' | 'live' | 'review' | 'approved'
}) {
  const tones = {
    default: 'border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100',
    mint: 'border-[#BCE1D6] dark:border-teal-900/60 bg-[#D8ECE5] dark:bg-teal-950/40 text-[#134E4A] dark:text-teal-300',
    rose: 'border-[#F9C8D4] dark:border-rose-900/60 bg-[#FCE1E8] dark:bg-rose-950/40 text-[#831843] dark:text-rose-300',
    butter: 'border-[#FDE68A] dark:border-amber-900/60 bg-[#FEF0C3] dark:bg-amber-950/40 text-[#78350F] dark:text-amber-300',
    lavender: 'border-[#DDD6FE] dark:border-purple-900/60 bg-[#E5DEFA] dark:bg-purple-950/40 text-[#4C1D95] dark:text-purple-300',
    sky: 'border-[#BAE6FD] dark:border-sky-900/60 bg-[#D9EDF8] dark:bg-sky-950/40 text-[#0369A1] dark:text-sky-300',
    live: 'border-[#F9C8D4] dark:border-rose-900/60 bg-[#FCE1E8] dark:bg-rose-950/40 text-[#831843] dark:text-rose-300',
    review: 'border-[#FDE68A] dark:border-amber-900/60 bg-[#FEF0C3] dark:bg-amber-950/40 text-[#78350F] dark:text-amber-300',
    approved: 'border-[#BCE1D6] dark:border-teal-900/60 bg-[#D8ECE5] dark:bg-teal-950/40 text-[#134E4A] dark:text-teal-300',
  } as const

  return (
    <div className={cn('relative flex flex-col justify-between overflow-hidden rounded-3xl border p-4 shadow-2xs transition-all hover:shadow-xs interactive-card', tones[tone])}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-2xs font-bold uppercase tracking-wider opacity-80">{label}</p>
        <div className="grid h-7 w-7 place-items-center rounded-full bg-white/80 dark:bg-slate-800/80 shadow-2xs">
          {icon || <span className="text-xs font-bold">↗</span>}
        </div>
      </div>
      <div className="mt-3">
        <p className="mono text-2xl font-bold leading-none">{value}</p>
        {detail ? <p className="mt-1 text-2xs opacity-80 font-medium">{detail}</p> : null}
      </div>
    </div>
  )
}

export function SectionDivider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5">
      <span className="text-2xs font-bold uppercase tracking-wider text-slate-400">{label}</span>
      <span className="h-px flex-1 bg-slate-200" />
    </div>
  )
}

export function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'danger',
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: 'danger' | 'primary'
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-sm rounded-3xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-raised animate-scale-spring text-slate-900 dark:text-slate-100">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'grid h-10 w-10 shrink-0 place-items-center rounded-2xl',
              tone === 'danger' ? 'bg-[#FCE1E8] dark:bg-rose-950/60 text-[#831843] dark:text-rose-400' : 'bg-[#D8ECE5] dark:bg-teal-950/60 text-[#134E4A] dark:text-teal-400',
            )}
          >
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">{title}</h3>
          </div>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-slate-600 dark:text-slate-400">{message}</p>
        <div className="mt-6 flex items-center justify-end gap-2.5">
          <button
            type="button"
            disabled={busy}
            onClick={onCancel}
            className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onConfirm}
            className={cn(
              'rounded-2xl px-4 py-2 text-xs font-bold text-white shadow-xs transition-colors',
              tone === 'danger' ? 'bg-[#DC2626] hover:bg-[#B91C1C]' : 'bg-[#18181B] hover:bg-[#27272A]',
            )}
          >
            {busy ? 'Deleting…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
