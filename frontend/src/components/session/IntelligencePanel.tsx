import { useMemo } from 'react'
import { Activity, Brain, Link2 } from 'lucide-react'

import { EmptyState, Panel } from '@/components/ui/primitives'
import {
  ENTITY_GROUPS,
  ENTITY_STATUS_LABELS,
  ENTITY_STATUS_STYLES,
} from '@/constants'
import type { ClinicalEntity, ProcessingStage } from '@/types'
import { cn } from '@/utils/cn'
import { titleCase } from '@/utils/format'

interface Props {
  entities: ClinicalEntity[]
  stage: ProcessingStage
  stageDetail: string
  onShowSource: (targetKey: string, statement: string) => void
}

export function IntelligencePanel({ entities, stage, stageDetail, onShowSource }: Props) {
  const grouped = useMemo(() => {
    return ENTITY_GROUPS.map((group) => ({
      title: group.title,
      items: entities.filter((entity) => group.key.includes(entity.entity_type)),
    })).filter((group) => group.items.length > 0)
  }, [entities])

  const isWorking = stage !== 'IDLE' && stage !== 'NOTE_STATE' && Boolean(stage)

  return (
    <Panel title="Clinical Findings" icon={<Brain className="h-3.5 w-3.5 text-teal-600" aria-hidden />}>
      <div className="space-y-3 p-3.5">
        {/* Clinician status indicator */}
        <div
          className={cn(
            'rounded-xl border p-3 transition-all duration-150',
            isWorking
              ? 'border-teal-200 dark:border-teal-800 bg-teal-50/80 dark:bg-teal-950/60 text-teal-950 dark:text-teal-200 shadow-2xs'
              : 'border-slate-200/80 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/60 text-slate-700 dark:text-slate-200',
          )}
        >
          <div className="flex items-center gap-2.5">
            <span className="relative flex h-2.5 w-2.5">
              {isWorking ? (
                <>
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal-400 opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-teal-600" />
                </>
              ) : (
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold">
                {isWorking ? 'Listening & Structuring' : 'Scribe Ready'}
              </p>
              <p className="truncate text-2xs text-slate-500 dark:text-slate-400">
                {isWorking
                  ? stageDetail || 'Extracting clinical facts in real time...'
                  : 'Clinical facts linked to transcript'}
              </p>
            </div>
            {isWorking ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-teal-100 dark:bg-teal-900/60 px-2 py-0.5 text-2xs font-semibold text-teal-800 dark:text-teal-300">
                <Activity className="h-3 w-3 animate-pulse" />
                Active
              </span>
            ) : null}
          </div>
        </div>

        {entities.length === 0 ? (
          <EmptyState
            title="Listening for clinical facts"
            detail="Symptoms, medications, allergies, and examination findings will automatically appear here as they are discussed."
          />
        ) : (
          grouped.map((group) => (
            <section key={group.title} className="overflow-hidden rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xs">
              <header className="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/60 px-3.5 py-2">
                <h3 className="text-2xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">{group.title}</h3>
                <span className="mono ml-auto text-2xs font-semibold text-teal-700 dark:text-teal-400 bg-teal-50 dark:bg-teal-950/60 px-2 py-0.5 rounded-full border border-teal-100/80 dark:border-teal-800">
                  {group.items.length}
                </span>
              </header>
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {group.items.map((entity) => (
                  <li key={entity.ref} className="px-3.5 py-2 hover:bg-slate-50/40 dark:hover:bg-slate-800/40 transition-colors">
                    <div className="flex items-center gap-2">
                      <span className={cn('badge rounded-full px-2 py-0.5 text-2xs font-semibold', ENTITY_STATUS_STYLES[entity.status])}>
                        {ENTITY_STATUS_LABELS[entity.status]}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-xs font-semibold text-slate-900 dark:text-slate-100">
                        {entity.normalized_value ? titleCase(entity.normalized_value) : entity.value}
                      </span>
                      <button
                        type="button"
                        onClick={() => onShowSource(entity.ref, entity.value)}
                        className="inline-flex items-center gap-1 text-2xs font-medium text-slate-400 hover:text-teal-700 dark:hover:text-teal-400"
                        title="View transcript citation"
                        aria-label={`Show source for ${entity.value}`}
                      >
                        <Link2 className="h-3 w-3" aria-hidden />
                        Sources
                      </button>
                    </div>
                    <div className="mt-0.5 flex items-center gap-2">
                      <span className="text-2xs text-slate-400 font-medium">{titleCase(entity.entity_type)}</span>
                      {entity.normalized_value && entity.normalized_value.toLowerCase() !== entity.value.toLowerCase() ? (
                        <span className="truncate text-2xs text-slate-400 italic">Spoken: &ldquo;{entity.value}&rdquo;</span>
                      ) : null}
                      {entity.detail ? (
                        <span className="truncate text-2xs text-slate-500">— {entity.detail}</span>
                      ) : null}
                    </div>
                    {entity.review_required ? (
                      <p className="mt-1 text-2xs font-medium text-amber-700">{entity.review_reason ?? 'Review required'}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </div>
    </Panel>
  )
}
