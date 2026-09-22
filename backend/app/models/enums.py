"""Domain enumerations shared by ORM models, API schemas and the AI layer."""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.value


class SessionStatus(StrEnum):
    CREATED = "CREATED"
    LIVE = "LIVE"
    PAUSED = "PAUSED"
    PROCESSING = "PROCESSING"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"


class SessionMode(StrEnum):
    DEMO = "DEMO"
    MICROPHONE = "MICROPHONE"
    UPLOAD = "UPLOAD"


class SimulationType(StrEnum):
    OSCE = "OSCE"
    WARD_ROUND = "WARD_ROUND"
    OUTPATIENT = "OUTPATIENT"
    EMERGENCY = "EMERGENCY"
    TEACHING = "TEACHING"
    MEETING = "MEETING"
    MDT = "MDT"
    OTHER = "OTHER"


class SpeakerRole(StrEnum):
    DOCTOR = "DOCTOR"
    PATIENT = "PATIENT"
    NURSE = "NURSE"
    STAFF = "STAFF"
    BACKGROUND = "BACKGROUND"
    UNKNOWN = "UNKNOWN"


class EntityType(StrEnum):
    SYMPTOM = "SYMPTOM"
    FINDING = "FINDING"
    MEDICATION = "MEDICATION"
    ALLERGY = "ALLERGY"
    DIAGNOSIS_MENTIONED = "DIAGNOSIS_MENTIONED"
    PROCEDURE = "PROCEDURE"
    INVESTIGATION = "INVESTIGATION"
    DURATION = "DURATION"
    SEVERITY = "SEVERITY"
    FREQUENCY = "FREQUENCY"
    CHARACTER = "CHARACTER"
    PLAN = "PLAN"
    FOLLOW_UP = "FOLLOW_UP"
    MEDICAL_HISTORY = "MEDICAL_HISTORY"


class EntityStatus(StrEnum):
    PRESENT = "PRESENT"
    NEGATED = "NEGATED"
    UNCERTAIN = "UNCERTAIN"
    HISTORICAL = "HISTORICAL"
    UNKNOWN = "UNKNOWN"


class NoteStatus(StrEnum):
    PROCESSING = "PROCESSING"
    DRAFT = "DRAFT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    EXPORTED = "EXPORTED"


class NoteSectionKey(StrEnum):
    CHIEF_COMPLAINT = "chief_complaint"
    HISTORY_OF_PRESENT_ILLNESS = "history_of_present_illness"
    RELEVANT_MEDICAL_HISTORY = "relevant_medical_history"
    SOCIAL_HISTORY = "social_history"
    FAMILY_HISTORY = "family_history"
    MENSTRUAL_HISTORY = "menstrual_history"
    PHYSICAL_EXAMINATION = "physical_examination"
    CURRENT_MEDICATION = "current_medication"
    ALLERGIES = "allergies"
    TREATMENT_HISTORY = "treatment_history"
    PREVIOUS_INVESTIGATION = "previous_investigation"
    ASSESSMENT = "assessment"
    PLAN = "plan"
    FOLLOW_UP = "follow_up"


class UserRole(StrEnum):
    DOCTOR = "DOCTOR"
    STUDENT = "STUDENT"
    FACULTY = "FACULTY"
    ADMIN = "ADMIN"


class ExportFormat(StrEnum):
    JSON = "JSON"
    PDF = "PDF"
    FHIR = "FHIR"


class AudioSource(StrEnum):
    MICROPHONE = "MICROPHONE"
    UPLOAD = "UPLOAD"
    SIMULATION = "SIMULATION"
