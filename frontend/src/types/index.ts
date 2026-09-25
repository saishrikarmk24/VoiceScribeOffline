/** Contracts mirrored from the backend Pydantic schemas. */

export type SessionStatus =
  | 'CREATED'
  | 'LIVE'
  | 'PAUSED'
  | 'PROCESSING'
  | 'REVIEW'
  | 'APPROVED'
  | 'COMPLETED'

export type SessionMode = 'DEMO' | 'MICROPHONE' | 'UPLOAD'
export type AudioSource = 'MICROPHONE' | 'UPLOAD' | 'SIMULATION'
export type EncounterType =
  | 'OSCE'
  | 'WARD_ROUND'
  | 'OUTPATIENT'
  | 'EMERGENCY'
  | 'TEACHING'
  | 'MEETING'
  | 'MDT'
  | 'OTHER'

export type SpeakerRole = 'DOCTOR' | 'PATIENT' | 'NURSE' | 'STAFF' | 'BACKGROUND' | 'UNKNOWN'

export type EntityType =
  | 'SYMPTOM'
  | 'FINDING'
  | 'MEDICATION'
  | 'ALLERGY'
  | 'DIAGNOSIS_MENTIONED'
  | 'PROCEDURE'
  | 'INVESTIGATION'
  | 'DURATION'
  | 'SEVERITY'
  | 'FREQUENCY'
  | 'CHARACTER'
  | 'PLAN'
  | 'FOLLOW_UP'
  | 'MEDICAL_HISTORY'

export type EntityStatus = 'PRESENT' | 'NEGATED' | 'UNCERTAIN' | 'HISTORICAL' | 'UNKNOWN'

export type NoteStatus = 'PROCESSING' | 'DRAFT' | 'REVIEW_REQUIRED' | 'APPROVED' | 'EXPORTED'

export type NoteSectionKey =
  | 'chief_complaint'
  | 'history_of_present_illness'
  | 'relevant_medical_history'
  | 'social_history'
  | 'family_history'
  | 'menstrual_history'
  | 'physical_examination'
  | 'current_medication'
  | 'allergies'
  | 'treatment_history'
  | 'previous_investigation'
  | 'assessment'
  | 'plan'
  | 'follow_up'

export type EntityGroupKey = 'medications' | 'symptoms' | 'findings' | 'investigations'

export type ProcessingStage =
  | 'AUDIO_CAPTURE'
  | 'AUDIO_PREPROCESSING'
  | 'DIARIZATION'
  | 'ROLE_ATTRIBUTION'
  | 'ASR'
  | 'TRANSCRIPT_ASSEMBLY'
  | 'CLINICAL_NLP'
  | 'LLM_STRUCTURING'
  | 'EVIDENCE_LINKING'
  | 'NOTE_STATE'
  | 'IDLE'

export type ExportFormat = 'JSON' | 'PDF' | 'FHIR'

export interface Speaker {
  id: string
  label: string
  display_name: string | null
  role: SpeakerRole
  confidence: number
  role_source: 'SYSTEM' | 'HUMAN' | string
}

export interface TranscriptSegment {
  id: string
  ref: string
  sequence: number
  speaker_id: string | null
  speaker_label: string | null
  role: SpeakerRole
  text: string
  start_time: number
  end_time: number
  confidence: number
  asr_confidence: number
  diarization_confidence: number
  overlapping: boolean
  is_final: boolean
}

export interface EvidenceReference {
  transcript_segment_ref: string
  speaker_label: string | null
  speaker_role: string | null
  timestamp: number | null
  confidence: number
  source_text: string | null
  validated: boolean
  validation_error: string | null
}

export interface ClinicalEntity {
  id: string
  ref: string
  entity_type: EntityType
  value: string
  normalized_value: string | null
  normalized_code: string | null
  terminology_system: string | null
  status: EntityStatus
  confidence: number
  source_segment_refs: string[]
  detail: string | null
  review_required: boolean
  review_reason: string | null
  evidence: EvidenceReference[]
}

export interface ClinicalSection {
  text: string
  confidence: number
  evidence: EvidenceReference[]
  review_required: boolean
  review_reason: string | null
  edited_by_human: boolean
}

export interface ClinicalNoteContent
  extends Record<NoteSectionKey, ClinicalSection>,
    Record<EntityGroupKey, ClinicalEntity[]> {
  generated_at: string | null
  model: string | null
  version: number
}

export interface ReviewFlag {
  section: string
  label: string
  reason: string
  severity: 'ERROR' | 'WARNING' | 'INFO' | string
}

export interface ClinicalNote {
  id: string
  session_id: string
  status: NoteStatus
  version: number
  content: ClinicalNoteContent
  review_flags: ReviewFlag[]
  model: string | null
  approved_by: string | null
  approved_at: string | null
  exported_at: string | null
  updated_at: string | null
}

