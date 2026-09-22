import { useEffect, useMemo, useRef } from 'react'
import { MessageSquare, Layers, Radio, Sparkles } from 'lucide-react'

import { EmptyState, Panel, StatusDot } from '@/components/ui/primitives'
import { ROLE_STYLES } from '@/constants'
import type { EvidenceLink, Speaker, TranscriptSegment } from '@/types'
import { cn } from '@/utils/cn'
import { formatSpeakerDisplayName, formatTimestamp } from '@/utils/format'

interface Props {
  segments: TranscriptSegment[]
  speakers: Speaker[]
  evidence: EvidenceLink[]
  selectedRef: string | null
  highlightedRefs: string[]
  live: boolean
  onSelect: (ref: string | null) => void
  actions?: React.ReactNode
}

export function TranscriptPanel({
  segments,
  speakers,
  evidence,
  selectedRef,
  highlightedRefs,
  live,
  onSelect,
  actions,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const pinnedToBottom = useRef(true)

  const evidenceCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const link of evidence) {
      if (!link.segment_ref) continue
      counts.set(link.segment_ref, (counts.get(link.segment_ref) ?? 0) + 1)
    }
    return counts
  }, [evidence])

  // Auto-follow the live feed, but stop fighting the user once they scroll up.
  useEffect(() => {
    const node = scrollRef.current
    if (!node || !pinnedToBottom.current) return
    node.scrollTop = node.scrollHeight
  }, [segments.length])

  const handleScroll = () => {
    const node = scrollRef.current
    if (!node) return
    pinnedToBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 48
  }

  const highlighted = new Set(highlightedRefs)

  return (
    <Panel
      title="Conversation Transcript"
      icon={<MessageSquare className="h-3.5 w-3.5 text-teal-600" aria-hidden />}
      actions={
        <>
          {actions}
          <span className="mono flex items-center gap-1 text-2xs text-slate-500">
            <Layers className="h-3 w-3" aria-hidden />
            {segments.length} lines
          </span>
          {live ? (
            <span className="flex items-center gap-1 text-2xs font-semibold uppercase tracking-wide text-rose-600">
              <StatusDot className="bg-rose-500" pulse />
              Live
            </span>
          ) : null}
        </>
      }
      bodyClassName="bg-slate-50/40 dark:bg-slate-950/40 p-3"
    >
      <div ref={scrollRef} onScroll={handleScroll} className="h-full overflow-y-auto space-y-2.5 pr-1">
        {segments.length === 0 ? (
          <EmptyState
            icon={<Radio className="h-6 w-6" aria-hidden />}
            title="Waiting for speech"
            detail="Transcript will appear in real time as the doctor and patient speak."
          />
        ) : (
          <ol className="space-y-2.5">
            {segments.map((segment) => {
              const role = ROLE_STYLES[segment.role] ?? ROLE_STYLES.UNKNOWN
              const isSelected = selectedRef === segment.ref
              const isHighlighted = highlighted.has(segment.ref)
              const evidenceCount = evidenceCounts.get(segment.ref) ?? 0
              const speaker = speakers.find((s) => s.label === segment.speaker_label)
              const speakerInfo = formatSpeakerDisplayName(segment.speaker_label, segment.role, speaker?.display_name)

              return (
                <li key={segment.ref}>
                  <button
                    type="button"
                    onClick={() => onSelect(isSelected ? null : segment.ref)}
                    className={cn(
                      'group flex w-full flex-col gap-1.5 rounded-2xl border p-3 text-left transition-all duration-150',
                      isSelected
                        ? 'border-teal-500 dark:border-teal-400 bg-teal-50/90 dark:bg-teal-950/60 shadow-sm ring-1 ring-teal-500/20'
                        : isHighlighted
                          ? 'border-amber-400 dark:border-amber-600 bg-amber-50/80 dark:bg-amber-950/50 shadow-xs'
                          : 'border-slate-200/70 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700 hover:shadow-xs',
                    )}
                    aria-current={isSelected}
                  >
                    <div className="flex items-center gap-2">
                      <span className={cn('badge rounded-full px-2.5 py-0.5 font-bold text-2xs shadow-2xs tracking-normal', role.badge)}>
                        {speakerInfo.fullBadge}
                      </span>
                      <span className="mono text-2xs text-slate-400 dark:text-slate-500 font-medium">
                        {formatTimestamp(segment.start_time)}
                      </span>
                      <span className="ml-auto flex items-center gap-1.5">
                        {evidenceCount > 0 ? (
                          <span className="inline-flex items-center gap-1 rounded-full border border-teal-200 dark:border-teal-800 bg-teal-50 dark:bg-teal-950/60 px-2 py-0.5 text-2xs font-semibold text-teal-700 dark:text-teal-300">
                            <Sparkles className="h-2.5 w-2.5" />
                            {evidenceCount} cited
                          </span>
                        ) : null}
                      </span>
                    </div>
                    <p className="text-sm leading-relaxed text-slate-800 dark:text-slate-200 font-normal pl-0.5">{segment.text}</p>
                  </button>
                </li>
              )
            })}
          </ol>
        )}
      </div>
    </Panel>
  )
}
