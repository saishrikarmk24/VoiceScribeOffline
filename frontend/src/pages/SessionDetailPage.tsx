import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ClipboardCheck, FileClock, Radio, ScrollText, Waves } from 'lucide-react'

import { SpeakerRoster } from '@/components/session/SpeakerRoster'
import { InlineAlert, Panel, Spinner, StatCard } from '@/components/ui/primitives'
import { ENTITY_STATUS_LABELS, ENTITY_STATUS_STYLES, NOTE_STATUS_LABELS, ROLE_STYLES, SESSION_STATUS_STYLES } from '@/constants'
import { api } from '@/services/api'
import type { AudioChunk, ClinicalEntity, ClinicalNote, Session, TranscriptSegment } from '@/types'
import { cn } from '@/utils/cn'
import { formatDateTime, formatDuration, formatTimestamp, titleCase } from '@/utils/format'

interface AuditEntry {
  id: string
  action: string
  actor_email: string
  created_at: string
  detail: unknown
}

export function SessionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [session, setSession] = useState<Session | null>(null)
  const [segments, setSegments] = useState<TranscriptSegment[]>([])
  const [entities, setEntities] = useState<ClinicalEntity[]>([])
  const [note, setNote] = useState<ClinicalNote | null>(null)
  const [chunks, setChunks] = useState<AudioChunk[]>([])
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    Promise.all([
      api.getSession(id),
      api.transcript(id),
      api.entities(id),
      api.note(id),
      api.audioChunks(id),
      api.audit(id),
    ])
      .then(([nextSession, nextSegments, nextEntities, nextNote, nextChunks, nextAudit]) => {
        if (cancelled) return
        setSession(nextSession)
        setSegments(nextSegments)
        setEntities(nextEntities)
        setNote(nextNote)
        setChunks(nextChunks.chunks)
        setAudit(nextAudit.entries as AuditEntry[])
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [id])

  if (error) {
    return (
      <div className="p-6">
        <InlineAlert kind="error" title="Could not load session">
          {error}
        </InlineAlert>
      </div>
    )
  }

  if (!session) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-navy-500">
        <Spinner /> Loading session…
      </div>
    )
  }

  const speechSeconds = chunks.reduce((sum, chunk) => sum + (chunk.end_time - chunk.start_time) * chunk.speech_ratio, 0)

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-4 p-5">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="mono text-lg font-semibold tracking-tight text-slate-900">{session.reference}</h1>
              <span className={cn('badge', SESSION_STATUS_STYLES[session.status])}>{session.status}</span>
            </div>
            <p className="text-xs text-slate-500">
              {session.name} · Patient {session.patient_id} · Created {formatDateTime(session.created_at)}
            </p>
          </div>
          <div className="flex gap-2">
            <Link to={`/sessions/${session.id}/live`} className="btn-secondary !py-1 text-xs">
              <Radio className="h-4 w-4" aria-hidden />
              Live Workspace
            </Link>
            <Link to={`/sessions/${session.id}/review`} className="btn-teal !py-1 text-xs font-semibold flex items-center gap-1.5 shadow-sm">
              <ClipboardCheck className="h-4 w-4" aria-hidden />
              Review & Approve Note
            </Link>
          </div>
        </header>

        {session.last_error ? (
          <InlineAlert kind="warning" title="Last Recorded Note Warning">
            {session.last_error}
          </InlineAlert>
        ) : null}

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <StatCard label="Duration" value={formatDuration(session.duration_seconds)} />
          <StatCard label="Speech Lines" value={segments.length} />
          <StatCard label="Clinical Facts" value={entities.length} />
          <StatCard
            label="Note Status"
            value={note ? NOTE_STATUS_LABELS[note.status] : '—'}
            detail={note ? `Version ${note.version}` : undefined}
          />
          <StatCard label="Speech Audio" value={formatDuration(speechSeconds)} detail={`${chunks.length} recording files`} />
        </div>

        <div className="grid gap-3 lg:grid-cols-2">
          <Panel title="Conversation Transcript" icon={<ScrollText className="h-3.5 w-3.5 text-teal-600" aria-hidden />} className="max-h-96">
            {segments.length === 0 ? (
              <p className="p-3 text-xs text-slate-500">No transcript recorded.</p>
            ) : (
              <ol className="divide-y divide-slate-100">
                {segments.map((segment) => {
                  const role = ROLE_STYLES[segment.role] ?? ROLE_STYLES.UNKNOWN
                  return (
                    <li key={segment.ref} className={cn('border-l-2 px-3 py-2', role.accent)}>
                      <div className="flex items-center gap-2">
                        <span className={cn('badge', role.badge)}>{role.label}</span>
                        <span className="mono text-2xs text-slate-500">{formatTimestamp(segment.start_time)}</span>
                      </div>
                      <p className="mt-0.5 text-xs leading-relaxed text-slate-800">{segment.text}</p>
                    </li>
                  )
                })}
              </ol>
            )}
          </Panel>

          <div className="flex flex-col gap-3">
            <SpeakerRoster speakers={session.speakers} editable={false} />

            <Panel title="Key Clinical Findings" className="max-h-64">
              {entities.length === 0 ? (
                <p className="p-3 text-xs text-slate-500">No clinical findings extracted yet.</p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {entities.map((entity) => (
                    <li key={entity.ref} className="flex items-center gap-1.5 px-3 py-1.5 text-xs">
                      <span className={cn('badge', ENTITY_STATUS_STYLES[entity.status])}>
                        {ENTITY_STATUS_LABELS[entity.status]}
                      </span>
                      <span className="font-medium text-slate-900">{entity.value}</span>
                      <span className="ml-auto text-2xs text-slate-500">{titleCase(entity.entity_type)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-2">
          <Panel title="Audio chunks" icon={<Waves className="h-3.5 w-3.5" aria-hidden />} className="max-h-72">
            {chunks.length === 0 ? (
              <p className="p-3 text-xs text-navy-500">No audio processed.</p>
            ) : (
              <table className="w-full text-left text-2xs">
                <thead className="border-b border-navy-100 bg-navy-50/50 uppercase tracking-[0.1em] text-navy-500">
                  <tr>
                    <th className="px-3 py-1.5 font-semibold">#</th>
                    <th className="px-3 py-1.5 font-semibold">Source</th>
                    <th className="px-3 py-1.5 font-semibold">Window</th>
                    <th className="px-3 py-1.5 text-right font-semibold">Speech</th>
                    <th className="px-3 py-1.5 text-right font-semibold">RMS</th>
                    <th className="px-3 py-1.5 text-right font-semibold">Bytes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-navy-50">
                  {chunks.map((chunk) => (
                    <tr key={chunk.id}>
                      <td className="mono px-3 py-1 text-navy-600">{chunk.sequence}</td>
                      <td className="px-3 py-1 text-navy-600">{chunk.source}</td>
                      <td className="mono px-3 py-1 text-navy-600">
                        {formatTimestamp(chunk.start_time)}–{formatTimestamp(chunk.end_time)}
                      </td>
                      <td className="mono px-3 py-1 text-right text-navy-600">
                        {Math.round(chunk.speech_ratio * 100)}%
                      </td>
                      <td className="mono px-3 py-1 text-right text-navy-600">{chunk.rms_dbfs.toFixed(1)} dB</td>
                      <td className="mono px-3 py-1 text-right text-navy-600">{chunk.size_bytes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>

          <Panel title="Audit trail" icon={<FileClock className="h-3.5 w-3.5" aria-hidden />} className="max-h-72">
            {audit.length === 0 ? (
              <p className="p-3 text-xs text-navy-500">No audit entries.</p>
            ) : (
              <ol className="divide-y divide-navy-50">
                {audit.map((entry) => (
                  <li key={entry.id} className="px-3 py-1.5">
                    <div className="flex items-center gap-2">
                      <span className="mono text-2xs font-semibold text-navy-800">{entry.action}</span>
                      <span className="ml-auto text-2xs text-navy-400">{formatDateTime(entry.created_at)}</span>
                    </div>
                    <p className="text-2xs text-navy-500">{entry.actor_email}</p>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        </div>
      </div>
    </div>
  )
}
