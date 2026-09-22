import { useEffect, useState } from 'react'
import { Check, Copy, FileText, Link2, Mic, Pencil, ShieldAlert, X } from 'lucide-react'

import { EmptyState, InlineAlert, Panel } from '@/components/ui/primitives'
import { VitalsDictationModal } from './VitalsDictationModal'
import {
  ENTITY_STATUS_LABELS,
  ENTITY_STATUS_STYLES,
  MOM_SECTION_LABELS,
  NOTE_STATUS_LABELS,
  NOTE_STATUS_STYLES,
  SECTION_HINTS,
  SECTION_LABELS,
  SECTION_ORDER,
} from '@/constants'
import type { ClinicalEntity, ClinicalNote, ClinicalSection, EntityGroupKey, NoteSectionKey } from '@/types'
import { cn } from '@/utils/cn'
import { formatRelative } from '@/utils/format'

const ENTITY_GROUP_TITLES: Record<EntityGroupKey, string> = {
  symptoms: 'Symptoms',
  medications: 'Medications',
  findings: 'Physical Examination Findings',
  investigations: 'Investigations',
}

interface Props {
  note: ClinicalNote | null
  changedSections: string[]
  editable?: boolean
  isMeeting?: boolean
  encounterType?: string
  onShowSource: (targetKey: string, statement: string) => void
  onSaveSection?: (section: NoteSectionKey, text: string) => Promise<void>
  actions?: React.ReactNode
}

const UNDOCUMENTED_PHRASES = new Set([
  'not mentioned',
  'not found',
  'not stated',
  'not discussed',
  'none mentioned',
  'not available',
  'n/a',
  'na',
  'none',
  'unknown',
])

function isDocumented(section: ClinicalSection | undefined) {
  const text = (section?.text ?? '').trim()
  if (!text) return false
  return !UNDOCUMENTED_PHRASES.has(text.toLowerCase())
}

