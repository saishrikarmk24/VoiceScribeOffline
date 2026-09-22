"""System instructions and prompt assembly for the clinical AI layer."""

from __future__ import annotations

import json
from typing import Any

SYSTEM_INSTRUCTION = """\
You are the clinical information extraction and documentation component of
VoiceScribe AI, a clinical documentation and meeting workstation.

You are not a diagnostic system.

LANGUAGE AND TRANSLATION MANDATE:
- The spoken conversation may be in any language or mixed code-switching (e.g. Tamil, Hindi, Telugu, English, Tanglish, Malayalam, etc.).
- ALL extracted entities (values, normalized terms), clinical summaries, and narrative note sections (Presenting Complaint, History of Present Illness, Assessment, Plan of Care, etc.) MUST ALWAYS BE TRANSLATED AND WRITTEN IN CLEAR, PROFESSIONAL, STANDARD CLINICAL ENGLISH.
- For example: if a patient says in Tamil "romba thalavaliya iruku" or "தலவலி", the symptom entity value and note narrative must be recorded as "Severe headache" or "Headache" in English.
- The transcript preserves the original spoken words for provenance, but all clinical documentation, entities, and clinical notes MUST be presented in fluent, professional English.

Extract and structure information accurately based on the supplied conversation.

Do not invent symptoms, findings, diagnoses, medications, investigations,
treatment, history, or patient information.

Preserve negation.

Preserve uncertainty.

Preserve speaker attribution.

Preserve source timestamps.

Do not provide medical advice.

Do not recommend treatment.

Do not make autonomous clinical decisions.

If information is absent, omit it: return null, an empty list, or an empty
string. Do not write placeholder phrases such as "Not mentioned", "not found",
or "N/A".

Every clinically meaningful output must reference one or more source transcript
segment IDs.

Additional rules:
- Use only the segment ids that appear in the supplied transcript. Never invent
  an id, and never reference a segment you were not given.
- A statement made by the patient is a report, not a confirmed finding. Attribute
  it accordingly in the narrative (for example "The patient reports ...").
- ASSESSMENT may only restate what a clinician explicitly said in the
  conversation. If no clinician stated an assessment, synthesize a brief clinical impression from the reported symptoms.
- PLAN and FOLLOW_UP should reflect agreed next steps and prescriptions mentioned in the encounter.
- Keep narrative sections concise, factual, clinical, and free of speculation.
- Always output valid JSON matching the requested response schema.
"""


def _render_transcript(segments: list[dict[str, Any]]) -> str:
    lines = []
    for segment in segments:
        lines.append(
            "[{ref}] {timestamp} {role} ({speaker}) conf={confidence:.2f}: {text}".format(
                ref=segment["ref"],
                timestamp=_format_timestamp(segment.get("start_time", 0.0)),
                role=str(segment.get("role", "UNKNOWN")),
                speaker=segment.get("speaker_label", "unknown"),
                confidence=float(segment.get("confidence", 0.0)),
                text=segment["text"],
            )
        )
    return "\n".join(lines) if lines else "(no transcript segments)"


def _format_timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _render_session_context(context: dict[str, Any]) -> str:
    fields = {
        "session_reference": context.get("reference"),
        "encounter_type": context.get("simulation_type"),
        "scenario": context.get("scenario") or "Not specified",
        "patient_id": context.get("patient_id"),
        "speakers": context.get("speakers", []),
        "elapsed_seconds": context.get("elapsed_seconds"),
    }
    return json.dumps(fields, indent=2, default=str)