export interface NoteVersion {
  id: string
  version: number
  status: NoteStatus
  change_summary: string | null
  changed_sections: string[]
  author_type: 'AI' | 'HUMAN' | string
  author: string | null
  model: string | null
  created_at: string | null
}

export interface EvidenceLink {
  id: string
  target_kind: 'SECTION' | 'ENTITY' | string
  target_key: string
  clinical_statement: string
  segment_ref: string | null
  speaker_label: string | null
  speaker_role: string | null
  source_text: string | null
  timestamp: number | null
  confidence: number
  validated: boolean
  validation_error: string | null
}

export interface Session {
  id: string
  reference: string
  name: string
  patient_id: string
  patient_name?: string | null
  scenario: string | null
  simulation_type: EncounterType
  doctor_name: string | null
  faculty_name: string | null
  status: SessionStatus
  mode: SessionMode
  audio_source: AudioSource
  ai_mode: string
  model_name: string
  started_at: string | null
  ended_at: string | null
  created_at: string
  updated_at: string
  last_error: string | null
  duration_seconds: number
  segment_count: number
  entity_count: number
  note_status: string | null
  note_version: number
  speakers: Speaker[]
}

export interface SessionSummary {
  id: string
  reference: string
  name: string
  patient_id: string
  patient_name?: string | null
  status: SessionStatus
  mode: SessionMode
  simulation_type: EncounterType
  created_at: string
  started_at: string | null
  ended_at: string | null
  duration_seconds: number
  segment_count: number
  entity_count: number
  note_status: string | null
}

export interface DashboardStats {
  active_sessions: number
  completed_sessions: number
  total_sessions: number
  notes_generated: number
  notes_approved: number
  total_segments: number
  total_entities: number
  average_note_latency_ms: number
  average_gemini_latency_ms: number
  review_required_count: number
  recent_sessions: SessionSummary[]
  sessions_by_day: { date: string; sessions: number }[]
  entity_distribution: { type: string; count: number }[]
}

export interface AiStatus {
  provider: string
  model: string
  mock: boolean
  degraded: boolean
  configured: boolean
  last_error?: { code: string; message: string; purpose?: string } | null
}

export interface SystemStatus {
  environment: string
  version: string
  database: {
    connected: boolean
    dialect: string
    using_fallback: boolean
    url: string
    error?: string
  }
  ai: Record<string, unknown> & {
    provider: string
    model: string
    mode: string
    gemini_configured: boolean
  }
  providers: {
    asr: { name: string; mock: boolean }
    diarization: { name: string; mock: boolean }
    terminology: Record<string, unknown>
    security: Record<string, unknown>
  }
  websocket: { connections: number; sessions: number }
  demo_mode_enabled: boolean
  pipeline?: Record<string, string>
}

export interface AudioChunk {
  id: string
  sequence: number
  source: string
  start_time: number
  end_time: number
  sample_rate: number
  channels: number
  size_bytes: number
  speech_ratio: number
  rms_dbfs: number
  status: string
}

export type SocketEventType =
  | 'SESSION_STARTED'
  | 'SESSION_STATUS'
  | 'AUDIO_STATUS'
  | 'DIARIZATION_UPDATE'
  | 'TRANSCRIPT_UPDATE'
  | 'ENTITY_UPDATE'
  | 'NOTE_UPDATE'
  | 'EVIDENCE_UPDATE'
  | 'PROCESSING_STATUS'
  | 'PROCESSING_ERROR'
  | 'SESSION_COMPLETED'
  | 'STATE_SNAPSHOT'
  | 'PONG'

export interface SocketEvent<T = Record<string, unknown>> {
  type: SocketEventType
  session_id: string
  payload: T
  emitted_at: string
  sequence: number
}

export interface StateSnapshot {
  session: Session
  segments: TranscriptSegment[]
  speakers: Speaker[]
  entities: ClinicalEntity[]
  note: ClinicalNote | null
  evidence: EvidenceLink[]
  ai: AiStatus
  stage: ProcessingStage
  providers: SystemStatus['providers'] | null
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface AuthUser {
  id: string
  email: string
  full_name: string
  doctor_id?: string | null
  department?: string | null
  role: 'ADMIN' | 'DOCTOR' | 'FACULTY' | 'STUDENT'
  is_active: boolean
  created_at?: string | null
  last_login_at?: string | null
}

export interface AuthResponse {
  token: string
  token_type: string
  expires_in_hours: number
  user: AuthUser
}

export interface DoctorCreatePayload {
  doctor_id: string
  full_name: string
  email: string
  department: string
  password: string
}

