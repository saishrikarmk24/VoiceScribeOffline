/**
 * REST client. The browser never talks to Gemini directly - every AI call goes
 * through the backend, which owns the API key.
 */

import { API_BASE } from '@/constants'
import type {
  AudioChunk,
  AuthResponse,
  AuthUser,
  ClinicalEntity,
  ClinicalNote,
  DashboardStats,
  DoctorCreatePayload,
  EvidenceLink,
  ExportFormat,
  NoteSectionKey,
  NoteVersion,
  Page,
  Session,
  SessionSummary,
  Speaker,
  SpeakerRole,
  SystemStatus,
  TranscriptSegment,
} from '@/types'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export interface Identity {
  token?: string
  email?: string
  role?: string
  doctor_id?: string
}

let identity: Identity = {}

export function setIdentity(next: Identity): void {
  identity = next
}

function headers(extra?: HeadersInit): HeadersInit {
  const base: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = identity.token || (typeof localStorage !== 'undefined' ? localStorage.getItem('medscribe_auth_token') : null)
  if (token) base['Authorization'] = `Bearer ${token}`
  if (identity.email) base['X-User-Email'] = identity.email
  if (identity.role) base['X-User-Role'] = identity.role
  if (identity.doctor_id) base['X-Doctor-Id'] = identity.doctor_id
  return { ...base, ...(extra as Record<string, string> | undefined) }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers: headers(init?.headers) })
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
      else if (Array.isArray(body?.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join(', ')
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export interface CreateSessionInput {
  name: string
  patient_id: string
  patient_name?: string | null
  scenario?: string | null
  simulation_type: string
  doctor_name?: string | null
  faculty_name?: string | null
  mode: string
  audio_source?: string | null
}

export const api = {
  // ---- system -------------------------------------------------------------
  health: () => request<Record<string, unknown>>('/health'),
  status: () => request<SystemStatus>('/status'),
  checkAi: () => request<Record<string, unknown>>('/ai/check'),
  metrics: () => request<{ counters: Record<string, number>; durations: Record<string, unknown> }>('/metrics'),
  scripts: () =>
    request<{ scripts: { key: string; title: string; description: string; utterances: number }[]; demo_mode_enabled: boolean }>(
      '/sessions/scripts',
    ),

  // ---- sessions -----------------------------------------------------------
  dashboard: () => request<DashboardStats>('/sessions/dashboard'),
  listSessions: (params: { limit?: number; offset?: number; status?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.limit) query.set('limit', String(params.limit))
    if (params.offset) query.set('offset', String(params.offset))
    if (params.status) query.set('status', params.status)
    const suffix = query.toString() ? `?${query}` : ''
    return request<Page<SessionSummary>>(`/sessions${suffix}`)
  },
  createSession: (input: CreateSessionInput) =>
    request<Session>('/sessions', { method: 'POST', body: JSON.stringify(input) }),
  getSession: (id: string) => request<Session>(`/sessions/${id}`),
  deleteSession: (id: string) => request<{ ok: boolean }>(`/sessions/${id}`, { method: 'DELETE' }),
  startSession: (id: string) => request<Session>(`/sessions/${id}/start`, { method: 'POST' }),
  pauseSession: (id: string) => request<Session>(`/sessions/${id}/pause`, { method: 'POST' }),
  resumeSession: (id: string) => request<Session>(`/sessions/${id}/resume`, { method: 'POST' }),
  stopSession: (id: string) => request<Session>(`/sessions/${id}/stop`, { method: 'POST' }),
  retryProcessing: (id: string) =>
    request<{ ok: boolean; message: string | null; detail: Record<string, unknown> }>(`/sessions/${id}/process`, {
      method: 'POST',
    }),

  // ---- pipeline data ------------------------------------------------------
  transcript: (id: string) => request<TranscriptSegment[]>(`/sessions/${id}/transcript`),
  speakers: (id: string) => request<Speaker[]>(`/sessions/${id}/speakers`),
  audioChunks: (id: string) => request<{ chunks: AudioChunk[] }>(`/sessions/${id}/audio-chunks`),
  entities: (id: string) => request<ClinicalEntity[]>(`/sessions/${id}/entities`),
  note: (id: string) => request<ClinicalNote>(`/sessions/${id}/note`),
  noteVersions: (id: string) => request<NoteVersion[]>(`/sessions/${id}/note/versions`),
  evidence: (id: string, targetKey?: string) =>
    request<EvidenceLink[]>(`/sessions/${id}/evidence${targetKey ? `?target_key=${encodeURIComponent(targetKey)}` : ''}`),
  evidenceDetail: (id: string, targetKey: string) =>
    request<{
      target_key: string
      clinical_statement: string | null
      chain: { evidence: EvidenceLink; segment: TranscriptSegment | null; audio_chunk_id: string | null }[]
      validated_count: number
      total_count: number
    }>(`/sessions/${id}/evidence/${encodeURIComponent(targetKey)}/detail`),
  audit: (id: string) =>
    request<{ entries: { id: string; action: string; actor_email: string; created_at: string; detail: unknown }[] }>(
      `/sessions/${id}/audit`,
    ),

  // ---- speakers / notes ---------------------------------------------------
  updateSpeakerRole: (speakerId: string, role: SpeakerRole, displayName?: string) =>
    request<Speaker>(`/speakers/${speakerId}`, {
      method: 'PATCH',
      body: JSON.stringify({ role, display_name: displayName ?? null }),
    }),
  editNote: (noteId: string, changes: Partial<Record<NoteSectionKey, string>> & { editor?: string }) =>
    request<ClinicalNote>(`/notes/${noteId}`, { method: 'PATCH', body: JSON.stringify(changes) }),
  approveNote: (noteId: string, approvedBy: string) =>
    request<ClinicalNote>(`/notes/${noteId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy, acknowledgement: true }),
    }),
  reopenNote: (noteId: string) => request<ClinicalNote>(`/notes/${noteId}/reopen`, { method: 'POST' }),

  // ---- audio --------------------------------------------------------------
  sendAudioChunk: (
    sessionId: string,
    payload: { audio_base64: string; mime_type: string; sample_rate?: number; channels?: number; duration_seconds?: number },
  ) =>
    request<{ ok: boolean; message: string | null; detail: Record<string, unknown> }>(
      `/sessions/${sessionId}/audio/chunk`,
      { method: 'POST', body: JSON.stringify(payload) },
    ),
  uploadRecording: async (sessionId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    const authHeaders: Record<string, string> = {}
    if (identity.email) authHeaders['X-User-Email'] = identity.email
    if (identity.role) authHeaders['X-User-Role'] = identity.role
    const response = await fetch(`${API_BASE}/sessions/${sessionId}/audio/upload`, {
      method: 'POST',
      body: form,
      headers: authHeaders,
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }))
      throw new ApiError(response.status, String(body.detail ?? 'Upload failed'))
    }
    return (await response.json()) as { ok: boolean; message: string | null; detail: Record<string, unknown> }
  },
  transcribeClip: async (file: File | Blob) => {
    const form = new FormData()
    form.append('file', file, 'vitals_dictation.wav')
    const authHeaders: Record<string, string> = {}
    if (identity.email) authHeaders['X-User-Email'] = identity.email
    if (identity.role) authHeaders['X-User-Role'] = identity.role
    const response = await fetch(`${API_BASE}/sessions/transcribe_clip`, {
      method: 'POST',
      body: form,
      headers: authHeaders,
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }))
      throw new ApiError(response.status, String(body.detail ?? 'Clip transcription failed'))
    }
    return (await response.json()) as { ok: boolean; message: string | null; detail?: { text?: string } }
  },

  // ---- export -------------------------------------------------------------
  exportSession: async (sessionId: string, format: ExportFormat): Promise<{ blob: Blob; filename: string }> => {
    const response = await fetch(`${API_BASE}/sessions/${sessionId}/export?format=${format}`, {
      method: 'POST',
      headers: headers(),
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }))
      throw new ApiError(response.status, String(body.detail ?? 'Export failed'))
    }
    const disposition = response.headers.get('Content-Disposition') ?? ''
    const match = /filename="?([^"]+)"?/.exec(disposition)
    return { blob: await response.blob(), filename: match?.[1] ?? `medscribe-export.${format.toLowerCase()}` }
  },
  exportPreview: (sessionId: string) =>
    request<{ json_export: Record<string, unknown>; fhir_bundle: Record<string, unknown>; fhir_resource_counts: Record<string, number> }>(
      `/sessions/${sessionId}/export/preview`,
    ),

  // ---- auth & doctor provisioning ----------------------------------------
  login: (identifier: string, password: string) =>
    request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ identifier, password }),
    }),
  adminRegister: (data: { email: string; full_name: string; password: string }) =>
    request<AuthResponse>('/auth/admin/register', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getMe: () => request<AuthUser>('/auth/me'),
  listDoctors: () => request<AuthUser[]>('/auth/doctors'),
  createDoctor: (data: DoctorCreatePayload) =>
    request<AuthUser>('/auth/doctors', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateDoctorStatus: (doctorUuid: string, isActive: boolean) =>
    request<AuthUser>(`/auth/doctors/${doctorUuid}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: isActive }),
    }),
  resetDoctorPassword: (doctorUuid: string, newPassword: string) =>
    request<{ ok: boolean; message: string | null }>(`/auth/doctors/${doctorUuid}/reset_password`, {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword }),
    }),
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