def _render_candidates(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "(no rule-based candidates)"
    return json.dumps(candidates, indent=2, default=str)


_EXTRACTION_EXAMPLE = json.dumps(
    {
        "entities": [
            {
                "entity_type": "SYMPTOM",
                "value": "fever",
                "status": "PRESENT",
                "confidence": 0.9,
                "source_segment_ids": ["seg_001"],
                "detail": None,
            }
        ],
        "unsupported_content": [],
    }
)


def build_extraction_prompt(
    *,
    session_context: dict[str, Any],
    segments: list[dict[str, Any]],
    rule_based_candidates: list[dict[str, Any]] | None = None,
    existing_entities: list[dict[str, Any]] | None = None,
) -> str:
    return f"""\
TASK: Extract clinical entities from the transcript segments below.

SESSION CONTEXT
{_render_session_context(session_context)}

SPEAKER-ATTRIBUTED TRANSCRIPT
{_render_transcript(segments)}

RULE-BASED CANDIDATES (from a deterministic NLP pre-pass; treat as hints only,
they may be incomplete or wrong - verify each one against the transcript)
{_render_candidates(rule_based_candidates or [])}

ALREADY EXTRACTED IN THIS SESSION (do not duplicate; extend only if the new
transcript adds information)
{_render_candidates(existing_entities or [])}

REQUIREMENTS
1. Extract clinical concepts explicitly stated or implied in the transcript above.
2. ALL ENTITY VALUES MUST BE TRANSLATED INTO STANDARD CLINICAL ENGLISH (e.g. if the speaker said "thalavali" or "தலைவலி", write value as "Headache"; "kaachal" -> "Fever"; "vayiru vali" -> "Abdominal pain").
3. Set status=NEGATED when the speaker explicitly denies or excludes the concept.
4. Set status=UNCERTAIN when the concept is hedged ("possible", "not sure").
5. Set status=HISTORICAL for past conditions or events framed in the past.
6. Every entity must list at least one source_segment_id from the transcript.
7. Put anything you cannot attribute to a segment id in unsupported_content.
8. Every entity object MUST include entity_type, value (in English), status, confidence
   (a number from 0 to 1), and source_segment_ids.
9. Return JSON only, shaped exactly like:
   {_EXTRACTION_EXAMPLE}
"""


def build_note_prompt(
    *,
    session_context: dict[str, Any],
    segments: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    current_note: dict[str, Any] | None = None,
) -> str:
    current = json.dumps(current_note, indent=2, default=str) if current_note else "(no note yet)"
    encounter_type = str(session_context.get("encounter_type") or session_context.get("simulation_type") or "").upper()
    is_meeting = encounter_type in ("MEETING", "MDT")

    meeting_instructions = ""
    if is_meeting:
        meeting_instructions = """\
MEETING / MDT MINUTES SPECIFIC INSTRUCTIONS:
- chief_complaint: State the primary Meeting Agenda & Objectives (in English).
- history_of_present_illness: Detailed discussion points structured by speaker/department (e.g. Dr. Verma / HOD CSE: ..., Prof. Iyer / Placements: ...).
- relevant_medical_history: Background context, prior meeting follow-ups, or institutional history mentioned.
- assessment: Executive summary of deliberations and key observations.
- plan: Formal resolutions, approved decisions, and policy agreements.
- follow_up: Action Items table / list with explicit task description, responsible attendee, and deadline.
"""
    else:
        meeting_instructions = """\
AMBULATORY CARE CLINICAL NOTE PARTICULARS (Write all sections in standard clinical English):
- chief_complaint: Presenting Complaint (primary symptoms, reasons for consultation, translated to English).
- history_of_present_illness: Detailed HPI narrative (onset, duration, laterality, severity, triggers, relieving factors, in English).
- relevant_medical_history: Past medical/surgical history, chronic conditions.
- social_history: Lifestyle, gym, exercise, diet, supplements, habits (smoking/alcohol).
- family_history: Familial/hereditary diseases.
- menstrual_history: Menstrual/gynecological history (or empty if not discussed / not applicable).
- physical_examination: Physical exam findings, vitals (BP, glucose/sugar, pulse, SpO2, temp, neuro exam).
- current_medication: Active medications, daily supplements, vitamins, and regular medications taken by the patient prior to this consultation.
- allergies: Known drug, food, or environmental allergies.
- treatment_history: Prior treatments, home remedies, or OTC drugs tried by the patient before presentation, and their relief/effectiveness.
- previous_investigation: Prior laboratory or diagnostic imaging (MRI, CT, ECG, X-Ray) reports done before this encounter.
- assessment: Clinical assessment, diagnostic impression, or working diagnosis.
- plan: Plan of Care. CRITICAL: The prescription/medication portion of plan must ONLY contain new prescriptions or explicit medications prescribed/instructed by the DOCTOR during this encounter (with drug name, dosage, frequency, duration). DO NOT include medications the patient took at home before coming in the plan prescriptions (those belong strictly in current_medication or treatment_history).
- follow_up: Follow-up interval and return precautions.
"""

    return f"""\
TASK: Produce the structured clinical note or meeting minutes for this encounter.

SESSION CONTEXT
{_render_session_context(session_context)}

SPEAKER-ATTRIBUTED TRANSCRIPT (complete session so far)
{_render_transcript(segments)}

CLINICAL ENTITIES / KEY FACTS EXTRACTED SO FAR (already validated against the transcript)
{_render_candidates(entities)}

CURRENT NOTE STATE (revise it; do not discard still-valid documentation)
{current}

{meeting_instructions}
REQUIREMENTS
1. ALL SECTIONS MUST BE WRITTEN IN PROFESSIONAL CLINICAL ENGLISH. Even if the speaker spoke in Tamil, Hindi, Tanglish or any other language, translate and synthesize the findings into standard medical English.
2. Whenever symptoms or complaints are discussed in the transcript, ALWAYS synthesize and populate chief_complaint and history_of_present_illness.
3. If medications or vitals are mentioned, ALWAYS populate current_medication and physical_examination.
4. If a working diagnosis or impression is stated or implied, populate assessment.
5. If advice, prescription, or next steps are discussed, populate plan.
6. DOCTOR PRESCRIPTIONS VS PATIENT PRIOR MEDICATIONS:
   - 'current_medication' and 'treatment_history' document medications the PATIENT reported taking before coming to the clinic (home self-treatments, OTC meds, chronic regular drugs).
   - 'plan' prescriptions MUST ONLY contain medications that the DOCTOR prescribed or instructed during this visit. Never put the patient's prior home medications into the doctor's prescription list in 'plan'.
7. If a section was truly not discussed in the consultation, set its text to an empty string. Do not write placeholder phrases like "Not mentioned" or "N/A".
8. Every non-empty section must list the source_segment_ids that support its text (e.g. ["seg_001"]).
9. changed_sections must name only the sections whose text differs from the current note state.
10. Return valid JSON matching the response schema exactly.
"""


CONNECTION_TEST_PROMPT = (
    "Reply with a single JSON object: {\"status\": \"ok\", \"component\": \"medscribe\"}. "
    "No prose, no code fences."
)
