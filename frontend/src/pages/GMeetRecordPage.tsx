import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ClipboardCheck, MonitorUp, Square, Video } from 'lucide-react'

import { ClinicalNotePanel } from '@/components/session/ClinicalNotePanel'
import { EvidenceViewer } from '@/components/session/EvidenceViewer'
import { IntelligencePanel } from '@/components/session/IntelligencePanel'
import { SpeakerRoster } from '@/components/session/SpeakerRoster'
import { TranscriptPanel } from '@/components/session/TranscriptPanel'
import { InlineAlert, Panel, Spinner } from '@/components/ui/primitives'
import { ENCOUNTER_TYPES } from '@/constants'
import { useMeetTabCapture } from '@/hooks/useMeetTabCapture'
import { api } from '@/services/api'
import { useSessionStore } from '@/store/sessionStore'
import { useUiStore } from '@/store/uiStore'
import { cn } from '@/utils/cn'
import { formatDuration } from '@/utils/format'

const DEFAULTS = {
  name: 'Google Meet session',
  patient_id: 'SIM-PT-GMEET',
  scenario: 'Remote doctor–patient encounter captured from Google Meet',
  simulation_type: 'OUTPATIENT',
  doctor_name: 'Dr. A. Rao',
}

/**
 * Standalone Google Meet capture. Creates a normal UPLOAD session and sends the
 * captured WAV through the existing transcription pipeline — no backend changes.
 */
