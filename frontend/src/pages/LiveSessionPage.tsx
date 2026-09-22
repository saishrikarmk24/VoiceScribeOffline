import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Activity,
  FileText,
  Mic,
  Sparkles,
  Square,
  Stethoscope,
} from 'lucide-react'

import { ConsultationPipelineAnimation } from '@/components/session/ConsultationPipelineAnimation'
import { VitalsDictationModal } from '@/components/session/VitalsDictationModal'
import { InlineAlert } from '@/components/ui/primitives'
import { MedicalPulseLoader } from '@/components/ui/MedicalAnimations'
import { SECTION_LABELS, SECTION_ORDER } from '@/constants'
import { useAudioRecorder } from '@/hooks/useAudioRecorder'
import { api } from '@/services/api'
import { useSessionStore } from '@/store/sessionStore'
import { useUiStore } from '@/store/uiStore'
import type { NoteSectionKey } from '@/types'
import { cn } from '@/utils/cn'
import { formatDuration } from '@/utils/format'

export function LiveSessionPage() {
  const { id } = useParams<{ id: string }>()
  const pushToast = useUiStore((state) => state.pushToast)

  const {
    session,
    entities,
    note,
    stage,
    stageDetail,
    completed,
    loading,
    attach,
    detach,
    refresh,
    setSession,
    setNote,
  } = useSessionStore()

  const [loadError, setLoadError] = useState<string | null>(null)
  const [noteTab, setNoteTab] = useState<'draft' | 'final'>('draft')
  const [vitalsModalOpen, setVitalsModalOpen] = useState(false)

  const recorder = useAudioRecorder(id ?? null)

  useEffect(() => {
    if (!id) return
    attach(id).catch((error: Error) => setLoadError(error.message))
    return () => detach()
  }, [attach, detach, id])


  useEffect(() => {
    if (completed && session) {
      pushToast({
        kind: 'success',
        title: 'Session complete',
        detail: 'Open the review screen to verify evidence and approve the note.',
      })
    }
  }, [completed, pushToast, session])

  const handleStartRecording = async () => {
    if (!session) return
    try {
      if (session.status === 'CREATED') {
        const updated = await api.startSession(session.id)
        setSession(updated)
      }
      await recorder.start()
    } catch (err) {
      pushToast({ kind: 'error', title: 'Recording failed', detail: (err as Error).message })
    }
  }

  const handleStopRecording = async () => {
    try {
      await recorder.stop()
      await refresh()
    } catch (err) {
      pushToast({ kind: 'error', title: 'Could not stop recording', detail: (err as Error).message })
    }
  }

  const handleAddVitals = async (vitalsSummary: string, medsSummary: string) => {
    if (!session) return
    try {
      let currentNote = note
      if (!currentNote) {
        currentNote = await api.note(session.id)
        setNote(currentNote)
      }

      const content = currentNote.content as unknown as Record<string, { text?: string } | undefined>
      const changes: Partial<Record<NoteSectionKey, string>> = {}

      if (vitalsSummary) {
        const existing = content.physical_examination?.text?.trim() || ''
        const isPlaceholder = !existing || existing.toLowerCase() === 'not mentioned' || existing.toLowerCase().startsWith('not mentioned')
        changes.physical_examination = isPlaceholder ? `Vital signs: ${vitalsSummary}` : `${existing}. Vital signs: ${vitalsSummary}`
      }
      if (medsSummary) {
        const existing = content.current_medication?.text?.trim() || ''
        const isPlaceholder = !existing || existing.toLowerCase() === 'not mentioned' || existing.toLowerCase().startsWith('not mentioned')
        changes.current_medication = isPlaceholder ? medsSummary : `${existing}. ${medsSummary}`
      }

      if (Object.keys(changes).length > 0) {
        const updated = await api.editNote(currentNote.id, {
          ...changes,
          editor: 'Doctor (Dictation)',
        })
        setNote(updated)
        await refresh()
        pushToast({
          kind: 'success',
          title: 'Vitals & medications saved',
          detail: 'Updated Physical Examination & Medications in clinical note.',
        })
      }
    } catch (err) {
      pushToast({
        kind: 'error',
        title: 'Could not save vitals',
        detail: (err as Error).message,
      })
    }
  }

  const isProcessing = useMemo(() => {
    return (
      recorder.state === 'uploading' ||
      ['ASR', 'DIARIZATION', 'ROLE_ATTRIBUTION', 'TRANSCRIPT_ASSEMBLY', 'CLINICAL_NLP', 'LLM_STRUCTURING'].includes(
        stage,
      )
    )
  }, [recorder.state, stage])

  // Group entities by category
  const groupedEntities = useMemo(() => {
    const map: Record<string, typeof entities> = {
      Symptoms: [],
      'Medications & Treatments': [],
      Allergies: [],
      'Examination & Vitals': [],
      'Diagnoses & Assessment': [],
    }

    for (const ent of entities) {
      const type = String(ent.entity_type).toUpperCase()
      if (type.includes('SYMPTOM') || type.includes('COMPLAINT')) {
        map['Symptoms'].push(ent)
      } else if (type.includes('MEDIC') || type.includes('DRUG') || type.includes('TREATMENT') || type.includes('DOSE')) {
        map['Medications & Treatments'].push(ent)
      } else if (type.includes('ALLERG')) {
        map['Allergies'].push(ent)
      } else if (type.includes('EXAM') || type.includes('VITAL') || type.includes('SIGN')) {
        map['Examination & Vitals'].push(ent)
      } else {
        map['Diagnoses & Assessment'].push(ent)
      }
    }

    return Object.entries(map).filter(([_, items]) => items.length > 0)
  }, [entities])

  // Check if clinical note has any populated content
  const hasNoteContent = useMemo(() => {
    if (!note?.content) return false
    const content = note.content as unknown as Record<string, unknown>
    return Object.values(content).some((val) => {
      if (typeof val === 'string') return val.trim().length > 0
      if (typeof val === 'object' && val !== null && 'text' in val) {
        return Boolean((val as { text?: string }).text?.trim())
      }
      if (Array.isArray(val)) return val.length > 0
      return false
    })
  }, [note])

  if (loadError) {
    return (
      <div className="p-6">
        <InlineAlert kind="error" title="Could not load session">
          {loadError}
        </InlineAlert>
      </div>
    )
  }

  if (!session || loading) {
    return (
      <div className="flex h-full items-center justify-center p-12">
        <MedicalPulseLoader
          label="Connecting to Ambient Consultation..."
          sublabel="Establishing real-time clinical stream, audio diarization, and LLM synthesis"
        />
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#f8fafc] dark:bg-slate-950 text-slate-900 dark:text-slate-100 overflow-hidden font-sans">
      {/* Top Header Bar matching Mockup */}
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 px-6 pt-5 pb-4 shrink-0">
        <div>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            {session.name || 'Outpatient Consultation'}
          </h1>
          <p className="text-xs md:text-sm font-medium text-slate-500 dark:text-slate-400 mt-0.5">
            Capture the conversation. Generate structured clinical notes.
          </p>
        </div>

        <div className="flex items-center gap-2.5 self-start sm:self-auto">
          <button
            type="button"
            onClick={() => setVitalsModalOpen(true)}
            className="inline-flex items-center gap-2 rounded-xl border border-teal-200 dark:border-teal-800 bg-teal-50 dark:bg-teal-950/60 px-4 py-2.5 text-xs font-bold text-teal-800 dark:text-teal-300 hover:bg-teal-100 dark:hover:bg-teal-900/60 shadow-xs transition-all hover:shadow-sm"
            title="Dictate or enter patient vitals & medications"
          >
            <Activity className="h-4 w-4 text-teal-600 dark:text-teal-400" />
            <span>Dictate Vitals &amp; Meds</span>
          </button>

          <Link
            to={`/sessions/${session.id}/review`}
            className="inline-flex items-center gap-2 rounded-xl bg-[#0d9488] hover:bg-[#0f766e] text-white px-4 py-2.5 text-xs font-bold shadow-xs transition-all hover:shadow-sm"
          >
            <FileText className="h-4 w-4" />
            <span>Review &amp; Approve Note</span>
          </Link>
        </div>
      </header>

      {recorder.error && (
        <div className="px-6 pb-2">
          <InlineAlert kind="error" title="Recording Error" onDismiss={recorder.clearError}>
            {recorder.error}
          </InlineAlert>
        </div>
      )}

      {/* Main 3-Column Workstation Grid */}
      <div className="flex-1 min-h-0 px-6 pb-6 overflow-hidden">
        <div className="grid h-full grid-cols-1 md:grid-cols-3 gap-5 lg:gap-6">
          {/* ============================================================ */}
          {/* Card 1 (Left): Live Audio Recording Controller */}
          {/* ============================================================ */}
          <div className="rounded-3xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xs flex flex-col items-center justify-between p-7 text-center overflow-y-auto relative">
            <div className="w-full flex flex-col items-center">
              {/* Glowing animated microphone target */}
              <div className="relative my-7 flex items-center justify-center">
                {/* Outer pulsing glow */}
                <div
                  className={cn(
                    'absolute -inset-8 rounded-full blur-2xl transition-all duration-700',
                    recorder.recording ? 'bg-teal-500/25 scale-125' : 'bg-teal-500/5 scale-100',
                  )}
                />

                {/* Ripple rings when recording */}
                {recorder.recording && (
                  <>
                    <span className="absolute -inset-4 rounded-full border-2 border-teal-400/40 animate-ping opacity-60" />
                    <span className="absolute -inset-9 rounded-full border border-teal-300/30 animate-pulse opacity-40" />
                  </>
                )}

                {/* Floating particle sparkle dots */}
                <span className="absolute -top-3 -right-2 h-2 w-2 rounded-full bg-teal-400 shadow-[0_0_8px_#2dd4bf] animate-pulse" />
                <span className="absolute top-8 -left-5 h-2 w-2 rounded-full bg-teal-400/70 shadow-[0_0_8px_#2dd4bf] animate-ping" />
                <span className="absolute -bottom-2 -right-4 h-2.5 w-2.5 rounded-full bg-teal-400/60 shadow-[0_0_8px_#2dd4bf]" />
                <span className="absolute bottom-6 -left-4 h-1.5 w-1.5 rounded-full bg-teal-400/80 animate-pulse" />

                {/* Central Microphone Circle */}
                <button
                  type="button"
                  onClick={recorder.recording ? () => void handleStopRecording() : () => void handleStartRecording()}
                  disabled={recorder.busy}
                  className={cn(
                    'relative grid h-28 w-28 place-items-center rounded-full transition-all duration-300 shadow-xl select-none',
                    recorder.recording
                      ? 'bg-[#0d9488] text-white shadow-teal-500/30 scale-105 ring-8 ring-teal-500/15'
                      : 'bg-[#e6f7f4] dark:bg-teal-950/60 text-[#0d9488] dark:text-teal-300 hover:scale-105 hover:bg-teal-100 dark:hover:bg-teal-900/60 ring-8 ring-teal-500/5',
                  )}
                  title={recorder.recording ? 'Click to stop recording' : 'Click to start recording'}
                >
                  <Mic className="h-12 w-12" />
                </button>
              </div>

              {/* Status Headline */}
              <h2 className="text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
                {recorder.recording
                  ? `Recording... ${formatDuration(recorder.seconds)}`
                  : recorder.state === 'uploading'
                    ? 'Transcribing Audio...'
                    : 'Ready to Record'}
              </h2>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                Capture your consultation naturally
              </p>

              {/* Action Button */}
              <div className="mt-5">
                {recorder.recording ? (
                  <button
                    type="button"
                    onClick={() => void handleStopRecording()}
                    disabled={recorder.busy}
                    className="inline-flex items-center gap-2 rounded-full bg-[#fee2e2] dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 text-rose-600 dark:text-rose-300 hover:bg-rose-100 dark:hover:bg-rose-900/60 px-6 py-2.5 text-xs font-bold shadow-2xs transition-all hover:scale-105"
                  >
                    <Square className="h-3 w-3 fill-rose-600 text-rose-600" />
                    <span>Stop Recording</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => void handleStartRecording()}
                    disabled={recorder.busy}
                    className="inline-flex items-center gap-2 rounded-full bg-[#0d9488] hover:bg-[#0f766e] text-white px-6 py-2.5 text-xs font-bold shadow-2xs transition-all hover:scale-105"
                  >
                    <Mic className="h-3.5 w-3.5" />
                    <span>Start Recording</span>
                  </button>
                )}
              </div>
            </div>

            {/* Equalizer Visualizer & Footer Note */}
            <div className="w-full flex flex-col items-center mt-6">
              {/* Animated 28-Bar Equalizer Waveform */}
              <div className="flex items-center justify-center gap-1 h-8 w-full max-w-[240px] px-2">
                {[40, 60, 90, 45, 80, 100, 70, 30, 85, 95, 60, 40, 75, 90, 50, 65, 80, 40, 70, 95, 55, 35, 60, 80, 45, 60, 30].map(
                  (h, i) => (
                    <span
                      key={i}
                      className={cn(
                        'w-1 rounded-full transition-all duration-150',
                        recorder.recording
                          ? 'bg-[#0d9488] dark:bg-teal-400'
                          : 'bg-teal-200 dark:bg-teal-950/80',
                      )}
                      style={{
                        height: recorder.recording
                          ? `${Math.max(6, Math.min(32, Math.round((h / 100) * (20 + (i % 3) * 6))))}px`
                          : '6px',
                        animation: recorder.recording
                          ? `pulse ${0.4 + (i % 5) * 0.15}s infinite alternate`
                          : undefined,
                      }}
                    />
                  ),
                )}
              </div>

              <p className="mt-4 text-2xs text-slate-400 dark:text-slate-500 font-medium">
                Audio will be transcribed after you stop recording
              </p>
            </div>
          </div>

          {/* ============================================================ */}
          {/* Card 2 (Middle): Clinical Notes Panel */}
          {/* ============================================================ */}
          <div className="rounded-3xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xs flex flex-col overflow-hidden">
            {/* Card Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800/80 shrink-0">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                <span className="text-xs font-bold tracking-wider uppercase text-slate-800 dark:text-slate-200">
                  CLINICAL NOTES
                </span>
              </div>

              {/* Draft Note / Final Note Toggle */}
              <div className="flex items-center gap-1 rounded-xl bg-slate-100 dark:bg-slate-800/80 p-1 text-2xs font-semibold">
                <button
                  type="button"
                  onClick={() => setNoteTab('draft')}
                  className={cn(
                    'rounded-lg px-3 py-1 transition-all',
                    noteTab === 'draft'
                      ? 'bg-white dark:bg-slate-900 text-[#0d9488] dark:text-teal-300 border border-slate-200/80 dark:border-slate-700 shadow-2xs font-bold'
                      : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200',
                  )}
                >
                  Draft Note
                </button>
                <button
                  type="button"
                  onClick={() => setNoteTab('final')}
                  className={cn(
                    'rounded-lg px-3 py-1 transition-all',
                    noteTab === 'final'
                      ? 'bg-white dark:bg-slate-900 text-[#0d9488] dark:text-teal-300 border border-slate-200/80 dark:border-slate-700 shadow-2xs font-bold'
                      : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200',
                  )}
                >
                  Final Note
                </button>
              </div>
            </div>

            {/* Card Body */}
            <div className="flex-1 min-h-0 p-6 overflow-y-auto flex flex-col items-center justify-center">
              {isProcessing ? (
                /* Animated Pipeline Sequence */
                <ConsultationPipelineAnimation
                  stage={stage}
                  stageDetail={stageDetail}
                  isUploading={recorder.state === 'uploading'}
                />
              ) : hasNoteContent ? (
                /* Structured SOAP Note Content */
                <div className="w-full h-full space-y-4 text-left animate-fade-in">
                  {SECTION_ORDER.map((key) => {
                    const contentRecord = note?.content as unknown as Record<string, unknown> | undefined
                    const sectionContent = contentRecord?.[key] as { text?: string } | string | undefined
                    if (!sectionContent) return null
                    const text =
                      typeof sectionContent === 'object' && sectionContent !== null && 'text' in sectionContent
                        ? sectionContent.text
                        : String(sectionContent)
                    if (!text?.trim()) return null
                    const label = SECTION_LABELS[key as NoteSectionKey] || key.replace(/_/g, ' ')
                    return (
                      <div
                        key={key}
                        className="rounded-2xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30 p-4 shadow-2xs"
                      >
                        <h4 className="text-2xs font-bold uppercase tracking-wider text-teal-700 dark:text-teal-300 mb-1.5 flex items-center gap-1.5">
                          <span className="h-1.5 w-1.5 rounded-full bg-teal-500" />
                          {label}
                        </h4>
                        <div className="text-xs leading-relaxed text-slate-700 dark:text-slate-200 whitespace-pre-wrap">
                          {text}
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                /* Empty / Waiting Placeholder matching Mockup */
                <div className="flex flex-col items-center text-center max-w-xs select-none animate-fade-in">
                  <div className="relative mb-5 grid h-24 w-24 place-items-center rounded-full bg-sky-50 dark:bg-slate-800/60 border border-sky-100 dark:border-slate-700/60 shadow-2xs">
                    <FileText className="h-10 w-10 text-sky-500/80 dark:text-sky-400" />
                    <Sparkles className="absolute top-4 right-4 h-4 w-4 text-emerald-500" />
                  </div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    Your clinical note will appear here
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-slate-400 dark:text-slate-500">
                    Once you stop recording, the conversation will be transcribed and structured into a clinical note.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* ============================================================ */}
          {/* Card 3 (Right): Clinical Findings Panel */}
          {/* ============================================================ */}
          <div className="rounded-3xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xs flex flex-col overflow-hidden">
            {/* Card Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800/80 shrink-0">
              <div className="flex items-center gap-2">
                <Stethoscope className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                <span className="text-xs font-bold tracking-wider uppercase text-slate-800 dark:text-slate-200">
                  CLINICAL FINDINGS
                </span>
              </div>
              {entities.length > 0 && (
                <span className="rounded-full bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200/60 px-2.5 py-0.5 text-2xs font-semibold">
                  {entities.length} Extracted
                </span>
              )}
            </div>

            {/* Card Body */}
            <div className="flex-1 min-h-0 p-6 overflow-y-auto flex flex-col items-center justify-center">
              {isProcessing ? (
                /* Scanning Findings Animation */
                <div className="flex flex-col items-center text-center p-6 select-none animate-fade-in">
                  <div className="relative mb-5 grid h-20 w-20 place-items-center rounded-full bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800/60 shadow-2xs">
                    <Activity className="h-9 w-9 text-emerald-600 dark:text-emerald-400 animate-pulse" />
                  </div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    Scanning Clinical Findings...
                  </h3>
                  <p className="mt-1.5 text-xs text-slate-400 dark:text-slate-500 max-w-xs">
                    Extracting symptoms, medications, and examination metrics from dialogue
                  </p>
                </div>
              ) : entities.length > 0 ? (
                /* Grouped Structured Findings */
                <div className="w-full h-full space-y-4 text-left animate-fade-in">
                  {groupedEntities.map(([groupTitle, items]) => (
                    <div
                      key={groupTitle}
                      className="rounded-2xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30 p-3.5 shadow-2xs"
                    >
                      <h4 className="text-2xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2 flex items-center justify-between">
                        <span>{groupTitle}</span>
                        <span className="text-slate-400">({items.length})</span>
                      </h4>
                      <div className="flex flex-wrap gap-1.5">
                        {items.map((ent) => (
                          <span
                            key={ent.id}
                            className="inline-flex items-center gap-1 rounded-lg bg-white dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700 px-2.5 py-1 text-xs font-medium text-slate-800 dark:text-slate-200 shadow-2xs"
                          >
                            <span>{ent.value || ent.ref}</span>
                            {ent.confidence ? (
                              <span className="text-2xs font-bold text-teal-600 dark:text-teal-400">
                                {Math.round(ent.confidence * 100)}%
                              </span>
                            ) : null}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                /* Empty / Waiting Placeholder matching Mockup */
                <div className="flex flex-col items-center text-center max-w-xs select-none animate-fade-in">
                  <div className="relative mb-5 grid h-24 w-24 place-items-center rounded-full bg-sky-50 dark:bg-slate-800/60 border border-sky-100 dark:border-slate-700/60 shadow-2xs">
                    <Activity className="h-10 w-10 text-sky-500/80 dark:text-sky-400" />
                    <Sparkles className="absolute top-4 right-4 h-4 w-4 text-emerald-500" />
                  </div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    Key clinical information will appear here
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-slate-400 dark:text-slate-500">
                    Symptoms, medications, allergies, examination findings and other relevant details will be organized here.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Vitals Dictation & Entry Modal */}
      <VitalsDictationModal
        open={vitalsModalOpen}
        onClose={() => setVitalsModalOpen(false)}
        onAddVitals={handleAddVitals}
      />
    </div>
  )
}