export function ClinicalNotePanel({
  note,
  changedSections,
  editable = false,
  isMeeting = false,
  encounterType,
  onShowSource,
  onSaveSection,
  actions,
}: Props) {
  const [copied, setCopied] = useState(false)
  const [vitalsModalOpen, setVitalsModalOpen] = useState(false)
  const meetingMode = isMeeting || encounterType === 'MEETING' || encounterType === 'MDT'
  const sectionLabels = meetingMode ? MOM_SECTION_LABELS : SECTION_LABELS
  const panelTitle = meetingMode ? 'Minutes of Meeting (MoM)' : 'Ambulatory Care Clinical Notes'

  const handleAddVitals = async (vitalsSummary: string, medsSummary: string) => {
    if (!onSaveSection || !note) return
    const content = note.content
    if (vitalsSummary) {
      const rawExisting = (content.physical_examination?.text || '').trim()
      const isPlaceholder = !rawExisting || rawExisting.toLowerCase() === 'not mentioned' || rawExisting.toLowerCase().startsWith('not mentioned')
      const vitalsText = vitalsSummary.toLowerCase().startsWith('vital signs:') ? vitalsSummary : `Vital signs: ${vitalsSummary}`
      const updated = isPlaceholder ? vitalsText : `${rawExisting}. ${vitalsText}`
      await onSaveSection('physical_examination', updated)
    }
    if (medsSummary) {
      const rawExisting = (content.current_medication?.text || '').trim()
      const isPlaceholder = !rawExisting || rawExisting.toLowerCase() === 'not mentioned' || rawExisting.toLowerCase().startsWith('not mentioned')
      const updated = isPlaceholder ? medsSummary : `${rawExisting}. ${medsSummary}`
      await onSaveSection('current_medication', updated)
    }
  }

  if (!note) {
    return (
      <Panel title={panelTitle} icon={<FileText className="h-3.5 w-3.5 text-teal-600" aria-hidden />}>
        <EmptyState
          title={meetingMode ? 'No meeting minutes generated yet' : 'No note generated yet'}
          detail={
            meetingMode
              ? 'Meeting minutes and action items draft in real time as the discussion proceeds.'
              : 'The clinical note drafts in real time as the consultation proceeds.'
          }
        />
      </Panel>
    )
  }

  const content = note.content
  const flagged = note.review_flags ?? []
  const visibleSections = SECTION_ORDER.filter((key) => isDocumented(content[key]))
  const visibleGroups = (Object.keys(ENTITY_GROUP_TITLES) as EntityGroupKey[])
    .map((groupKey) => ({ groupKey, entities: content[groupKey] ?? [] }))
    .filter((group) => group.entities.length > 0)

  const copyNote = async () => {
    const lines: string[] = []
    lines.push(meetingMode ? 'MINUTES OF MEETING (MoM)' : 'AMBULATORY CARE CLINICAL NOTES')
    lines.push(`Status: ${NOTE_STATUS_LABELS[note.status]}`)
    if (note.approved_by) lines.push(`Approved by: ${note.approved_by}`)
    lines.push('----------------------------------------\n')

    for (const key of SECTION_ORDER) {
      const section = content[key]
      if (isDocumented(section)) {
        lines.push(`${(sectionLabels[key] || SECTION_LABELS[key]).toUpperCase()}:`)
        lines.push(`${section.text}\n`)
      }
    }

    for (const groupKey of Object.keys(ENTITY_GROUP_TITLES) as EntityGroupKey[]) {
      const entities = content[groupKey] ?? []
      if (entities.length > 0) {
        lines.push(`${ENTITY_GROUP_TITLES[groupKey].toUpperCase()}:`)
        lines.push(entities.map((e) => `- ${e.normalized_value ? e.normalized_value : e.value}${e.detail ? ` (${e.detail})` : ''}`).join('\n'))
        lines.push('')
      }
    }

    try {
      await navigator.clipboard.writeText(lines.join('\n'))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {}
  }

  return (
    <>
      <Panel
        title={panelTitle}
        icon={<FileText className="h-3.5 w-3.5 text-teal-600" aria-hidden />}
        actions={
          <>
            {actions}
            {!meetingMode && editable && onSaveSection ? (
              <button
                type="button"
                onClick={() => setVitalsModalOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-teal-200 dark:border-teal-800 bg-teal-50 dark:bg-teal-950/60 px-2.5 py-1 text-2xs font-semibold text-teal-800 dark:text-teal-300 shadow-2xs hover:bg-teal-100 dark:hover:bg-teal-900/60 transition-all"
                title="Dictate or add patient vitals & medications"
              >
                <Mic className="h-3 w-3 text-teal-700 dark:text-teal-400" aria-hidden />
                <span>Dictate Vitals & Meds</span>
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => void copyNote()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2.5 py-1 text-2xs font-semibold text-slate-700 dark:text-slate-200 shadow-2xs transition-all hover:border-teal-500 hover:text-teal-700 dark:hover:border-teal-400 dark:hover:text-teal-300"
              title="Copy clinical note to clipboard"
            >
              {copied ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3 text-slate-500 dark:text-slate-400" />}
              {copied ? 'Copied' : 'Copy Note'}
            </button>
            <span className={cn('badge rounded-full px-2.5 py-0.5 text-2xs font-semibold shadow-2xs', NOTE_STATUS_STYLES[note.status])}>
              {NOTE_STATUS_LABELS[note.status]}
            </span>
          </>
        }
      >
        <div className="space-y-3 p-3.5">
          <div className="flex flex-wrap items-center justify-between text-2xs text-slate-400 dark:text-slate-500">
            <span>Updated {formatRelative(note.updated_at)}</span>
            {note.approved_by ? <span className="font-medium text-teal-700 dark:text-teal-400">Signed by {note.approved_by}</span> : null}
          </div>

          {flagged.length > 0 ? (
            <InlineAlert kind="warning" title={`${flagged.length} item(s) require review`}>
              <ul className="mt-1 space-y-0.5">
                {flagged.map((flag) => (
                  <li key={`${flag.section}-${flag.reason}`}>
                    <span className="font-semibold">{flag.label}:</span> {flag.reason}
                  </li>
                ))}
              </ul>
            </InlineAlert>
          ) : null}

          {visibleSections.map((key) => (
            <NoteSection
              key={key}
              sectionKey={key}
              section={content[key]}
              changed={changedSections.includes(key)}
              editable={editable}
              onShowSource={onShowSource}
              onSave={onSaveSection}
            />
          ))}

          {visibleGroups.map((group) => (
            <EntityGroup
              key={group.groupKey}
              title={ENTITY_GROUP_TITLES[group.groupKey]}
              entities={group.entities}
              onShowSource={onShowSource}
            />
          ))}

          {visibleSections.length === 0 && visibleGroups.length === 0 ? (
            <EmptyState title="Nothing documented yet" detail="Sections will automatically appear as discussion topics are mentioned." />
          ) : null}
        </div>
      </Panel>

      <VitalsDictationModal
        open={vitalsModalOpen}
        onClose={() => setVitalsModalOpen(false)}
        onAddVitals={handleAddVitals}
      />
    </>
  )
}

function NoteSection({
  sectionKey,
  section,
  changed,
  editable,
  onShowSource,
  onSave,
}: {
  sectionKey: NoteSectionKey
  section: ClinicalSection | undefined
  changed: boolean
  editable: boolean
  onShowSource: (targetKey: string, statement: string) => void
  onSave?: (section: NoteSectionKey, text: string) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(section?.text ?? '')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!editing) setDraft(section?.text ?? '')
  }, [section?.text, editing])

  if (!section) return null
  const evidenceCount = section.evidence?.length ?? 0
  const needsReview = section.review_required

  const save = async () => {
    if (!onSave) return
    setSaving(true)
    try {
      await onSave(sectionKey, draft.trim())
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <article
      className={cn(
        'overflow-hidden rounded-xl border bg-white dark:bg-slate-900 shadow-2xs transition-all duration-150',
        needsReview
          ? 'border-amber-300 dark:border-amber-700 ring-1 ring-amber-200 dark:ring-amber-900/40'
          : 'border-slate-200/80 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700',
        changed && 'ring-2 ring-teal-500/30',
      )}
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/60 px-3.5 py-2">
        <h3 className="text-2xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
          {SECTION_LABELS[sectionKey]}
        </h3>
        {section.edited_by_human ? (
          <span className="badge rounded-full border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-2xs text-slate-600 dark:text-slate-300">
            Edited
          </span>
        ) : null}
        {needsReview ? (
          <span className="badge rounded-full border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/60 px-2 py-0.5 text-2xs font-semibold text-amber-800 dark:text-amber-300">
            <ShieldAlert className="h-3 w-3" aria-hidden /> Review
          </span>
        ) : null}
        <span className="ml-auto flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => onShowSource(sectionKey, section.text)}
            aria-label={`Show source for ${SECTION_LABELS[sectionKey]}`}
            className="inline-flex items-center gap-1 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-0.5 text-2xs font-semibold text-slate-600 dark:text-slate-300 shadow-2xs hover:border-teal-400 hover:text-teal-700 dark:hover:text-teal-300"
          >
            <Link2 className="h-3 w-3" aria-hidden />
            Sources ({evidenceCount})
          </button>
          {editable ? (
            editing ? (
              <span className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => void save()}
                  disabled={saving}
                  className="inline-flex items-center gap-1 rounded-md border border-teal-600 bg-teal-600 px-2 py-0.5 text-2xs font-semibold text-white shadow-2xs disabled:opacity-60"
                >
                  <Check className="h-3 w-3" aria-hidden />
                  Save
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setEditing(false)
                    setDraft(section.text)
                  }}
                  className="inline-flex items-center rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-1.5 py-0.5 text-2xs font-semibold text-slate-600 dark:text-slate-300"
                >
                  <X className="h-3 w-3" aria-hidden />
                </button>
              </span>
            ) : (
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="inline-flex items-center gap-1 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-0.5 text-2xs font-semibold text-slate-600 dark:text-slate-300 shadow-2xs hover:border-slate-300 dark:hover:border-slate-600"
              >
                <Pencil className="h-3 w-3 text-slate-400" aria-hidden />
                Edit
              </button>
            )
          ) : null}
        </span>
      </header>

      <div className="p-3.5">
        {editing ? (
          <>
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={4}
              className="field-input font-normal dark:bg-slate-950 dark:border-slate-700 dark:text-slate-100"
              aria-label={`Edit ${SECTION_LABELS[sectionKey]}`}
            />
            <p className="mt-1.5 text-2xs text-slate-500 dark:text-slate-400">{SECTION_HINTS[sectionKey]}</p>
          </>
        ) : isDocumented(section) ? (
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800 dark:text-slate-200 font-normal">{section.text}</p>
        ) : (
          <p className="text-xs text-slate-400 dark:text-slate-500 italic font-normal">— Not discussed in consultation —</p>
        )}
        {needsReview && section.review_reason ? (
          <p className="mt-2 text-2xs font-medium text-amber-700 dark:text-amber-400">{section.review_reason}</p>
        ) : null}
      </div>
    </article>
  )
}

function EntityGroup({
  title,
  entities,
  onShowSource,
}: {
  title: string
  entities: ClinicalEntity[]
  onShowSource: (targetKey: string, statement: string) => void
}) {
  return (
    <article className="overflow-hidden rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xs">
      <header className="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/60 px-3.5 py-2">
        <h3 className="text-2xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">{title}</h3>
        <span className="mono ml-auto text-2xs font-semibold text-slate-400 dark:text-slate-500">{entities.length}</span>
      </header>
      <div className="p-3.5">
        <ul className="space-y-1.5">
          {entities.map((entity) => (
            <li key={entity.ref} className="flex flex-wrap items-center gap-2 text-xs">
              <span className={cn('badge rounded-full px-2 py-0.5 text-2xs font-semibold', ENTITY_STATUS_STYLES[entity.status])}>
                {ENTITY_STATUS_LABELS[entity.status]}
              </span>
              <span className="font-semibold text-slate-900 dark:text-slate-100">
                {entity.normalized_value ? entity.normalized_value : entity.value}
              </span>
              {entity.normalized_value && entity.normalized_value.toLowerCase() !== entity.value.toLowerCase() ? (
                <span className="text-2xs text-slate-400 dark:text-slate-500 italic">(&ldquo;{entity.value}&rdquo;)</span>
              ) : null}
              {entity.detail ? <span className="text-slate-500 dark:text-slate-400">— {entity.detail}</span> : null}
              <button
                type="button"
                onClick={() => onShowSource(entity.ref, entity.value)}
                className="ml-auto inline-flex items-center gap-1 text-2xs font-medium text-slate-400 hover:text-teal-700 dark:hover:text-teal-400"
              >
                <Link2 className="h-3 w-3" aria-hidden />
                Sources
              </button>
            </li>
          ))}
        </ul>
      </div>
    </article>
  )
}
