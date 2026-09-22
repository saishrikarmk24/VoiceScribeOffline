import { CircleStop, Cpu, Mic, MicOff, Pause, Play, RefreshCw, Wifi, WifiOff } from 'lucide-react'

import { StatusDot } from '@/components/ui/primitives'
import type { ConnectionState } from '@/services/socket'
import type { AiStatus, Session } from '@/types'
import { cn } from '@/utils/cn'
import { formatTimestamp } from '@/utils/format'

interface Props {
  session: Session
  elapsed: number
  connection: ConnectionState
  ai: AiStatus | null
  audioActive: boolean
  audioLabel: string
  busy: boolean
  onPause: () => void
  onResume: () => void
  onStop: () => void
  onRetryAi: () => void
}

export function SessionBar({
  session,
  elapsed,
  connection,
  ai,
  audioActive,
  audioLabel,
  busy,
  onPause,
  onResume,
  onStop,
  onRetryAi,
}: Props) {
  const isLive = session.status === 'LIVE'
  const isPaused = session.status === 'PAUSED'
  const canEnd = ['LIVE', 'PAUSED', 'PROCESSING'].includes(session.status)

  const aiLabel = !ai
    ? 'AI Scribe: Ready'
    : ai.mock
      ? 'AI Scribe: Local Demo'
      : ai.degraded
        ? 'AI Scribe: Degraded'
        : 'AI Scribe: Active'
  const aiOk = Boolean(ai && !ai.degraded)

  return (
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-slate-800 bg-slate-950 px-4 py-2.5 text-white shadow-sm">
      <div className="flex items-center gap-3">
        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-2xs font-semibold uppercase tracking-wider',
            isLive
              ? 'bg-rose-500/20 text-rose-300 ring-1 ring-rose-500/40'
              : isPaused
                ? 'bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/40'
                : 'bg-slate-800 text-slate-300',
          )}
        >
          <StatusDot className={isLive ? 'bg-rose-400' : isPaused ? 'bg-amber-400' : 'bg-slate-400'} pulse={isLive} />
          {session.status}
        </span>
        <div className="leading-tight">
          <div className="flex items-center gap-2">
            <span className="mono text-xs font-bold text-white">{session.reference}</span>
            <span className="text-2xs text-slate-500">·</span>
            <span className="text-xs font-medium text-slate-300">Pt. {session.patient_id}</span>
          </div>
          <p className="max-w-[16rem] truncate text-2xs text-slate-400">{session.name}</p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <p className="mono text-2xl font-bold tabular-nums tracking-tight text-white" aria-label="Session timer">
          {formatTimestamp(elapsed)}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-slate-300">
        <span className="flex items-center gap-1.5" title={`Audio source: ${audioLabel}`}>
          {audioActive ? (
            <Mic className="h-3.5 w-3.5 text-teal-400 animate-pulse" aria-hidden />
          ) : (
            <MicOff className="h-3.5 w-3.5 text-slate-500" aria-hidden />
          )}
          <span>{audioActive ? 'Mic Active' : 'Mic Idle'}</span>
        </span>
        <span className="flex items-center gap-1.5" title={aiLabel}>
          <Cpu className={cn('h-3.5 w-3.5', aiOk ? 'text-teal-400' : 'text-amber-400')} aria-hidden />
          {aiLabel}
        </span>
        <span className="flex items-center gap-1.5">
          {connection === 'open' ? (
            <Wifi className="h-3.5 w-3.5 text-teal-400" aria-hidden />
          ) : (
            <WifiOff className="h-3.5 w-3.5 text-amber-400" aria-hidden />
          )}
          {connection === 'open' ? 'Live Synced' : connection === 'reconnecting' ? 'Reconnecting…' : connection}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onRetryAi}
          disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/20 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-white/10 disabled:opacity-50 transition"
          title="Force a clinical structuring pass now"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden />
          Refresh Note
        </button>
        {isLive ? (
          <button
            type="button"
            onClick={onPause}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/20 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-white/10 disabled:opacity-50 transition"
          >
            <Pause className="h-3.5 w-3.5" aria-hidden />
            Pause
          </button>
        ) : null}
        {isPaused ? (
          <button
            type="button"
            onClick={onResume}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg border border-teal-500 bg-teal-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-teal-500 disabled:opacity-50 transition"
          >
            <Play className="h-3.5 w-3.5" aria-hidden />
            Resume
          </button>
        ) : null}
        <button
          type="button"
          onClick={onStop}
          disabled={busy || !canEnd}
          className="inline-flex items-center gap-1.5 rounded-lg border border-rose-600 bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-rose-500 disabled:opacity-50 transition"
        >
          <CircleStop className="h-3.5 w-3.5" aria-hidden />
          End Encounter & Review
        </button>
      </div>
    </header>
  )
}
