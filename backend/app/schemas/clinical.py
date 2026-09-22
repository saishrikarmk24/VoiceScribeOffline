"""Clinical data contracts.

These models are used in three places at once:

* the REST/WebSocket API surface,
* the response schema handed to Gemini for structured output,
* validation of whatever the model returns.

Keeping one definition prevents the AI layer and the API from drifting apart.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import EntityStatus, EntityType, NoteStatus


SECTION_KEYS: tuple[str, ...] = (
    "chief_complaint",
    "history_of_present_illness",
    "relevant_medical_history",
    "social_history",
    "family_history",
    "menstrual_history",
    "physical_examination",
    "current_medication",
    "allergies",
    "treatment_history",
    "previous_investigation",
    "assessment",
    "plan",
    "follow_up",
)

ENTITY_KEYS: tuple[str, ...] = (
    "medications",
    "symptoms",
    "findings",
    "investigations",
)

SECTION_LABELS: dict[str, str] = {
    "chief_complaint": "Presenting Complaint",
    "history_of_present_illness": "History of Present Illness",
    "relevant_medical_history": "Past History",
    "social_history": "Social History",
    "family_history": "Family History",
    "menstrual_history": "Menstrual History",
    "physical_examination": "Physical Examination",
    "current_medication": "Current Medication",
    "allergies": "Allergies",
    "treatment_history": "Treatment History",
    "previous_investigation": "Previous Investigation",
    "assessment": "Assessment and Plan",
    "plan": "Plan Of Care",
    "follow_up": "Follow-up",
}


class EvidenceReference(BaseModel):
    """A pointer from a clinical statement back into the transcript."""

    model_config = ConfigDict(from_attributes=True)

    transcript_segment_ref: str = Field(description="Short transcript segment id, e.g. seg_003")
    speaker_label: str | None = None
    speaker_role: str | None = None
    timestamp: float | None = None
    confidence: float = 0.0
    source_text: str | None = None
    validated: bool = False
    validation_error: str | None = None

    @field_validator("confidence")
    @classmethod
    def _clamp(cls, value: float) -> float:
        return min(max(value, 0.0), 1.0)


class ClinicalEntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ref: str
    entity_type: EntityType
    value: str
    normalized_value: str | None = None
    normalized_code: str | None = None
    terminology_system: str | None = None
    status: EntityStatus = EntityStatus.UNKNOWN
    confidence: float = 0.0
    source_segment_refs: list[str] = Field(default_factory=list)
    detail: str | None = None
    review_required: bool = False
    review_reason: str | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)


class ClinicalSection(BaseModel):
    """A narrative section of the clinical note with its provenance."""

    text: str = "Not mentioned"
    confidence: float = 0.0
    evidence: list[EvidenceReference] = Field(default_factory=list)
    review_required: bool = False
    review_reason: str | None = None
    edited_by_human: bool = False

    @field_validator("confidence")
    @classmethod
    def _clamp(cls, value: float) -> float:
        return min(max(value, 0.0), 1.0)


class ClinicalNoteContent(BaseModel):
    """The full clinical note document (stored as JSON on ``clinical_notes``)."""

    chief_complaint: ClinicalSection = Field(default_factory=ClinicalSection)
    history_of_present_illness: ClinicalSection = Field(default_factory=ClinicalSection)
    relevant_medical_history: ClinicalSection = Field(default_factory=ClinicalSection)
    social_history: ClinicalSection = Field(default_factory=ClinicalSection)
    family_history: ClinicalSection = Field(default_factory=ClinicalSection)
    menstrual_history: ClinicalSection = Field(default_factory=ClinicalSection)
    physical_examination: ClinicalSection = Field(default_factory=ClinicalSection)
    current_medication: ClinicalSection = Field(default_factory=ClinicalSection)
    allergies: ClinicalSection = Field(default_factory=ClinicalSection)
    treatment_history: ClinicalSection = Field(default_factory=ClinicalSection)
    previous_investigation: ClinicalSection = Field(default_factory=ClinicalSection)

    medications: list[ClinicalEntityOut] = Field(default_factory=list)
    symptoms: list[ClinicalEntityOut] = Field(default_factory=list)
    findings: list[ClinicalEntityOut] = Field(default_factory=list)
    investigations: list[ClinicalEntityOut] = Field(default_factory=list)

    assessment: ClinicalSection = Field(default_factory=ClinicalSection)
    plan: ClinicalSection = Field(default_factory=ClinicalSection)
    follow_up: ClinicalSection = Field(default_factory=ClinicalSection)

    generated_at: str | None = None
    model: str | None = None
    version: int = 0

    def sections(self) -> dict[str, ClinicalSection]:
        return {key: getattr(self, key) for key in SECTION_KEYS if hasattr(self, key)}

    def entity_groups(self) -> dict[str, list[ClinicalEntityOut]]:
        return {key: getattr(self, key) for key in ENTITY_KEYS if hasattr(self, key)}


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    status: NoteStatus
    version: int
    content: ClinicalNoteContent
    review_flags: list[dict[str, Any]] = Field(default_factory=list)
    model: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    exported_at: str | None = None
    updated_at: str | None = None


class NoteVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: int
    status: NoteStatus
    change_summary: str | None = None
    changed_sections: list[str] = Field(default_factory=list)
    author_type: str = "AI"
    author: str | None = None
    model: str | None = None
    created_at: str | None = None


class SectionEdit(BaseModel):
    text: str


class NotePatch(BaseModel):
    """Human edits. Only the supplied sections are replaced."""

    chief_complaint: str | None = None
    history_of_present_illness: str | None = None
    relevant_medical_history: str | None = None
    social_history: str | None = None
    family_history: str | None = None
    menstrual_history: str | None = None
    physical_examination: str | None = None
    current_medication: str | None = None
    allergies: str | None = None
    treatment_history: str | None = None
    previous_investigation: str | None = None
    assessment: str | None = None
    plan: str | None = None
    follow_up: str | None = None
    editor: str | None = None

    def changes(self) -> dict[str, str]:
        return {
            key: value
            for key, value in self.model_dump(exclude={"editor"}).items()
            if value is not None
        }


class NoteApproval(BaseModel):
    approved_by: str | None = None
    acknowledgement: bool = Field(
        default=False,
        description="The reviewer confirms they have read the note and its evidence.",
    )


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_kind: str
    target_key: str
    clinical_statement: str
    segment_ref: str | None = None
    speaker_label: str | None = None
    speaker_role: str | None = None
    source_text: str | None = None
    timestamp: float | None = None
    confidence: float = 0.0
    validated: bool = False
    validation_error: str | None = None
