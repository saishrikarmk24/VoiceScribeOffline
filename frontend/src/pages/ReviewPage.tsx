import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  BadgeCheck,
  CheckCircle2,
  FileText,
  History,
  Info,
  Link2,
  ListFilter,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react'

import { ClinicalNotePanel } from '@/components/session/ClinicalNotePanel'
import { EvidenceViewer } from '@/components/session/EvidenceViewer'
import { SpeakerRoster } from '@/components/session/SpeakerRoster'
import { TranscriptPanel } from '@/components/session/TranscriptPanel'
import { EmptyState, InlineAlert, Spinner } from '@/components/ui/primitives'
import { MedicalPulseLoader, TabTransition } from '@/components/ui/MedicalAnimations'
import { ENTITY_STATUS_LABELS, ENTITY_STATUS_STYLES } from '@/constants'
import { api, downloadBlob } from '@/services/api'
import { useSessionStore } from '@/store/sessionStore'
import { useUiStore } from '@/store/uiStore'
import type { ExportFormat, NoteSectionKey, NoteVersion } from '@/types'
import { cn } from '@/utils/cn'
import { formatDateTime, formatDuration, formatTimestamp, titleCase } from '@/utils/format'

type SidebarTab = 'entities' | 'evidence' | 'versions' | 'info'

