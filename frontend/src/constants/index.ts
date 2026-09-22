import type {
  EntityStatus,
  EntityType,
  NoteSectionKey,
  NoteStatus,
  ProcessingStage,
  SessionStatus,
  SpeakerRole,
} from '@/types'

export const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'
export const WS_BASE = import.meta.env.VITE_WS_BASE ?? ''

export const CONFIDENCE_TOOLTIP = 'Model confidence is not a measure of clinical correctness.'

export const SPEAKER_ROLES: SpeakerRole[] = [
  'DOCTOR',
  'PATIENT',
  'NURSE',
  'STAFF',
  'BACKGROUND',
  'UNKNOWN',
]

export const ROLE_STYLES: Record<SpeakerRole, { label: string; badge: string; accent: string; dot: string }> = {
  DOCTOR: {
    label: 'Doctor',
    badge: 'border-[#BCE1D6] bg-[#D8ECE5] text-[#134E4A] dark:border-teal-800 dark:bg-teal-950/70 dark:text-teal-300',
    accent: 'border-l-[#134E4A]',
    dot: 'bg-[#134E4A]',
  },
  PATIENT: {
    label: 'Patient',
    badge: 'border-[#BAE6FD] bg-[#D9EDF8] text-[#0369A1] dark:border-sky-800 dark:bg-sky-950/70 dark:text-sky-300',
    accent: 'border-l-[#0369A1]',
    dot: 'bg-[#0369A1]',
  },
  NURSE: {
    label: 'Nurse',
    badge: 'border-[#DDD6FE] bg-[#E5DEFA] text-[#4C1D95] dark:border-purple-800 dark:bg-purple-950/70 dark:text-purple-300',
    accent: 'border-l-[#4C1D95]',
    dot: 'bg-[#4C1D95]',
  },
  STAFF: {
    label: 'Staff',
    badge: 'border-[#FDE68A] bg-[#FEF0C3] text-[#78350F] dark:border-amber-800 dark:bg-amber-950/70 dark:text-amber-300',
    accent: 'border-l-[#78350F]',
    dot: 'bg-[#78350F]',
  },
  BACKGROUND: {
    label: 'Background',
    badge: 'border-slate-200 bg-slate-100 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300',
    accent: 'border-l-slate-400',
    dot: 'bg-slate-400',
  },
  UNKNOWN: {
    label: 'Unknown',
    badge: 'border-slate-200 bg-white text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400',
    accent: 'border-l-slate-300',
    dot: 'bg-slate-300',
  },
}

export const SESSION_STATUS_STYLES: Record<SessionStatus, string> = {
  CREATED: 'border-navy-200 bg-navy-50 text-navy-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300',
  LIVE: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-950/60 dark:text-rose-300',
  PAUSED: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300',
  PROCESSING: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300',
  REVIEW: 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300',
  APPROVED: 'border-green-200 bg-green-50 text-green-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300',
  COMPLETED: 'border-navy-200 bg-navy-50 text-navy-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300',
}

export const NOTE_STATUS_STYLES: Record<NoteStatus, string> = {
  PROCESSING: 'border-navy-200 bg-navy-50 text-navy-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300',
  DRAFT: 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/60 dark:text-blue-300',
  REVIEW_REQUIRED: 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300',
  APPROVED: 'border-green-200 bg-green-50 text-green-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300',
  EXPORTED: 'border-teal-200 bg-teal-50 text-teal-700 dark:border-teal-800 dark:bg-teal-950/60 dark:text-teal-300',
}

export const NOTE_STATUS_LABELS: Record<NoteStatus, string> = {
  PROCESSING: 'Drafting Note',
  DRAFT: 'Draft Note',
  REVIEW_REQUIRED: 'Needs Review',
  APPROVED: 'Signed & Approved',
  EXPORTED: 'Exported to EHR',
}

export const SECTION_ORDER: NoteSectionKey[] = [
  'chief_complaint',
  'history_of_present_illness',
  'relevant_medical_history',
  'social_history',
  'family_history',
  'menstrual_history',
  'physical_examination',
  'current_medication',
  'allergies',
  'treatment_history',
  'previous_investigation',
  'assessment',
  'plan',
  'follow_up',
]

export const SECTION_LABELS: Record<NoteSectionKey, string> = {
  chief_complaint: 'Presenting Complaint',
  history_of_present_illness: 'History of Present Illness',
  relevant_medical_history: 'Past History',
  social_history: 'Social History',
  family_history: 'Family History',
  menstrual_history: 'Menstrual History',
  physical_examination: 'Physical Examination',
  current_medication: 'Current Medication',
  allergies: 'Allergies',
  treatment_history: 'Treatment History',
  previous_investigation: 'Previous Investigation',
  assessment: 'Assessment and Plan',
  plan: 'Plan Of Care',
  follow_up: 'Follow-up & Next Steps',
}

