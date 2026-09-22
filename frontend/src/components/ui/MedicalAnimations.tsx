import React from 'react'
import { cn } from '@/utils/cn'

interface MedicalPulseLoaderProps {
  label?: string
  sublabel?: string
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

export const MedicalPulseLoader: React.FC<MedicalPulseLoaderProps> = ({
  label = 'Processing Consultation...',
  sublabel = 'Synthesizing clinical documentation & entities',
  className,
  size = 'md',
}) => {
  const isSmall = size === 'sm'
  const isLarge = size === 'lg'

  return (
    <div className={cn('flex flex-col items-center justify-center p-6 text-center select-none', className)}>
      {/* Animated Cardiac Monitor Container */}
      <div className="relative flex items-center justify-center mb-4">
        {/* Breathing ambient glow ring */}
        <div className="absolute inset-0 -m-3 rounded-full bg-teal-500/15 blur-xl animate-pulse-dot" />

        {/* Outer Circular Ring */}
        <div
          className={cn(
            'relative rounded-full border border-teal-500/30 bg-slate-950/80 backdrop-blur-md flex items-center justify-center overflow-hidden shadow-lg shadow-teal-500/10',
            isSmall ? 'w-12 h-12' : isLarge ? 'w-24 h-24' : 'w-18 h-18 px-3 py-3',
          )}
        >
          {/* Animated SVG ECG Waveform */}
          <svg
            className={cn('text-teal-400', isSmall ? 'w-8 h-8' : isLarge ? 'w-16 h-16' : 'w-12 h-12')}
            viewBox="0 0 100 40"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            {/* Background grid line */}
            <line x1="0" y1="20" x2="100" y2="20" stroke="currentColor" strokeOpacity="0.15" strokeWidth="1" />
            {/* ECG trace line */}
            <path
              d="M0 20 L25 20 L32 10 L38 32 L44 5 L50 28 L56 16 L62 20 L100 20"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="animate-pulse"
            />
          </svg>

          {/* Sweeping scanline dot */}
          <span className="absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-teal-300 shadow-[0_0_8px_#2dd4bf] animate-ping opacity-75" />
        </div>
      </div>

      {/* Label and sublabel */}
      {label && <p className="text-xs font-bold tracking-tight text-slate-800 dark:text-slate-200">{label}</p>}
      {sublabel && <p className="text-2xs text-slate-500 max-w-xs mt-1 leading-relaxed">{sublabel}</p>}
    </div>
  )
}

/**
 * Animated audio equalizer bars for active microphone capture or dictation.
 */
export const AudioEqualizerBars: React.FC<{ active?: boolean; className?: string }> = ({
  active = true,
  className,
}) => {
  return (
    <div className={cn('flex items-center gap-0.5 h-5 px-1', className)}>
      <span
        className={cn(
          'w-1 bg-teal-500 rounded-full transition-all duration-150',
          active ? 'animate-equalizer-1' : 'h-1.5 opacity-40',
        )}
      />
      <span
        className={cn(
          'w-1 bg-teal-400 rounded-full transition-all duration-150',
          active ? 'animate-equalizer-2' : 'h-2 opacity-40',
        )}
      />
      <span
        className={cn(
          'w-1 bg-emerald-400 rounded-full transition-all duration-150',
          active ? 'animate-equalizer-3' : 'h-1.5 opacity-40',
        )}
      />
      <span
        className={cn(
          'w-1 bg-teal-500 rounded-full transition-all duration-150',
          active ? 'animate-equalizer-4' : 'h-1 opacity-40',
        )}
      />
    </div>
  )
}

/**
 * Animated wrapper for tab panels so switching tabs feels tactile and fluid.
 */
export const TabTransition: React.FC<{
  tabKey: string | number
  children: React.ReactNode
  direction?: 'horizontal' | 'vertical'
  className?: string
}> = ({ tabKey, children, direction = 'vertical', className }) => {
  return (
    <div
      key={tabKey}
      className={cn(
        direction === 'vertical' ? 'animate-fade-in-up' : 'animate-tab-slide',
        'will-change-transform',
        className,
      )}
    >
      {children}
    </div>
  )
}

/**
 * Skeleton placeholder for loading cards and clinical summaries.
 */
export const SkeletonCard: React.FC<{ className?: string }> = ({ className }) => {
  return (
    <div className={cn('rounded-3xl border border-slate-200/80 bg-white p-5 shadow-xs overflow-hidden', className)}>
      <div className="flex items-center justify-between mb-4">
        <div className="h-4 w-32 rounded-lg shimmer-skeleton" />
        <div className="h-6 w-16 rounded-full shimmer-skeleton" />
      </div>
      <div className="space-y-2.5">
        <div className="h-3 w-full rounded shimmer-skeleton" />
        <div className="h-3 w-5/6 rounded shimmer-skeleton" />
        <div className="h-3 w-4/6 rounded shimmer-skeleton" />
      </div>
      <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between">
        <div className="h-3 w-20 rounded shimmer-skeleton" />
        <div className="h-4 w-24 rounded-lg shimmer-skeleton" />
      </div>
    </div>
  )
}

/**
 * Animated Beacon Indicator with breathing ping rings.
 */
export const StatusBeacon: React.FC<{
  variant?: 'teal' | 'rose' | 'amber' | 'emerald'
  pulse?: boolean
  className?: string
}> = ({ variant = 'teal', pulse = true, className }) => {
  const colorMap = {
    teal: { dot: 'bg-teal-500', ping: 'bg-teal-400' },
    rose: { dot: 'bg-rose-500', ping: 'bg-rose-400' },
    amber: { dot: 'bg-amber-500', ping: 'bg-amber-400' },
    emerald: { dot: 'bg-emerald-500', ping: 'bg-emerald-400' },
  }
  const { dot, ping } = colorMap[variant]

  return (
    <span className={cn('relative flex h-2.5 w-2.5 shrink-0', className)}>
      {pulse && <span className={cn('absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping', ping)} />}
      <span className={cn('relative inline-flex rounded-full h-2.5 w-2.5', dot)} />
    </span>
  )
}