export function ReviewPage() {
  const { id } = useParams<{ id: string }>()
  const pushToast = useUiStore((state) => state.pushToast)
  const identityName = useUiStore((state) => state.identityName)

  const {
    session,
    segments,
    speakers,
    entities,
    note,
    evidence,
    selectedSegmentRef,
    evidenceFocus,
    attach,
    detach,
    refresh,
    selectSegment,
    focusEvidence,
    setNote,
  } = useSessionStore()

  const [versions, setVersions] = useState<NoteVersion[]>([])
  const [acknowledged, setAcknowledged] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showApproveModal, setShowApproveModal] = useState(false)
  const [activeTab, setActiveTab] = useState<SidebarTab>('entities')

  useEffect(() => {
    if (!id) return
    attach(id).catch((err: Error) => setError(err.message))
    return () => detach()
  }, [attach, detach, id])

  const loadVersions = useCallback(() => {
    if (!id) return
    api
      .noteVersions(id)
      .then(setVersions)
      .catch(() => setVersions([]))
  }, [id])

  useEffect(loadVersions, [loadVersions, note?.version])

  const stats = useMemo(() => {
    const validated = evidence.filter((link) => link.validated).length
    return { validated, total: evidence.length }
  }, [evidence])

  const highlightedRefs = useMemo(() => {
    if (!evidenceFocus) return []
    return evidence
      .filter((link) => link.target_key === evidenceFocus.targetKey && link.segment_ref)
      .map((link) => link.segment_ref as string)
  }, [evidence, evidenceFocus])

  const saveSection = async (section: NoteSectionKey, text: string) => {
    if (!note) return
    try {
      const updated = await api.editNote(note.id, { [section]: text, editor: identityName })
      setNote(updated)
      pushToast({ kind: 'success', title: 'Section saved', detail: `Note is now version ${updated.version}.` })
      loadVersions()
    } catch (err) {
      pushToast({ kind: 'error', title: 'Could not save section', detail: (err as Error).message })
    }
  }

  const approve = async () => {
    if (!note) return
    setBusy(true)
    try {
      const updated = await api.approveNote(note.id, identityName)
      setNote(updated)
      setShowApproveModal(false)
      await refresh()
      loadVersions()
      pushToast({ kind: 'success', title: 'Note approved & signed', detail: `Signed by ${identityName}.` })
    } catch (err) {
      pushToast({ kind: 'error', title: 'Approval blocked', detail: (err as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const reopen = async () => {
    if (!note) return
    setBusy(true)
    try {
      const updated = await api.reopenNote(note.id)
      setNote(updated)
      setAcknowledged(false)
      await refresh()
      loadVersions()
      pushToast({ kind: 'info', title: 'Note reopened for editing' })
    } catch (err) {
      pushToast({ kind: 'error', title: 'Could not reopen note', detail: (err as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const exportAs = async (format: ExportFormat) => {
    if (!session) return
    setBusy(true)
    try {
      const { blob, filename } = await api.exportSession(session.id, format)
      downloadBlob(blob, filename)
      await refresh()
      pushToast({ kind: 'success', title: `${format} export downloaded`, detail: filename })
    } catch (err) {
      pushToast({ kind: 'error', title: `${format} export failed`, detail: (err as Error).message })
    } finally {
      setBusy(false)
    }
  }

  if (error) {
    return (
      <div className="p-6">
        <InlineAlert kind="error" title="Could not load session">
          {error}
        </InlineAlert>
      </div>
    )
  }

  if (!session || !note) {
    return (
      <div className="flex h-full items-center justify-center p-12">
        <MedicalPulseLoader
          label="Loading Clinical Review Workspace..."
          sublabel="Verifying EHR provenance, ambulatory care narrative, and diagnostic orders"
        />
      </div>
    )
  }

  const flags = note.review_flags ?? []
  const blockingFlags = flags.filter((f) => f.severity === 'ERROR' || f.severity === 'BLOCKING')
  const infoFlags = flags.filter((f) => f.severity === 'INFO' || f.severity === 'WARNING')
  const approvable = note.status === 'DRAFT' || note.status === 'REVIEW_REQUIRED'
  const isApproved = note.status === 'APPROVED' || note.status === 'EXPORTED'

  return (
    <div className="flex h-full min-h-0 flex-col bg-slate-100/60 dark:bg-slate-950 animate-fade-in-up">
      {/* Top Main Header */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-2.5 shadow-sm">
        <div className="flex items-center gap-3">
          <Link to={`/sessions/${session.id}/live`} className="btn-secondary !py-1 text-xs">
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Return to Session
          </Link>
          <div className="h-4 w-px bg-slate-200 dark:bg-slate-800" />
          <div className="leading-tight">
            <div className="flex items-center gap-2">
              <span className="mono text-xs font-bold text-slate-900 dark:text-slate-100">{session.reference}</span>
              <span className="text-2xs font-medium text-slate-500">·</span>
              <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
                {session.patient_name ? `${session.patient_name} (${session.patient_id})` : `Patient ${session.patient_id}`}
              </span>
              <span className="text-2xs font-medium text-slate-500">·</span>
              <span className="text-2xs text-slate-500">{formatDuration(session.duration_seconds)}</span>
            </div>
            <p className="truncate text-2xs text-slate-500">{session.name}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Quick Export Actions */}
          <button
            type="button"
            className="btn-secondary !py-1 text-xs"
            disabled={busy}
            onClick={() => void exportAs('PDF')}
            title="Download formatted clinical PDF note"
          >
            <FileText className="h-3.5 w-3.5 text-rose-600" aria-hidden />
            PDF
          </button>

          {isApproved ? (
            <button
              type="button"
              className="btn-secondary !py-1 text-xs font-medium text-slate-700 dark:text-slate-200"
              disabled={busy}
              onClick={() => void reopen()}
              title="Reopen note for additional clinical edits"
            >
              <RotateCcw className="h-3.5 w-3.5 text-slate-500" aria-hidden />
              Reopen Note
            </button>
          ) : null}
        </div>
      </header>

      {/* Prominent Sticky Clinical Approval Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800 bg-white/95 dark:bg-slate-900/95 px-4 py-2 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          {isApproved ? (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/50 px-3 py-1 text-xs font-semibold text-emerald-800 dark:text-emerald-300 shadow-sm">
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
              Approved & Signed by {note.approved_by ?? identityName}
              <span className="text-2xs font-normal text-emerald-700 dark:text-emerald-400">({formatDateTime(note.approved_at)})</span>
            </span>
          ) : (
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/50 px-2.5 py-1 text-xs font-semibold text-amber-800 dark:text-amber-300">
                <ShieldAlert className="h-3.5 w-3.5 text-amber-600" />
                Pending Doctor Review & Approval
              </span>
              {blockingFlags.length > 0 ? (
                <span className="text-2xs font-medium text-amber-700 dark:text-amber-400">({blockingFlags.length} items flagged)</span>
              ) : (
                <span className="text-2xs text-slate-500">
                  {infoFlags.length > 0 ? 'Clinical edits and vitals preserved · Ready to sign' : 'All statements cited with transcript evidence'}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {!isApproved ? (
            <button
              type="button"
              className="btn-teal flex items-center gap-1.5 shadow-sm text-xs font-semibold px-4 py-1.5 rounded-lg"
              disabled={busy || !approvable || blockingFlags.length > 0}
              onClick={() => setShowApproveModal(true)}
              title={blockingFlags.length > 0 ? 'Resolve blocking review flags before approving' : 'Approve and sign clinical note'}
            >
              <BadgeCheck className="h-4 w-4" aria-hidden />
              Approve & Sign Note
            </button>
          ) : null}
        </div>
      </div>

      {/* Flagged Review Items Alert - Only for genuine blocking errors */}
      {blockingFlags.length > 0 ? (
        <div className="border-b border-amber-200 dark:border-amber-900/60 bg-amber-50 dark:bg-amber-950/40 px-4 py-2 text-xs text-amber-900 dark:text-amber-200">
          <div className="flex items-center gap-2 font-semibold">
            <ShieldAlert className="h-4 w-4 text-amber-600 shrink-0" />
            <span>Items requiring clinical review prior to approval:</span>
          </div>
          <ul className="mt-1 ml-6 list-disc space-y-0.5 text-2xs text-amber-800 dark:text-amber-300">
            {blockingFlags.map((flag) => (
              <li key={`${flag.section}-${flag.reason}`}>
                <span className="font-semibold">{flag.label}:</span> {flag.reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Main 3-Column Workstation Layout */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 p-2 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)_minmax(0,0.85fr)]">
        {/* Col 1: Transcript Panel & Speakers */}
        <div className="flex min-h-0 flex-col gap-2">
          <TranscriptPanel
            segments={segments}
            speakers={speakers}
            evidence={evidence}
            selectedRef={selectedSegmentRef}
            highlightedRefs={highlightedRefs}
            live={false}
            onSelect={selectSegment}
          />
          <SpeakerRoster speakers={speakers} editable={!isApproved} onChanged={() => void refresh()} />
        </div>

        {/* Col 2: Clinical Note with Inline Editing */}
        <ClinicalNotePanel
          note={note}
          encounterType={session.simulation_type}
          changedSections={[]}
          editable={!isApproved}
          onShowSource={(targetKey, statement) => focusEvidence({ targetKey, statement, kind: 'SECTION' })}
          onSaveSection={saveSection}
        />

        {/* Col 3: Tabbed Clinical Insights, Evidence, Versions & Info */}
        <div className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-panel">
          {/* Tabs Navigation */}
          <div className="flex border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950/70 p-1">
            <button
              type="button"
              onClick={() => setActiveTab('entities')}
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-2xs font-semibold transition',
                activeTab === 'entities'
                  ? 'bg-white dark:bg-slate-800 text-teal-700 dark:text-teal-400 shadow-sm'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200',
              )}
            >
              <ListFilter className="h-3 w-3" />
              Facts ({entities.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('evidence')}
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-2xs font-semibold transition',
                activeTab === 'evidence'
                  ? 'bg-white dark:bg-slate-800 text-teal-700 dark:text-teal-400 shadow-sm'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200',
              )}
            >
              <Link2 className="h-3 w-3" />
              Evidence ({stats.validated})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('versions')}
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-2xs font-semibold transition',
                activeTab === 'versions'
                  ? 'bg-white dark:bg-slate-800 text-teal-700 dark:text-teal-400 shadow-sm'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200',
              )}
            >
              <History className="h-3 w-3" />
              History ({versions.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('info')}
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-2xs font-semibold transition',
                activeTab === 'info'
                  ? 'bg-white dark:bg-slate-800 text-teal-700 dark:text-teal-400 shadow-sm'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200',
              )}
            >
              <Info className="h-3 w-3" />
              Encounter
            </button>
          </div>

          {/* Tab Content */}
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            <TabTransition tabKey={activeTab}>
              {activeTab === 'entities' && (
              <div className="space-y-2">
                {entities.length === 0 ? (
                  <EmptyState
                    title="No clinical facts extracted"
                    detail="Structured symptoms, medications, and findings will appear here."
                  />
                ) : (
                  <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                    {entities.map((entity) => (
                      <li key={entity.ref} className="py-1.5">
                        <div className="flex items-center gap-1.5">
                          <span className={cn('badge', ENTITY_STATUS_STYLES[entity.status])}>
                            {ENTITY_STATUS_LABELS[entity.status]}
                          </span>
                          <span className="min-w-0 flex-1 truncate text-xs font-medium text-slate-900 dark:text-slate-100">
                            {entity.value}
                          </span>
                          <button
                            type="button"
                            onClick={() => focusEvidence({ targetKey: entity.ref, statement: entity.value, kind: 'ENTITY' })}
                            className="shrink-0 text-2xs font-semibold text-slate-500 hover:text-teal-700 dark:text-slate-400 dark:hover:text-teal-400"
                            title="View transcript citation"
                          >
                            <Link2 className="h-3 w-3" />
                          </button>
                        </div>
                        <div className="mt-0.5 flex items-center justify-between text-2xs text-slate-500 dark:text-slate-400">
                          <span>{titleCase(entity.entity_type)}</span>
                          {entity.detail ? <span className="text-slate-400 dark:text-slate-500">({entity.detail})</span> : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {activeTab === 'evidence' && (
              <div className="space-y-2">
                {evidence.length === 0 ? (
                  <EmptyState
                    title="No evidence citations"
                    detail="All clinical statements are linked to audio segments."
                  />
                ) : (
                  <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                    {evidence.map((link) => (
                      <li key={link.id}>
                        <button
                          type="button"
                          onClick={() => selectSegment(link.segment_ref)}
                          className="w-full rounded p-1.5 text-left hover:bg-slate-50 dark:hover:bg-slate-800/60 transition"
                        >
                          <div className="flex items-center gap-1.5 text-2xs text-slate-500 dark:text-slate-400">
                            <span className="mono font-semibold text-teal-700 dark:text-teal-400">{link.segment_ref ?? 'citation'}</span>
                            <span>·</span>
                            <span>{formatTimestamp(link.timestamp ?? 0)}</span>
                            {link.validated ? (
                              <span className="ml-auto text-2xs text-emerald-700 dark:text-emerald-400 font-medium flex items-center gap-0.5">
                                <CheckCircle2 className="h-3 w-3" /> Verified
                              </span>
                            ) : null}
                          </div>
                          <p className="mt-0.5 text-xs text-slate-800 dark:text-slate-200 line-clamp-2">{link.clinical_statement}</p>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {activeTab === 'versions' && (
              <div className="space-y-2">
                {versions.length === 0 ? (
                  <EmptyState title="No version history" detail="Edits and AI updates will appear here." />
                ) : (
                  <ol className="divide-y divide-slate-100 dark:divide-slate-800">
                    {versions.map((version) => (
                      <li key={version.id} className="py-2 text-2xs">
                        <div className="flex items-center gap-1.5">
                          <span className="mono font-semibold text-slate-900 dark:text-slate-100">v{version.version}</span>
                          <span className="badge border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                            {version.author_type}
                          </span>
                          <span className="ml-auto text-slate-400 dark:text-slate-500">{formatDateTime(version.created_at)}</span>
                        </div>
                        <p className="mt-1 text-slate-700 dark:text-slate-300">{version.change_summary ?? 'Clinical update'}</p>
                        {version.changed_sections?.length ? (
                          <p className="mono mt-0.5 text-slate-400 dark:text-slate-500">Sections: {version.changed_sections.join(', ')}</p>
                        ) : null}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            )}

            {activeTab === 'info' && (
              <div className="space-y-3">
                <dl className="grid grid-cols-2 gap-x-2 gap-y-2 text-2xs">
                  <Meta label="Patient ID" value={session.patient_id} />
                  <Meta label="Doctor" value={session.doctor_name ?? 'Dr. Clinician'} />
                  <Meta label="Encounter Type" value={session.simulation_type} />
                  <Meta label="Encounter Duration" value={formatDuration(session.duration_seconds)} />
                  <Meta label="Started" value={formatDateTime(session.started_at)} />
                  <Meta label="Ended" value={formatDateTime(session.ended_at)} />
                </dl>
                {session.scenario ? (
                  <div className="rounded bg-slate-50 dark:bg-slate-800/60 p-2 text-2xs">
                    <p className="font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Scenario Context</p>
                    <p className="mt-0.5 text-slate-700 dark:text-slate-300">{session.scenario}</p>
                  </div>
                ) : null}
              </div>
            )}
            </TabTransition>
          </div>
        </div>
      </div>

      {/* 1-Click Doctor Sign-off Modal */}
      {showApproveModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xs p-4">
          <div className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 p-5 shadow-2xl border border-slate-200 dark:border-slate-800 animate-scale-spring">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <div className="flex items-center gap-2 text-teal-700 dark:text-teal-400 font-semibold text-sm">
                <ShieldCheck className="h-5 w-5 text-teal-600 dark:text-teal-400" />
                Sign & Finalize Clinical Note
              </div>
              <button
                type="button"
                onClick={() => setShowApproveModal(false)}
                className="rounded p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-600 dark:hover:text-slate-300"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-3 space-y-3">
              <p className="text-xs leading-relaxed text-slate-600 dark:text-slate-300">
                You are approving documentation for <span className="font-semibold text-slate-900 dark:text-slate-100">Patient {session.patient_id}</span> ({session.reference}).
              </p>

              <label className="flex items-start gap-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/60 p-3 text-xs leading-relaxed text-slate-700 dark:text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={acknowledged}
                  onChange={(event) => setAcknowledged(event.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 dark:border-slate-700 text-teal-600 focus:ring-teal-500"
                />
                <span>
                  I confirm that I have reviewed this note and its supporting evidence, and I accept clinical responsibility for this record.
                </span>
              </label>
            </div>

            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                className="btn-secondary text-xs"
                onClick={() => setShowApproveModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-teal text-xs font-semibold flex items-center gap-1.5 px-4 py-2"
                disabled={busy || !acknowledged}
                onClick={() => void approve()}
              >
                {busy ? <Spinner /> : <BadgeCheck className="h-4 w-4" />}
                Sign & Approve Note
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {evidenceFocus ? (
        <div className="pointer-events-none fixed inset-y-0 right-0 flex">
          <div className="pointer-events-auto">
            <EvidenceViewer
              sessionId={session.id}
              targetKey={evidenceFocus.targetKey}
              statement={evidenceFocus.statement}
              onClose={() => focusEvidence(null)}
              onHighlight={selectSegment}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-2xs font-semibold uppercase tracking-[0.1em] text-slate-400 dark:text-slate-500">{label}</dt>
      <dd className="truncate text-xs font-medium text-slate-800 dark:text-slate-200">{value}</dd>
    </div>
  )
}
