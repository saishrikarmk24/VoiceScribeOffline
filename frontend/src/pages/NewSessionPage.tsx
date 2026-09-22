import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mic, PlayCircle, Upload } from 'lucide-react'

import { Panel, Spinner } from '@/components/ui/primitives'
import { ENCOUNTER_TYPES } from '@/constants'
import { api } from '@/services/api'
import { useAuthStore } from '@/store/authStore'
import { useUiStore } from '@/store/uiStore'
import type { SessionMode } from '@/types'
import { cn } from '@/utils/cn'

const MODES: { value: SessionMode; label: string; detail: string; icon: typeof Mic }[] = [
  {
    value: 'MICROPHONE',
    label: 'Live Microphone',
    detail: 'Record the doctor–patient conversation directly in the clinic. Speech is transcribed and structured in real time.',
    icon: Mic,
  },
  {
    value: 'UPLOAD',
    label: 'Upload Audio File',
    detail: 'Upload an audio file (.wav, .mp3, .m4a) of an encounter to generate notes in one pass.',
    icon: Upload,
  },
]

const DEFAULTS = {
  name: 'Consultation',
  patient_id: 'PT-1042',
  patient_name: '',
  scenario: '',
  simulation_type: 'OUTPATIENT',
  doctor_name: '',
}

export function NewSessionPage() {
  const navigate = useNavigate()
  const pushToast = useUiStore((state) => state.pushToast)
  const user = useAuthStore((state) => state.user)
  const identityName = useUiStore((state) => state.identityName)

  const activeDoctorName = user?.full_name
    ? (user.full_name.startsWith('Dr.') ? user.full_name : `Dr. ${user.full_name}`)
    : (identityName || 'Dr. A. Rao')

  const [form, setForm] = useState({ ...DEFAULTS, doctor_name: activeDoctorName })
  const [mode, setMode] = useState<SessionMode>('MICROPHONE')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Standard clinical encounters only (filtered from non-clinical presets)
  const clinicalEncounterTypes = useMemo(() => {
    return ENCOUNTER_TYPES.filter((t) => t.value !== 'MEETING' && t.value !== 'MDT')
  }, [])

  const audioSource = useMemo(
    () => (mode === 'MICROPHONE' ? 'MICROPHONE' : 'UPLOAD'),
    [mode],
  )

  const update = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((previous) => ({ ...previous, [key]: event.target.value }))

  const submit = async (autoStart: boolean) => {
    setSubmitting(true)
    setError(null)
    const consultationTitle = form.patient_name.trim()
      ? `${form.patient_name.trim()} - Consultation`
      : form.name.trim() || 'Consultation'

    try {
      const session = await api.createSession({
        name: consultationTitle,
        patient_id: form.patient_id.trim() || 'PT-1042',
        patient_name: form.patient_name.trim() || null,
        scenario: form.scenario.trim() || null,
        simulation_type: form.simulation_type,
        doctor_name: activeDoctorName,
        faculty_name: null,
        mode,
        audio_source: audioSource,
      })
      if (autoStart) {
        await api.startSession(session.id)
        pushToast({ kind: 'success', title: `${session.reference} started`, detail: 'Live clinical scribe is listening.' })
      } else {
        pushToast({ kind: 'success', title: `${session.reference} created` })
      }
      navigate(`/sessions/${session.id}/live`)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-[#f8fafc] dark:bg-slate-950 transition-colors duration-200">
      <div className="mx-auto max-w-3xl space-y-5 p-5 md:p-6 lg:p-8 pb-20">
        {/* Header */}
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            New Clinical Consultation
          </h1>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            Configure patient details and select an audio capture mode to begin ambient documentation.
          </p>
        </div>

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        ) : null}

        {/* Patient & Encounter Details */}
        <Panel title="Consultation Details" bodyClassName="grid gap-3 p-4 sm:grid-cols-2">
          <label>
            <span className="field-label">Patient Name *</span>
            <input
              className="field-input"
              value={form.patient_name}
              onChange={update('patient_name')}
              placeholder="e.g. Ramesh Kumar"
              required
              autoFocus
            />
          </label>

          <label>
            <span className="field-label">Patient ID / MRN *</span>
            <input
              className="field-input mono"
              value={form.patient_id}
              onChange={update('patient_id')}
              placeholder="e.g. PT-1042"
              required
            />
          </label>

          <label className="sm:col-span-2">
            <span className="field-label">Consultation Type</span>
            <select className="field-input" value={form.simulation_type} onChange={update('simulation_type')}>
              {clinicalEncounterTypes.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </label>

          <label className="sm:col-span-2">
            <span className="field-label">Clinical Scenario / Chief Concern (Optional)</span>
            <input
              className="field-input"
              value={form.scenario}
              onChange={update('scenario')}
              placeholder="Brief context (e.g. Follow-up for chest discomfort and hypertension)"
            />
          </label>

          <div className="sm:col-span-2 flex items-center justify-between rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/60 px-3.5 py-2.5 text-2xs text-slate-500 dark:text-slate-400">
            <span>Attending Clinician:</span>
            <span className="font-semibold text-teal-700 dark:text-teal-400 text-xs">{activeDoctorName}</span>
          </div>
        </Panel>

        {/* Audio Input Source */}
        <Panel title="Audio Input Source" bodyClassName="grid gap-2.5 p-4 sm:grid-cols-2">
          {MODES.map(({ value, label, detail, icon: Icon }) => (
            <button
              key={value}
              type="button"
              onClick={() => setMode(value)}
              className={cn(
                'flex flex-col gap-1.5 rounded-xl border p-3.5 text-left transition',
                mode === value
                  ? 'border-teal-500 bg-teal-50/80 dark:bg-teal-950/60 ring-1 ring-teal-500/40 shadow-xs'
                  : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700',
              )}
              aria-pressed={mode === value}
            >
              <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-900 dark:text-slate-100">
                <Icon className="h-4 w-4 text-teal-600 dark:text-teal-400" aria-hidden />
                {label}
              </span>
              <span className="text-2xs leading-relaxed text-slate-500 dark:text-slate-400">{detail}</span>
            </button>
          ))}
        </Panel>

        {/* Instructions */}
        {mode === 'MICROPHONE' ? (
          <Panel title="Microphone Instructions" bodyClassName="p-4">
            <ul className="space-y-1.5 text-2xs leading-relaxed text-slate-600 dark:text-slate-300 list-disc ml-4">
              <li>Click <strong>Start Consultation</strong> to launch the live recording workspace.</li>
              <li>Press <strong>Record</strong> when ready to capture ambient speech between clinician and patient.</li>
              <li>When the visit concludes, click <strong>Stop & Transcribe</strong> to generate the clinical note for physician sign-off.</li>
            </ul>
          </Panel>
        ) : null}

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-3 pt-2">
          <button
            type="button"
            className="btn-teal flex items-center gap-2 px-5 py-2.5 text-xs font-semibold shadow-sm"
            disabled={submitting || !form.patient_name.trim()}
            onClick={() => void submit(true)}
          >
            {submitting ? <Spinner className="text-white" /> : <PlayCircle className="h-4 w-4" aria-hidden />}
            Start Consultation
          </button>
          <button
            type="button"
            className="btn-secondary px-4 py-2.5 text-xs text-slate-600 dark:text-slate-300"
            disabled={submitting || !form.patient_name.trim()}
            onClick={() => void submit(false)}
          >
            Save as Draft
          </button>
        </div>
      </div>
    </div>
  )
}