export const MOM_SECTION_LABELS: Partial<Record<NoteSectionKey, string>> = {
  chief_complaint: 'Meeting Agenda & Objectives',
  history_of_present_illness: 'Discussion & Member Contributions',
  relevant_medical_history: 'Context & Prior Follow-ups',
  assessment: 'Key Findings & Deliberations',
  plan: 'Decisions & Approved Resolutions',
  follow_up: 'Action Items & Assigned Responsibilities',
}

export const SECTION_HINTS: Record<NoteSectionKey, string> = {
  chief_complaint: 'The main presenting symptoms or reasons for consultation.',
  history_of_present_illness: 'Detailed symptoms, timeline, laterality, and triggers.',
  relevant_medical_history: 'Past health conditions, surgeries, and chronic illnesses.',
  social_history: 'Lifestyle, exercise, gym, diet, supplements, and habits.',
  family_history: 'Familial and hereditary conditions.',
  menstrual_history: 'Menstrual/gynecological history.',
  physical_examination: 'Physical exam findings and vitals (BP, glucose, pulse, temp, SpO2).',
  current_medication: 'Active medications, daily supplements, and vitamins.',
  allergies: 'Documented drug, food, or environmental allergies.',
  treatment_history: 'Prior treatments, OTC medications tried, and their relief.',
  previous_investigation: 'Past lab tests, radiology, MRI, CT, or ECG reports.',
  assessment: 'Clinical impressions and diagnostic observations stated by the doctor.',
  plan: 'Prescriptions, orders, lifestyle recommendations, and treatment plan.',
  follow_up: 'Follow-up timeline and return precautions.',
}

export const ENTITY_GROUPS: { key: EntityType[]; title: string }[] = [
  { title: 'Symptoms Reported', key: ['SYMPTOM'] },
  { title: 'Medications Discussed', key: ['MEDICATION'] },
  { title: 'Allergies Mentioned', key: ['ALLERGY'] },
  { title: 'Examination Findings', key: ['FINDING'] },
  { title: 'Lab & Diagnostic Tests', key: ['INVESTIGATION', 'PROCEDURE'] },
  { title: 'Symptom Qualifiers', key: ['DURATION', 'SEVERITY', 'FREQUENCY', 'CHARACTER'] },
  { title: 'Past Medical History', key: ['MEDICAL_HISTORY'] },
  { title: 'Treatment & Follow-up', key: ['PLAN', 'FOLLOW_UP'] },
  { title: 'Diagnoses Discussed', key: ['DIAGNOSIS_MENTIONED'] },
]

export const ENTITY_STATUS_STYLES: Record<EntityStatus, string> = {
  PRESENT: 'border-teal-200 bg-teal-50 text-teal-700 dark:border-teal-800 dark:bg-teal-950/60 dark:text-teal-300',
  NEGATED: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-950/60 dark:text-rose-300',
  UNCERTAIN: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300',
  HISTORICAL: 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-950/60 dark:text-violet-300',
  UNKNOWN: 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300',
}

export const ENTITY_STATUS_LABELS: Record<EntityStatus, string> = {
  PRESENT: 'Reported',
  NEGATED: 'Denied',
  UNCERTAIN: 'Uncertain',
  HISTORICAL: 'Past History',
  UNKNOWN: 'Noted',
}

export const PIPELINE_STAGES: { stage: ProcessingStage; label: string }[] = [
  { stage: 'AUDIO_CAPTURE', label: 'Audio Recording' },
  { stage: 'AUDIO_PREPROCESSING', label: 'Audio Cleanup' },
  { stage: 'DIARIZATION', label: 'Speaker Separation' },
  { stage: 'ROLE_ATTRIBUTION', label: 'Doctor/Patient Tagging' },
  { stage: 'ASR', label: 'Speech-to-Text' },
  { stage: 'TRANSCRIPT_ASSEMBLY', label: 'Transcript Generation' },
  { stage: 'CLINICAL_NLP', label: 'Medical Fact Extraction' },
  { stage: 'LLM_STRUCTURING', label: 'Clinical Note Structuring' },
  { stage: 'EVIDENCE_LINKING', label: 'Transcript Citation' },
  { stage: 'NOTE_STATE', label: 'Clinical Note Ready' },
]

export const ENCOUNTER_TYPES: { value: string; label: string }[] = [
  { value: 'MEETING', label: 'College Leadership / Department Heads Meeting (MoM)' },
  { value: 'MDT', label: 'Hospital Multi-Disciplinary Team / MDT Board' },
  { value: 'OUTPATIENT', label: 'Outpatient Visit / Clinic' },
  { value: 'WARD_ROUND', label: 'Inpatient / Ward Round' },
  { value: 'EMERGENCY', label: 'Emergency / Urgent Care' },
  { value: 'OSCE', label: 'Clinical Examination / OSCE' },
  { value: 'TEACHING', label: 'Academic / Case Review' },
  { value: 'OTHER', label: 'General Consultation' },
]

export const SAFETY_NOTICE =
  'VoiceScribe AI documents what was said in the encounter. It does not diagnose, ' +
  'recommend treatment, or replace clinical judgement. Human review is required.'
