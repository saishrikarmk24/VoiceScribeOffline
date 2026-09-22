/**
 * Live session state. Every mutation originates from either a REST call or a
 * WebSocket event, so the UI renders whatever the pipeline last reported.
 */

import { create } from 'zustand'

import { api } from '@/services/api'
import { SessionSocket, type ConnectionState } from '@/services/socket'
import type {
  AiStatus,
  ClinicalEntity,
  ClinicalNote,
  EvidenceLink,
  ProcessingStage,
  Session,
  SocketEvent,
  Speaker,
  StateSnapshot,
  TranscriptSegment,
} from '@/types'

export interface PipelineError {
  code: string
  message: string
  stage: string
  recoverable: boolean
  at: string
}

export interface EvidenceFocus {
  targetKey: string
  statement: string
  kind: 'SECTION' | 'ENTITY' | string
}

interface SessionState {
  sessionId: string | null
  session: Session | null
  segments: TranscriptSegment[]
  speakers: Speaker[]
  entities: ClinicalEntity[]
  note: ClinicalNote | null
  evidence: EvidenceLink[]
  ai: AiStatus | null
  stage: ProcessingStage
  stageDetail: string
  connection: ConnectionState
  audioActive: boolean
  timelineSeconds: number
  lastNoteChange: { sections: string[]; summary: string; at: string } | null
  errors: PipelineError[]
  selectedSegmentRef: string | null
  evidenceFocus: EvidenceFocus | null
  completed: boolean
  loading: boolean
  socket: SessionSocket | null

  attach: (sessionId: string) => Promise<void>
  detach: () => void
  refresh: () => Promise<void>
  applyEvent: (event: SocketEvent) => void
  selectSegment: (ref: string | null) => void
  focusEvidence: (focus: EvidenceFocus | null) => void
  setSession: (session: Session) => void
  setNote: (note: ClinicalNote) => void
  dismissError: (code: string) => void
}

const initial = {
  sessionId: null,
  session: null,
  segments: [] as TranscriptSegment[],
  speakers: [] as Speaker[],
  entities: [] as ClinicalEntity[],
  note: null,
  evidence: [] as EvidenceLink[],
  ai: null,
  stage: 'IDLE' as ProcessingStage,
  stageDetail: '',
  connection: 'closed' as ConnectionState,
  audioActive: false,
  timelineSeconds: 0,
  lastNoteChange: null,
  errors: [] as PipelineError[],
  selectedSegmentRef: null,
  evidenceFocus: null,
  completed: false,
  loading: false,
  socket: null as SessionSocket | null,
}

function mergeSegments(existing: TranscriptSegment[], incoming: TranscriptSegment[]): TranscriptSegment[] {
  const byRef = new Map(existing.map((segment) => [segment.ref, segment]))
  for (const segment of incoming) byRef.set(segment.ref, segment)
  return [...byRef.values()].sort((a, b) => a.sequence - b.sequence)
}

