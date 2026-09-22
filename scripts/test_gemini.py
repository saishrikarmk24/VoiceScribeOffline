#!/usr/bin/env python
"""Verify the live Gemini integration end to end.

    python scripts/test_gemini.py

Checks: API connectivity, schema-constrained structured output, Pydantic
validation, entity extraction, negation handling, evidence references and full
note generation against the reference demo conversation.

Requires GEMINI_API_KEY (see .env.example). Without a key the script explains
what to do and exits with a non-zero status.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import settings  # noqa: E402
from app.models.enums import EntityStatus, EntityType  # noqa: E402
from app.services.evidence import EvidenceLinkingService, SegmentIndexEntry  # noqa: E402
from app.services.llm.base import LLMError  # noqa: E402
from app.services.llm.gemini_provider import GeminiProvider  # noqa: E402
from app.services.llm.validator import OutputValidator  # noqa: E402
from app.services.nlp import ClinicalNLPService  # noqa: E402
from app.services.types import AssembledSegment  # noqa: E402
from app.models.enums import SpeakerRole  # noqa: E402

SEGMENTS = [
    ("seg_001", "speaker_0", SpeakerRole.DOCTOR, "Good morning. What brings you in today?", 0.0, 3.4),
    ("seg_002", "speaker_1", SpeakerRole.PATIENT, "I've been having chest discomfort since yesterday evening.", 3.4, 7.6),
    ("seg_003", "speaker_0", SpeakerRole.DOCTOR, "Can you describe the discomfort?", 7.6, 10.4),
    ("seg_004", "speaker_1", SpeakerRole.PATIENT, "It feels like pressure. It comes and goes.", 10.4, 14.0),
    ("seg_005", "speaker_0", SpeakerRole.DOCTOR, "Any shortness of breath?", 14.0, 16.4),
    ("seg_006", "speaker_1", SpeakerRole.PATIENT, "No, I don't have any shortness of breath.", 16.4, 19.8),
    ("seg_007", "speaker_0", SpeakerRole.DOCTOR, "Are you currently taking any medications?", 19.8, 22.8),
    ("seg_008", "speaker_1", SpeakerRole.PATIENT, "I'm taking metformin.", 22.8, 25.0),
    ("seg_009", "speaker_0", SpeakerRole.DOCTOR, "Do you have any known allergies?", 25.0, 27.6),
    ("seg_010", "speaker_1", SpeakerRole.PATIENT, "No known drug allergies.", 27.6, 30.0),
]

CONTEXT = {
    "reference": "SIM-GEMINI-CHECK",
    "simulation_type": "OSCE",
    "scenario": "Outpatient chest discomfort (synthetic)",
    "patient_id": "SIM-PT-CHECK",
    "speakers": [
        {"label": "speaker_0", "role": "DOCTOR", "confidence": 0.95},
        {"label": "speaker_1", "role": "PATIENT", "confidence": 0.94},
    ],
    "elapsed_seconds": 30.0,
}

if sys.stdout.isatty():
    GREEN, RED, YELLOW, DIM, BOLD, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[1m", "\033[0m"
else:  # piped output stays readable without escape codes
    GREEN = RED = YELLOW = DIM = BOLD = RESET = ""


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.rows.append((name, passed, detail))
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"  {name:<26} {status}  {DIM}{detail}{RESET}")

    @property
    def ok(self) -> bool:
        return all(passed for _name, passed, _detail in self.rows)


def prompt_segments() -> list[dict]:
    return [
        {
            "ref": ref,
            "speaker_label": speaker,
            "role": role.value,
            "text": text,
            "start_time": start,
            "end_time": end,
            "confidence": 0.94,
        }
        for ref, speaker, role, text, start, end in SEGMENTS
    ]


def assembled_segments() -> list[AssembledSegment]:
    return [
        AssembledSegment(
            ref=ref,
            speaker_label=speaker,
            role=role,
            text=text,
            start_time=start,
            end_time=end,
            confidence=0.94,
            asr_confidence=0.94,
            diarization_confidence=0.94,
        )
        for ref, speaker, role, text, start, end in SEGMENTS
    ]


def evidence_service() -> EvidenceLinkingService:
    service = EvidenceLinkingService()
    service.build_index(
        [
            SegmentIndexEntry(
                ref=ref,
                text=text,
                speaker_label=speaker,
                role=role,
                start_time=start,
                end_time=end,
                confidence=0.94,
                segment_id=ref,
            )
            for ref, speaker, role, text, start, end in SEGMENTS
        ]
    )
    return service


async def main() -> int:
    print("=" * 60)
    print(f"{BOLD}MEDSCRIBE GEMINI TEST{RESET}")
    print("=" * 60)
    print(f"Model:        {settings.gemini_model}")
    print(f"AI mode:      {settings.ai_mode.value}")
    print(f"Key present:  {'yes' if settings.gemini_configured else 'no'}")
    print("-" * 60)

    if not settings.gemini_configured:
        print(f"{YELLOW}GEMINI_API_KEY is not set.{RESET}")
        print("  1. Create a key at https://aistudio.google.com/apikey")
        print("  2. Copy .env.example to .env and set GEMINI_API_KEY")
        print("  3. Re-run: python scripts/test_gemini.py")
        print(f"\n{DIM}MedScribe still runs without a key: the deterministic rule-based")
        print(f"provider takes over and Demo Mode remains fully usable.{RESET}")
        return 2

    report = Report()
    provider = GeminiProvider()
    validator = OutputValidator()
    evidence = evidence_service()
    segments = prompt_segments()

    connection = await provider.check_connection()
    report.add(
        "API Connection",
        bool(connection.get("connected")),
        f"{connection.get('latency_ms', 0)} ms" if connection.get("connected") else str(connection.get("error"))[:70],
    )
    if not connection.get("connected"):
        _summary(report)
        return 1

    nlp = ClinicalNLPService()
    candidates = nlp.extract(assembled_segments())
    rule_hints = [
        {
            "entity_type": candidate.entity_type.value,
            "value": candidate.value,
            "status": candidate.status.value,
            "source_segment_ids": candidate.source_segment_refs,
        }
        for candidate in candidates
    ]

    try:
        extraction = await provider.extract_entities(
            session_context=CONTEXT, segments=segments, rule_based_candidates=rule_hints
        )
    except LLMError as exc:
        report.add("Entity Extraction", False, f"{exc.code}: {exc}"[:70])
        _summary(report)
        return 1

    entities = extraction.result.entities
    report.add("Structured Output", True, f"{len(entities)} entities, {extraction.stats.duration_ms:.0f} ms")

    values = {(entity.entity_type, entity.value.lower().strip()) for entity in entities}
    found_symptom = any(
        entity_type is EntityType.SYMPTOM and "chest" in value for entity_type, value in values
    )
    found_medication = any(
        entity_type is EntityType.MEDICATION and "metformin" in value for entity_type, value in values
    )
    report.add(
        "Entity Extraction",
        found_symptom and found_medication,
        "chest discomfort + metformin" if found_symptom and found_medication else "expected concepts missing",
    )

    negated = [
        entity
        for entity in entities
        if "breath" in entity.value.lower() and entity.status is EntityStatus.NEGATED
    ]
    allergy_negated = [
        entity
        for entity in entities
        if entity.entity_type is EntityType.ALLERGY
        and (entity.status is EntityStatus.NEGATED or "no known" in entity.value.lower())
    ]
    report.add(
        "Negation Detection",
        bool(negated) and bool(allergy_negated),
        "shortness of breath NEGATED, allergies denied" if negated and allergy_negated else "negation not preserved",
    )

    validated = validator.validate_entities(
        entities,
        valid_segment_refs=evidence.valid_refs,
        segment_texts=evidence.segment_texts(),
        rule_statuses={
            (candidate.normalized_value or candidate.value).lower(): candidate.status for candidate in candidates
        },
    )
    report.add(
        "Schema Validation",
        validated.dropped == 0,
        f"{len(validated.entities)} valid, {validated.dropped} dropped",
    )

    linked = [
        evidence.link(
            target_kind="ENTITY",
            target_key=entity.value,
            clinical_statement=entity.value,
            refs=entity.source_segment_ids,
        )
        for entity in validated.entities
    ]
    unlinked = [statement.target_key for statement in linked if statement.review_required]
    report.add(
        "Evidence Mapping",
        not unlinked and bool(linked),
        "all entities cite real segments" if not unlinked else f"unlinked: {unlinked[:3]}",
    )

    try:
        note_response = await provider.generate_note(
            session_context=CONTEXT,
            segments=segments,
            entities=[
                {
                    "entity_type": entity.entity_type.value,
                    "value": entity.value,
                    "status": entity.status.value,
                    "confidence": entity.confidence,
                    "source_segment_refs": entity.source_segment_ids,
                }
                for entity in validated.entities
            ],
        )
    except LLMError as exc:
        report.add("Note Generation", False, f"{exc.code}: {exc}"[:70])
        _summary(report)
        return 1

    note_validation = validator.validate_note(note_response.result, valid_segment_refs=evidence.valid_refs)
    report.add(
        "Note Generation",
        bool(note_validation.note.chief_complaint.text)
        and note_validation.note.chief_complaint.text != "Not mentioned",
        f"{note_response.stats.duration_ms:.0f} ms, sections changed: {len(note_validation.changed_sections)}",
    )
    report.add(
        "No Invented Diagnosis",
        not any(entity.entity_type is EntityType.DIAGNOSIS_MENTIONED for entity in validated.entities),
        "assessment: " + note_validation.note.assessment.text[:48],
    )
    report.add(
        "Note Evidence Links",
        not note_validation.unsupported_sections,
        "every documented section cites the transcript"
        if not note_validation.unsupported_sections
        else f"unsupported: {note_validation.unsupported_sections}",
    )

    print("-" * 60)
    print(f"{BOLD}Extracted clinical entities{RESET}")
    for entity in validated.entities:
        print(
            f"  {entity.entity_type.value:<20} {entity.value[:34]:<34} "
            f"{entity.status.value:<10} {entity.confidence:.2f}  {','.join(entity.source_segment_ids)}"
        )

    print("-" * 60)
    print(f"{BOLD}Generated clinical note{RESET}")
    for key, section in note_validation.note.model_dump().items():
        refs = ",".join(section["source_segment_ids"]) or "-"
        print(f"  {key.replace('_', ' ').title()}")
        print(f"    {section['text']}")
        print(f"    {DIM}evidence: {refs} | confidence: {section['confidence']:.2f}{RESET}")

    return _summary(report)


def _summary(report: Report) -> int:
    print("=" * 60)
    for name, passed, _detail in report.rows:
        print(f"{name:<26} {'PASS' if passed else 'FAIL'}")
    print("=" * 60)
    if report.ok:
        print(f"{GREEN}Gemini integration is working.{RESET}")
        return 0
    print(f"{RED}Gemini integration has failures (see above).{RESET}")
    print(f"{DIM}MedScribe remains usable: the rule-based provider takes over automatically.{RESET}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
