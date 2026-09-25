import { useEffect, useState } from 'react'
import { CheckCircle2, Cpu, Save, ShieldAlert, TestTube2, XCircle } from 'lucide-react'

import { InlineAlert, Panel, Spinner, StatusDot } from '@/components/ui/primitives'
import { api } from '@/services/api'
import { useUiStore } from '@/store/uiStore'
import type { SystemStatus } from '@/types'
import { cn } from '@/utils/cn'

const ROLES = ['DOCTOR', 'STUDENT', 'FACULTY', 'ADMIN']

export function SettingsPage() {
  const { identityEmail, identityRole, identityName, setIdentity, pushToast } = useUiStore()
  const [email, setEmail] = useState(identityEmail)
  const [role, setRole] = useState(identityRole)
  const [name, setName] = useState(identityName)

  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [aiCheck, setAiCheck] = useState<Record<string, unknown> | null>(null)
  const [checking, setChecking] = useState(false)
  const [metrics, setMetrics] = useState<Record<string, number> | null>(null)

  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null))
    api
      .metrics()
      .then((response) => setMetrics(response.counters))
      .catch(() => setMetrics(null))
  }, [])

  const runAiCheck = async () => {
    setChecking(true)
    try {
      const result = await api.checkAi()
      setAiCheck(result)
      pushToast({
        kind: result.ok ? 'success' : 'warning',
        title: result.ok ? 'AI provider reachable' : 'AI provider unavailable',
        detail: String(result.detail ?? result.message ?? ''),
      })
    } catch (error) {
      pushToast({ kind: 'error', title: 'AI check failed', detail: (error as Error).message })
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-4 p-5">
        <header>
          <h1 className="text-lg font-semibold tracking-tight text-navy-900">Settings</h1>
          <p className="text-xs text-navy-500">
            Runtime configuration lives in the backend <code className="mono">.env</code>. This screen shows the effective
            configuration and lets you switch the development identity used for RBAC and audit logging.
          </p>
        </header>

        <Panel title="Development identity" bodyClassName="grid gap-3 p-4 sm:grid-cols-3">
          <label>
            <span className="field-label">Display name</span>
            <input className="field-input" value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            <span className="field-label">Email</span>
            <input className="field-input" value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label>
            <span className="field-label">Role</span>
            <select className="field-input" value={role} onChange={(event) => setRole(event.target.value)}>
              {ROLES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <div className="sm:col-span-3 flex items-center gap-2">
            <button
              type="button"
              className="btn-primary"
              onClick={() => {
                setIdentity(email.trim(), role, name.trim() || email.trim())
                pushToast({ kind: 'success', title: 'Identity updated', detail: `${name} · ${role}` })
              }}
            >
              <Save className="h-4 w-4" aria-hidden />
              Save identity
            </button>
            <p className="text-2xs leading-relaxed text-navy-500">
              Sent as <code className="mono">X-User-Email</code> / <code className="mono">X-User-Role</code>. Only DOCTOR
              and FACULTY roles can approve clinical documentation.
            </p>
          </div>
        </Panel>

        <Panel title="Offline pipeline (RTX 4050)" icon={<Cpu className="h-3.5 w-3.5" aria-hidden />} bodyClassName="space-y-3 p-4">
          <p className="text-xs text-navy-600">
            Audio stays on this PC. Speech-to-text is Faster-Whisper on CPU. The SOAP note is Qwen 2.5 7B via Ollama on the GPU.
            Invented medicines and diagnoses are dropped if they are not in the transcript.
          </p>

          {status?.pipeline ? (
            <ol className="space-y-1.5 rounded border border-navy-100 bg-navy-50/40 p-3 text-xs text-navy-800">
              <li>
                <span className="font-semibold">1. Capture</span> — {status.pipeline.audio}
              </li>
              <li>
                <span className="font-semibold">2. Transcribe</span> — {status.pipeline.asr}
              </li>
              <li>
                <span className="font-semibold">3. Speakers</span> — {status.pipeline.diarization}
              </li>
              <li>
                <span className="font-semibold">4. Note</span> — {status.pipeline.llm}
              </li>
              <li>
                <span className="font-semibold">5. Ground</span> — {status.pipeline.grounding}
              </li>
            </ol>
          ) : (
            <p className="text-xs text-navy-500">Load the backend to see the live pipeline.</p>
          )}

          <InlineAlert kind="info" title={String(status?.pipeline?.target_gpu ?? 'NVIDIA RTX 4050 laptop (6 GB)')}>
            {status?.pipeline?.vram_budget ??
              'Qwen 2.5 7B Q4 ~4.7 GB on GPU. Faster-Whisper turbo int8 runs on CPU so they do not share VRAM.'}
          </InlineAlert>

          <dl className="grid gap-x-4 gap-y-1.5 text-xs sm:grid-cols-2">
            {status
              ? Object.entries(status.ai).map(([key, value]) => (
                  <div key={key} className="flex items-baseline gap-2">
                    <dt className="text-2xs font-semibold uppercase tracking-[0.1em] text-navy-500">{key}</dt>
                    <dd className="mono truncate text-navy-800">{String(value)}</dd>
                  </div>
                ))
              : null}
          </dl>

          <div className="flex items-center gap-2">
            <button type="button" className="btn-secondary" onClick={() => void runAiCheck()} disabled={checking}>
              {checking ? <Spinner /> : <TestTube2 className="h-4 w-4" aria-hidden />}
              Test local LLM (Ollama)
            </button>
            {aiCheck ? (
              <span
                className={cn(
                  'flex items-center gap-1.5 text-xs',
                  aiCheck.ok ? 'text-teal-700' : 'text-amber-700',
                )}
              >
                {aiCheck.ok ? (
                  <CheckCircle2 className="h-4 w-4" aria-hidden />
                ) : (
                  <XCircle className="h-4 w-4" aria-hidden />
                )}
                {String(aiCheck.detail ?? aiCheck.message ?? (aiCheck.ok ? 'Reachable' : 'Unavailable'))}
              </span>
            ) : null}
          </div>
        </Panel>

        <Panel title="Pipeline providers" bodyClassName="grid gap-3 p-4 sm:grid-cols-2">
          <ProviderCard
            title="ASR"
            name={status?.providers.asr.name ?? '—'}
            mock={Boolean(status?.providers.asr.mock)}
            detail="Faster-Whisper large-v3-turbo (int8) on CPU. Multilingual. Audio never leaves this PC. Needs pip install -r requirements-asr.txt."
          />
          <ProviderCard
            title="Diarization"
            name={status?.providers.diarization.name ?? '—'}
            mock={Boolean(status?.providers.diarization.mock)}
            detail="Local two-speaker clustering on CPU. Do not enable pyannote on a 6 GB laptop — it would steal VRAM from Qwen 7B."
          />
          <ProviderCard
            title="Terminology"
            name={String(status?.providers.terminology?.name ?? 'mock')}
            mock
            detail="SNOMED CT / ICD-10 / RxNorm / LOINC interfaces are defined; codes are never fabricated."
          />
          <ProviderCard
            title="Database"
            name={status?.database.dialect ?? '—'}
            mock={Boolean(status?.database.using_fallback)}
            detail={status?.database.using_fallback ? 'Running on the SQLite development fallback.' : 'PostgreSQL connected.'}
          />
        </Panel>

        {metrics ? (
          <Panel title="Counters" bodyClassName="p-4">
            <dl className="grid gap-x-4 gap-y-1 text-2xs sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(metrics)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([key, value]) => (
                  <div key={key} className="flex items-baseline justify-between gap-2 border-b border-navy-50 py-0.5">
                    <dt className="truncate text-navy-600">{key}</dt>
                    <dd className="mono font-semibold text-navy-900">{value}</dd>
                  </div>
                ))}
            </dl>
            <p className="mt-2 text-2xs text-navy-500">
              Prometheus exposition is available at <code className="mono">/api/metrics?prometheus=true</code>.
            </p>
          </Panel>
        ) : null}

        <InlineAlert kind="info" title="Privacy and scope">
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            <li>Never enter real patient data.</li>
            <li>Audio and notes stay on this machine. Ollama and Whisper do not call the cloud.</li>
            <li>Every clinical statement must cite transcript evidence or it is dropped / flagged.</li>
            <li>Approval is always an explicit human action.</li>
          </ul>
        </InlineAlert>
      </div>
    </div>
  )
}

function ProviderCard({
  title,
  name,
  mock,
  detail,
}: {
  title: string
  name: string
  mock: boolean
  detail: string
}) {
  return (
    <div className="rounded border border-navy-200/70 bg-white p-3">
      <div className="flex items-center gap-1.5">
        <StatusDot className={mock ? 'bg-amber-500' : 'bg-teal-500'} />
        <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-navy-500">{title}</p>
        <span className="mono ml-auto text-2xs text-navy-700">{name}</span>
      </div>
      <p className="mt-1 flex gap-1.5 text-2xs leading-relaxed text-navy-500">
        {mock ? <ShieldAlert className="mt-0.5 h-3 w-3 shrink-0 text-amber-500" aria-hidden /> : null}
        {detail}
      </p>
    </div>
  )
}