export const useSessionStore = create<SessionState>((set, get) => ({
  ...initial,

  attach: async (sessionId: string) => {
    const current = get()
    if (current.sessionId === sessionId && current.socket) return
    current.socket?.close()

    set({ ...initial, sessionId, loading: true })
    await get().refresh()

    const socket = new SessionSocket(sessionId, {
      onEvent: (event) => get().applyEvent(event),
      onStateChange: (connection) => set({ connection }),
    })
    socket.connect()
    set({ socket, loading: false })
  },

  detach: () => {
    get().socket?.close()
    set({ ...initial })
  },

  refresh: async () => {
    const sessionId = get().sessionId
    if (!sessionId) return
    const [session, segments, speakers, entities, note, evidence] = await Promise.all([
      api.getSession(sessionId),
      api.transcript(sessionId),
      api.speakers(sessionId),
      api.entities(sessionId),
      api.note(sessionId),
      api.evidence(sessionId),
    ])
    set({ session, segments, speakers, entities, note, evidence })
  },

  applyEvent: (event: SocketEvent) => {
    switch (event.type) {
      case 'STATE_SNAPSHOT': {
        const payload = event.payload as unknown as StateSnapshot
        set({
          session: payload.session ?? get().session,
          segments: payload.segments ?? [],
          speakers: payload.speakers ?? [],
          entities: payload.entities ?? [],
          note: payload.note ?? get().note,
          evidence: payload.evidence ?? [],
          ai: payload.ai ?? get().ai,
          stage: payload.stage ?? 'IDLE',
        })
        break
      }
      case 'SESSION_STARTED': {
        const payload = event.payload as { ai?: AiStatus }
        set({ ai: payload.ai ?? get().ai, completed: false, audioActive: true })
        void get().refresh()
        break
      }
      case 'SESSION_STATUS': {
        const payload = event.payload as { status: Session['status']; duration_seconds: number; ai?: AiStatus }
        const session = get().session
        set({
          session: session ? { ...session, status: payload.status, duration_seconds: payload.duration_seconds } : session,
          ai: payload.ai ?? get().ai,
          audioActive: payload.status === 'LIVE',
        })
        break
      }
      case 'AUDIO_STATUS': {
        const payload = event.payload as { timeline_seconds: number; voice_activity: boolean }
        set({ timelineSeconds: payload.timeline_seconds, audioActive: payload.voice_activity })
        break
      }
      case 'TRANSCRIPT_UPDATE': {
        const payload = event.payload as { segments: TranscriptSegment[]; replace?: boolean }
        set({
          segments: payload.replace ? payload.segments : mergeSegments(get().segments, payload.segments ?? []),
        })
        break
      }
      case 'DIARIZATION_UPDATE': {
        const payload = event.payload as { speakers: Speaker[] }
        if (payload.speakers) set({ speakers: payload.speakers })
        break
      }
      case 'ENTITY_UPDATE': {
        const payload = event.payload as { entities: ClinicalEntity[] }
        set({ entities: payload.entities ?? [] })
        break
      }
      case 'NOTE_UPDATE': {
        const payload = event.payload as {
          note: ClinicalNote
          changed_sections: string[]
          change_summary: string
          ai?: AiStatus
        }
        set({
          note: payload.note ?? get().note,
          ai: payload.ai ?? get().ai,
          lastNoteChange: {
            sections: payload.changed_sections ?? [],
            summary: payload.change_summary ?? '',
            at: event.emitted_at,
          },
        })
        break
      }
      case 'EVIDENCE_UPDATE': {
        const payload = event.payload as { evidence: EvidenceLink[] }
        set({ evidence: payload.evidence ?? [] })
        break
      }
      case 'PROCESSING_STATUS': {
        const payload = event.payload as { stage: ProcessingStage; detail: string; ai?: AiStatus }
        set({ stage: payload.stage, stageDetail: payload.detail, ai: payload.ai ?? get().ai })
        break
      }
      case 'PROCESSING_ERROR': {
        const payload = event.payload as {
          code: string
          message: string
          stage: string
          recoverable: boolean
          ai?: AiStatus
        }
        set({
          errors: [{ ...payload, at: event.emitted_at }],
          ai: payload.ai ?? get().ai,
        })
        break
      }
      case 'SESSION_COMPLETED': {
        const payload = event.payload as { status: Session['status']; duration_seconds: number }
        const session = get().session
        set({
          completed: true,
          audioActive: false,
          stage: 'IDLE',
          session: session
            ? { ...session, status: payload.status, duration_seconds: payload.duration_seconds }
            : session,
        })
        void get().refresh()
        break
      }
      default:
        break
    }
  },

  selectSegment: (ref) => set({ selectedSegmentRef: ref }),
  focusEvidence: (focus) => set({ evidenceFocus: focus }),
  setSession: (session) => set({ session }),
  setNote: (note) => set({ note }),
  dismissError: (code) => set({ errors: get().errors.filter((error) => error.code !== code) }),
}))

/** Evidence links grouped by their target (section key or entity ref). */
export function selectEvidenceByTarget(evidence: EvidenceLink[]): Record<string, EvidenceLink[]> {
  return evidence.reduce<Record<string, EvidenceLink[]>>((grouped, link) => {
    grouped[link.target_key] = [...(grouped[link.target_key] ?? []), link]
    return grouped
  }, {})
}