export function GMeetRecordPage() {
  const navigate = useNavigate()
  const pushToast = useUiStore((state) => state.pushToast)
  const identityName = useUiStore((state) => state.identityName)

  const [form, setForm] = useState({ ...DEFAULTS, doctor_name: DEFAULTS.doctor_name })
  const [creating, setCreating] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const previewRef = useRef<HTMLVideoElement>(null)

  const {
    session,
    segments,
    speakers,
    entities,
    note,
    evidence,
    stage,
    stageDetail,
    errors,
    selectedSegmentRef,
    evidenceFocus,
    attach,
    detach,
    refresh,
    selectSegment,
    focusEvidence,
    dismissError,
  } = useSessionStore()

  const capture = useMeetTabCapture(session?.id ?? null)

  useEffect(() => {
    return () => detach()
  }, [detach])

  useEffect(() => {
    const node = previewRef.current
    if (!node) return
    node.srcObject = capture.previewStream
    return () => {
      node.srcObject = null
    }
  }, [capture.previewStream])

  const highlightedRefs = useMemo(() => {
    if (!evidenceFocus) return []
    return evidence
      .filter((link) => link.target_key === evidenceFocus.targetKey && link.segment_ref)
      .map((link) => link.segment_ref as string)
  }, [evidence, evidenceFocus])

  const update = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((previous) => ({ ...previous, [key]: event.target.value }))

  const createSession = async () => {
    setCreating(true)
    setFormError(null)
    try {
      const created = await api.createSession({
        name: form.name.trim(),
        patient_id: form.patient_id.trim(),
        scenario: form.scenario.trim() || null,
        simulation_type: form.simulation_type,
        doctor_name: form.doctor_name.trim() || identityName,
        faculty_name: null,
        mode: 'UPLOAD',
        audio_source: 'UPLOAD',
      })
      await api.startSession(created.id)
      await attach(created.id)
      pushToast({
        kind: 'success',
        title: `${created.reference} ready`,
        detail: 'Share the Google Meet tab to begin recording.',
      })
    } catch (err) {
      setFormError((err as Error).message)
    } finally {
      setCreating(false)
    }
  }

  const onStopCapture = useCallback(async () => {
    await capture.stop()
    await refresh()
  }, [capture, refresh])

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <header className="shrink-0 border-b border-navy-200 bg-white px-5 py-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight text-navy-900">
              <Video className="h-5 w-5 text-teal-700" aria-hidden />
              Record Google Meet
            </h1>
            <p className="text-xs text-navy-500">
              Capture the Meet tab, then process it through the same transcript → note → evidence pipeline.
            </p>
          </div>
          {session ? (
            <Link to={`/sessions/${session.id}/review`} className="btn-secondary">
              <ClipboardCheck className="h-4 w-4" aria-hidden />
              Review & Approve
            </Link>
          ) : null}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-7xl space-y-3 p-4">
          <InlineAlert kind="info" title="How to capture a Meet">
            Open the Google Meet in Chrome or Edge. After the session is created, click Share Meet tab, select that tab,
            and tick <strong>Share tab audio</strong>. Keep this window open until you press Stop.
          </InlineAlert>

          {!session ? (
            <Panel title="Session details" bodyClassName="grid gap-3 p-4 sm:grid-cols-2">
              {formError ? (
                <div className="sm:col-span-2">
                  <InlineAlert kind="error" title="Could not create session" onDismiss={() => setFormError(null)}>
                    {formError}
                  </InlineAlert>
                </div>
              ) : null}
              <label className="sm:col-span-2">
                <span className="field-label">Session name</span>
                <input className="field-input" value={form.name} onChange={update('name')} />
              </label>
              <label>
                <span className="field-label">Patient ID</span>
                <input className="field-input mono" value={form.patient_id} onChange={update('patient_id')} />
              </label>
              <label>
                <span className="field-label">Encounter type</span>
                <select className="field-input" value={form.simulation_type} onChange={update('simulation_type')}>
                  {ENCOUNTER_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="sm:col-span-2">
                <span className="field-label">Scenario</span>
                <input className="field-input" value={form.scenario} onChange={update('scenario')} />
              </label>
              <label>
                <span className="field-label">Doctor</span>
                <input className="field-input" value={form.doctor_name} onChange={update('doctor_name')} />
              </label>
              <div className="sm:col-span-2">
                <button
                  type="button"
                  className="btn-primary"
                  disabled={creating || !form.name.trim() || !form.patient_id.trim()}
                  onClick={() => void createSession()}
                >
                  {creating ? <Spinner className="text-white" /> : <MonitorUp className="h-4 w-4" aria-hidden />}
                  Create session
                </button>
              </div>
            </Panel>
          ) : (
            <Panel title="Meet capture" bodyClassName="space-y-3 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mono text-xs font-semibold text-navy-800">{session.reference}</span>
                <span className="text-xs text-navy-500">{session.name}</span>
              </div>

              {capture.error ? (
                <InlineAlert kind="error" title="Capture error" onDismiss={capture.clearError}>
                  {capture.error}
                </InlineAlert>
              ) : null}

              {errors.map((item) => (
                <InlineAlert
                  key={item.code}
                  kind="warning"
                  title={item.code}
                  onDismiss={() => dismissError(item.code)}
                >
                  {item.message}
                </InlineAlert>
              ))}

              <div className="flex items-center gap-2 text-xs">
                <span className={cn('inline-block h-2 w-2 rounded-full', capture.micConnected ? 'bg-green-500' : 'bg-amber-400')} />
                <span className={capture.micConnected ? 'text-green-700' : 'text-amber-700'}>
                  {capture.micConnected
                    ? 'Microphone connected — your voice is being recorded'
                    : capture.recording
                      ? 'Microphone not connected — only Meet tab audio is being recorded'
                      : 'Microphone will be captured automatically when recording starts'}
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className={cn(capture.recording ? 'btn-danger' : 'btn-teal')}
                  disabled={session.status !== 'LIVE' || capture.busy}
                  onClick={() => (capture.recording ? void onStopCapture() : void capture.start())}
                >
                  {capture.state === 'uploading' ? (
                    <Spinner />
                  ) : capture.recording ? (
                    <Square className="h-4 w-4" aria-hidden />
                  ) : (
                    <Video className="h-4 w-4" aria-hidden />
                  )}
                  {capture.state === 'requesting'
                    ? 'Waiting for tab picker…'
                    : capture.state === 'uploading'
                      ? 'Transcribing Meet audio…'
                      : capture.recording
                        ? `Stop & transcribe · ${formatDuration(capture.seconds)}`
                        : 'Share Meet tab'}
                </button>
                {capture.recording ? (
                  <>
                    <span className="flex items-center gap-1.5 text-2xs text-navy-500">
                      <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" aria-hidden />
                      Level
                      <span className="relative h-1.5 w-24 overflow-hidden rounded-full bg-navy-100">
                        <span
                          className="absolute inset-y-0 left-0 rounded-full bg-teal-500"
                          style={{ width: `${Math.min(100, Math.round(capture.level * 160))}%` }}
                        />
                      </span>
                    </span>
                    <button type="button" className="btn-secondary" onClick={capture.cancel}>
                      Discard
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      capture.cancel()
                      void api.stopSession(session.id).then((stopped) => navigate(`/sessions/${stopped.id}/review`))
                    }}
                  >
                    End session
                  </button>
                )}
              </div>

              {capture.previewStream ? (
                <video
                  ref={previewRef}
                  className="h-36 w-full rounded border border-navy-200 bg-navy-950 object-contain"
                  muted
                  autoPlay
                  playsInline
                  aria-label="Shared Meet tab preview"
                />
              ) : null}
            </Panel>
          )}

          {session ? (
            <div className="grid min-h-[28rem] grid-cols-1 gap-2 lg:grid-cols-3">
              <TranscriptPanel
                segments={segments}
                speakers={speakers}
                evidence={evidence}
                selectedRef={selectedSegmentRef}
                highlightedRefs={highlightedRefs}
                live={capture.recording}
                onSelect={selectSegment}
              />
              <ClinicalNotePanel
                note={note}
                changedSections={[]}
                onShowSource={(targetKey, statement) => focusEvidence({ targetKey, statement, kind: 'SECTION' })}
              />
              <div className="flex min-h-0 flex-col gap-2">
                <IntelligencePanel
                  entities={entities}
                  stage={stage}
                  stageDetail={stageDetail}
                  onShowSource={(targetKey, statement) => focusEvidence({ targetKey, statement, kind: 'ENTITY' })}
                />
                <SpeakerRoster speakers={speakers} onChanged={() => void refresh()} />
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {session && evidenceFocus ? (
        <EvidenceViewer
          sessionId={session.id}
          targetKey={evidenceFocus.targetKey}
          statement={evidenceFocus.statement}
          onClose={() => focusEvidence(null)}
          onHighlight={selectSegment}
        />
      ) : null}
    </div>
  )
}
