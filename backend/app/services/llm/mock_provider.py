"""Deterministic clinical structuring provider (no external API calls).

Used in three situations:

* ``AI_MODE=mock`` (offline demos, CI, unit tests);
* ``GEMINI_API_KEY`` missing;
* Gemini failed after its bounded retries - the session degrades to this
  provider and the note is flagged REVIEW_REQUIRED rather than lost.

It shares the rule engine with :mod:`app.services.nlp`, so its behaviour on
negation and uncertainty is identical to the pre-pass that grounds Gemini.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.models.enums import EntityStatus, EntityType, SpeakerRole
from app.services.llm.base import ExtractionResponse, LLMCallStats, LLMProvider, NoteResponse
from app.services.llm.schemas import (
    ExtractedEntity,
    ExtractionResult,
    GeneratedNote,
    GeneratedSection,
    NoteUpdate,
)
from app.services.nlp.clinical_nlp import ClinicalNLPService
from app.services.types import AssembledSegment

logger = get_logger(__name__)

NOT_MENTIONED = "Not mentioned"


def _to_assembled(segment: dict[str, Any]) -> AssembledSegment:
    role = segment.get("role", SpeakerRole.UNKNOWN)
    if isinstance(role, str):
        try:
            role = SpeakerRole(role.upper())
        except ValueError:
            role = SpeakerRole.UNKNOWN
    return AssembledSegment(
        ref=str(segment.get("ref", "seg_000")),
        speaker_label=str(segment.get("speaker_label", "unknown")),
        role=role,
        text=str(segment.get("text", "")),
        start_time=float(segment.get("start_time", 0.0)),
        end_time=float(segment.get("end_time", 0.0)),
        confidence=float(segment.get("confidence", 0.0)),
        asr_confidence=float(segment.get("asr_confidence", 0.0)),
        diarization_confidence=float(segment.get("diarization_confidence", 0.0)),
    )


class DeterministicLLMProvider(LLMProvider):
    name = "rule-based"
    model = "medscribe-rules-v1"
    is_mock = True

    def __init__(self, nlp: ClinicalNLPService | None = None) -> None:
        self.nlp = nlp or ClinicalNLPService()

    async def extract_entities(
        self,
        *,
        session_context: dict[str, Any],
        segments: list[dict[str, Any]],
        rule_based_candidates: list[dict[str, Any]] | None = None,
        existing_entities: list[dict[str, Any]] | None = None,
    ) -> ExtractionResponse:
        assembled = [_to_assembled(segment) for segment in segments]
        candidates = self.nlp.extract(assembled)
        entities = [
            ExtractedEntity(
                entity_type=candidate.entity_type,
                value=candidate.value,
                status=candidate.status,
                confidence=candidate.confidence,
                source_segment_ids=list(candidate.source_segment_refs),
                detail=candidate.detail,
            )
            for candidate in candidates
        ]
        return ExtractionResponse(
            result=ExtractionResult(entities=entities),
            stats=LLMCallStats(provider=self.name, model=self.model, fallback_used=True),
        )

    async def generate_note(
        self,
        *,
        session_context: dict[str, Any],
        segments: list[dict[str, Any]],
        entities: list[dict[str, Any]],
        current_note: dict[str, Any] | None = None,
    ) -> NoteResponse:
        assembled = [_to_assembled(segment) for segment in segments]
        grouped = self._group(entities)
        note = GeneratedNote(
            chief_complaint=self._chief_complaint(grouped, assembled),
            history_of_present_illness=self._hpi(grouped, assembled),
            relevant_medical_history=self._history(grouped, assembled),
            social_history=self._social_history(grouped, assembled),
            family_history=self._family_history(grouped, assembled),
            menstrual_history=self._menstrual_history(grouped, assembled),
            physical_examination=self._physical_examination(grouped, assembled),
            current_medication=self._current_medication(grouped, assembled),
            allergies=self._allergies(grouped, assembled),
            treatment_history=self._treatment_history(grouped, assembled),
            previous_investigation=self._investigations(grouped, assembled),
            assessment=self._assessment(grouped, assembled),
            plan=self._plan(grouped, assembled),
            follow_up=self._follow_up(grouped, assembled),
        )
        changed = self._changed_sections(note, current_note)
        return NoteResponse(
            result=NoteUpdate(
                note=note,
                changed_sections=changed,
                change_summary="Rule-based structuring (deterministic provider).",
            ),
            stats=LLMCallStats(provider=self.name, model=self.model, fallback_used=True),
        )

    async def check_connection(self) -> dict[str, Any]:
        return {"connected": True, "model": self.model, "provider": self.name, "mock": True}

    # --------------------------------------------------------------- composition
    @staticmethod
    def _group(entities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for entity in entities:
            entity_type = entity.get("entity_type")
            key = entity_type.value if hasattr(entity_type, "value") else str(entity_type)
            grouped.setdefault(key, []).append(entity)
        return grouped

    @staticmethod
    def _refs(entities: list[dict[str, Any]]) -> list[str]:
        refs: list[str] = []
        for entity in entities:
            for ref in entity.get("source_segment_refs") or entity.get("source_segment_ids") or []:
                if ref not in refs:
                    refs.append(ref)
        return refs

    @staticmethod
    def _status(entity: dict[str, Any]) -> str:
        status = entity.get("status", EntityStatus.UNKNOWN)
        return status.value if hasattr(status, "value") else str(status)

    @staticmethod
    def _value(entity: dict[str, Any]) -> str:
        return str(entity.get("normalized_value") or entity.get("value") or "").strip()

    def _present(self, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [entity for entity in entities if self._status(entity) in ("PRESENT", "UNKNOWN")]

    def _negated(self, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [entity for entity in entities if self._status(entity) == "NEGATED"]

    def _uncertain(self, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [entity for entity in entities if self._status(entity) == "UNCERTAIN"]

    def _chief_complaint(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        symptoms = self._present(grouped.get(EntityType.SYMPTOM.value, []))
        durations = self._present(grouped.get(EntityType.DURATION.value, []))
        if not symptoms:
            if not segments:
                return GeneratedSection(text="", confidence=0.0, source_segment_ids=[])
            first = segments[0]
            return GeneratedSection(
                text=f"Patient presents with: {first.text.rstrip('.')}.",
                confidence=round(first.confidence * 0.8, 4),
                source_segment_ids=[first.ref],
            )
        primary = symptoms[0]
        text = f"Patient presents with {self._value(primary)}"
        refs = list(primary.get("source_segment_refs") or primary.get("source_segment_ids") or [])
        if not refs and segments:
            refs = [segments[0].ref]
        if durations:
            text += f" of {self._value(durations[0])} duration"
            refs += [ref for ref in self._refs([durations[0]]) if ref not in refs]
        return GeneratedSection(text=text.strip() + ".", confidence=0.86, source_segment_ids=refs)

    def _hpi(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        symptoms = grouped.get(EntityType.SYMPTOM.value, [])
        sentences: list[str] = []
        refs: list[str] = []

        present = self._present(symptoms)
        if present:
            sentences.append("Patient describes experiencing " + ", ".join(self._value(e) for e in present) + ".")
            refs += self._refs(present)

        qualifiers = [
            ("Character of symptoms", grouped.get(EntityType.CHARACTER.value, [])),
            ("Severity level", grouped.get(EntityType.SEVERITY.value, [])),
            ("Frequency of episodes", grouped.get(EntityType.FREQUENCY.value, [])),
            ("Reported duration", grouped.get(EntityType.DURATION.value, [])),
        ]
        for label, items in qualifiers:
            usable = self._present(items)
            if usable:
                sentences.append(f"{label}: " + ", ".join(self._value(e) for e in usable) + ".")
                refs += [ref for ref in self._refs(usable) if ref not in refs]

        meds = self._present(grouped.get(EntityType.MEDICATION.value, []))
        if meds:
            sentences.append("Patient notes taking " + ", ".join(self._value(e) for e in meds) + " for symptom relief.")
            refs += [ref for ref in self._refs(meds) if ref not in refs]

        negated = self._negated(symptoms)
        if negated:
            sentences.append("Patient explicitly denies " + ", ".join(self._value(e) for e in negated) + ".")
            refs += [ref for ref in self._refs(negated) if ref not in refs]

        uncertain = self._uncertain(symptoms)
        if uncertain:
            sentences.append(
                "Uncertain report of " + ", ".join(self._value(e) for e in uncertain) + " (pending clinical evaluation)."
            )
            refs += [ref for ref in self._refs(uncertain) if ref not in refs]

        if not sentences:
            if not segments:
                return GeneratedSection(text="", confidence=0.0, source_segment_ids=[])
            return GeneratedSection(
                text=f"Patient reports: {segments[0].text.rstrip('.')}.",
                confidence=0.80,
                source_segment_ids=[segments[0].ref],
            )
        if not refs and segments:
            refs = [segments[0].ref]
        return GeneratedSection(text=" ".join(sentences), confidence=0.85, source_segment_ids=list(dict.fromkeys(refs)))

    def _history(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        history = grouped.get(EntityType.MEDICAL_HISTORY.value, [])
        procedures = grouped.get(EntityType.PROCEDURE.value, [])
        items = self._present(history) + self._present(procedures)
        if not items:
            return GeneratedSection(text="", confidence=0.0, source_segment_ids=[])
        refs = self._refs(items)
        if not refs and segments:
            refs = [segments[0].ref]
        return GeneratedSection(
            text="Past medical and surgical history includes: " + ", ".join(self._value(e) for e in items) + ".",
            confidence=0.80,
            source_segment_ids=refs,
        )

    def _social_history(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        return GeneratedSection(text="", confidence=0.0, source_segment_ids=[])

    def _family_history(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        return GeneratedSection(text="", confidence=0.0, source_segment_ids=[])

    def _menstrual_history(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        return GeneratedSection(text="", confidence=0.0, source_segment_ids=[])

    def _physical_examination(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        findings = self._present(grouped.get(EntityType.FINDING.value, []))
        if not findings:
            return GeneratedSection(text="", confidence=0.0, source_segment_ids=[])
        refs = self._refs(findings)
        if not refs and segments:
            refs = [segments[0].ref]
        text = "Physical examination findings: " + ", ".join(self._value(e) for e in findings) + "."
        return GeneratedSection(text=text, confidence=0.84, source_segment_ids=refs)

    def _current_medication(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        meds = self._present(grouped.get(EntityType.MEDICATION.value, []))
        if not meds:
            return GeneratedSection(text="", confidence=0.0, source_segment_ids=[])
        items: list[str] = []
        for e in meds:
            val = self._value(e)
            detail = e.get("detail")
            items.append(f"{val} ({detail})" if detail else val)
        text = "Active medications: " + ", ".join(items) + "."
        refs = self._refs(meds)
        if not refs and segments:
            refs = [segments[0].ref]
        return GeneratedSection(text=text, confidence=0.85, source_segment_ids=refs)

    def _allergies(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        allergies = self._present(grouped.get(EntityType.ALLERGY.value, []))
        if not allergies:
            return GeneratedSection(text="", confidence=0.0, source_segment_ids=[])
        refs = self._refs(allergies)
        if not refs and segments:
            refs = [segments[0].ref]
        text = "Documented allergies: " + ", ".join(self._value(e) for e in allergies) + "."
        return GeneratedSection(text=text, confidence=0.88, source_segment_ids=refs)

    def _treatment_history(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        seg_roles = {s.ref: s.role for s in segments}
        all_meds = self._present(grouped.get(EntityType.MEDICATION.value, []))
        pt_meds = []
        for e in all_meds:
            refs = e.get("source_segment_refs") or e.get("source_segment_ids") or []
            roles = [seg_roles.get(r) for r in refs if r in seg_roles]
            # Include in treatment history if spoken by patient or marked prior
            if roles and all(r == SpeakerRole.PATIENT for r in roles):
                pt_meds.append(e)
            elif str(e.get("status", "")).upper() in ("HISTORICAL", "PAST"):
                pt_meds.append(e)
        if not pt_meds:
            return GeneratedSection(text="", confidence=0.0, source_segment_ids=[])
        text = "Prior treatments and medications taken prior to presentation: " + ", ".join(self._value(e) for e in pt_meds) + "."
        refs = self._refs(pt_meds)
        if not refs and segments:
            refs = [segments[0].ref]
        return GeneratedSection(text=text, confidence=0.82, source_segment_ids=refs)

    def _investigations(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        invs = self._present(grouped.get(EntityType.INVESTIGATION.value, []))
        if not invs:
            return GeneratedSection(text="", confidence=0.0, source_segment_ids=[])
        refs = self._refs(invs)
        if not refs and segments:
            refs = [segments[0].ref]
        text = "Diagnostic investigations and lab tests: " + ", ".join(self._value(e) for e in invs) + "."
        return GeneratedSection(text=text, confidence=0.82, source_segment_ids=refs)

    def _assessment(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        diagnoses = grouped.get(EntityType.DIAGNOSIS_MENTIONED.value, [])
        stated = self._present(diagnoses)
        if not stated:
            return GeneratedSection(text=NOT_MENTIONED, confidence=0.0, source_segment_ids=[])
        refs = self._refs(stated)
        if not refs and segments:
            refs = [segments[0].ref]
        return GeneratedSection(
            text="Clinical assessment and diagnostic impression: " + ", ".join(self._value(e) for e in stated) + ".",
            confidence=0.85,
            source_segment_ids=refs,
        )

    def _plan(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        plans = self._present(grouped.get(EntityType.PLAN.value, []))
        all_meds = self._present(grouped.get(EntityType.MEDICATION.value, []))
        all_invs = self._present(grouped.get(EntityType.INVESTIGATION.value, []))

        seg_roles = {s.ref: s.role for s in segments}

        # Filter: Doctor-prescribed medications only (exclude patient-only prior medications)
        doc_meds = []
        for e in all_meds:
            refs = e.get("source_segment_refs") or e.get("source_segment_ids") or []
            roles = [seg_roles.get(r) for r in refs if r in seg_roles]
            if roles and all(r == SpeakerRole.PATIENT for r in roles):
                continue
            if str(e.get("status", "")).upper() in ("HISTORICAL", "PAST"):
                continue
            doc_meds.append(e)

        # Filter: Doctor-ordered investigations only
        doc_invs = []
        for e in all_invs:
            refs = e.get("source_segment_refs") or e.get("source_segment_ids") or []
            roles = [seg_roles.get(r) for r in refs if r in seg_roles]
            if roles and all(r == SpeakerRole.PATIENT for r in roles):
                continue
            if str(e.get("status", "")).upper() in ("HISTORICAL", "PAST"):
                continue
            doc_invs.append(e)

        parts: list[str] = []
        refs: list[str] = []
        if plans:
            parts.append("Care plan: " + "; ".join(self._value(e) for e in plans))
            refs += self._refs(plans)
        if doc_meds:
            parts.append("Prescriptions / Medication management: " + ", ".join(self._value(e) for e in doc_meds))
            refs += self._refs(doc_meds)
        if doc_invs:
            parts.append("Diagnostic orders: " + ", ".join(self._value(e) for e in doc_invs))
            refs += self._refs(doc_invs)
        if not parts:
            return GeneratedSection(text="", confidence=0.0, source_segment_ids=[])
        if not refs and segments:
            refs = [segments[0].ref]
        return GeneratedSection(
            text=". ".join(parts) + ".", confidence=0.84, source_segment_ids=list(dict.fromkeys(refs))
        )

    def _follow_up(
        self, grouped: dict[str, list[dict[str, Any]]], segments: list[AssembledSegment]
    ) -> GeneratedSection:
        followups = self._present(grouped.get(EntityType.FOLLOW_UP.value, []))
        if not followups:
            return GeneratedSection(text="", confidence=0.0, source_segment_ids=[])
        refs = self._refs(followups)
        if not refs and segments:
            refs = [segments[0].ref]
        text = "Follow-up and instructions: " + "; ".join(self._value(e) for e in followups) + "."
        return GeneratedSection(text=text, confidence=0.82, source_segment_ids=refs)

    @staticmethod
    def _changed_sections(note: GeneratedNote, current_note: dict[str, Any] | None) -> list[str]:
        if not current_note:
            return [key for key, section in note.model_dump().items() if section.get("text")]
        changed: list[str] = []
        for key, section in note.model_dump().items():
            existing = current_note.get(key) or {}
            existing_text = existing.get("text") if isinstance(existing, dict) else existing
            if section.get("text") != existing_text:
                changed.append(key)
        return changed

