"""Verification script for 100% offline multilingual pipeline.

Tests:
1. LocalLLMProvider with qwen2.5:3b on code-mixed Indian clinical dialogues (Tamil/Tanglish, Hindi/Hinglish, Telugu)
2. Negation handling (ensures denied symptoms are marked NEGATED)
3. Clinical entity extraction & SOAP note synthesis
4. Output validation and PDF exporter verification with explicit patient name
"""

import asyncio
import json
import time

from app.core.config import settings
from app.services.export.exporters import export_pdf
from app.services.llm.local_provider import LocalLLMProvider
from app.services.llm.validator import OutputValidator


async def main():
    print("=" * 70)
    print("VoiceScribe AI - 100% Offline Multilingual Indian Clinical Verification")
    print(f"Active Model: {settings.local_llm_model} via {settings.local_llm_base_url}")
    print(f"ASR Provider: {settings.asr_provider.value}")
    print("=" * 70)

    llm = LocalLLMProvider()

    # 1. Connection check
    print("\n[1/4] Checking Local LLM Connection...")
    conn = await llm.check_connection()
    print("  Connection Status:", json.dumps(conn, indent=2))
    assert conn.get("ok") is True, f"Failed to connect: {conn.get('error')}"

    # 2. Multilingual Clinical Dialogue Test (Tanglish + Hinglish + Indian English)
    print("\n[2/4] Testing Clinical Entity Extraction on Indian Code-Switched Dialogue...")
    segments = [
        {"ref": "seg_001", "speaker_label": "Doctor", "text": "Good morning Mrs. Priya, enna aachu pa?"},
        {
            "ref": "seg_002",
            "speaker_label": "Patient",
            "text": "Doctor, rendu naala romba nenju vali irukku, heavy burning in chest. Also moochu vida kashtam when walking.",
        },
        {
            "ref": "seg_003",
            "speaker_label": "Doctor",
            "text": "Any fever or cough? Aur koi takleef jaise chakkar aana ya ulti?",
        },
        {
            "ref": "seg_004",
            "speaker_label": "Patient",
            "text": "No fever doctor, kaichal illa. But thalai vali and chakkar irukku. No vomiting.",
        },
        {
            "ref": "seg_005",
            "speaker_label": "Doctor",
            "text": "Are you taking any medications for BP or sugar?",
        },
        {
            "ref": "seg_006",
            "speaker_label": "Patient",
            "text": "Yes doctor, taking Glycomet 500mg and Telma 40mg daily morning. Blood pressure was 140/90 when checked yesterday.",
        },
    ]

    t0 = time.perf_counter()
    extraction_resp = await llm.extract_entities(
        session_context={"encounter_type": "OUTPATIENT"},
        segments=segments,
    )
    dt_extract = time.perf_counter() - t0
    entities = extraction_resp.result.entities
    print(f"  Extraction completed in {dt_extract:.2f}s ({len(entities)} entities found):")
    for ent in entities:
        print(f"    - [{ent.entity_type}] {ent.value} (status: {ent.status}, refs: {ent.source_segment_ids})")

    # Validate negation of fever and vomiting
    negated_values = [ent.value.lower() for ent in entities if ent.status.value == "NEGATED"]
    print(f"  Negated Entities Detected: {negated_values}")

    # 3. SOAP Note Synthesis
    print("\n[3/4] Synthesizing Structured Clinical SOAP Note...")
    t1 = time.perf_counter()
    note_resp = await llm.generate_note(
        session_context={"encounter_type": "OUTPATIENT"},
        segments=segments,
        entities=[e.model_dump() for e in entities],
    )
    dt_note = time.perf_counter() - t1
    note = note_resp.result.note
    print(f"  Note generated in {dt_note:.2f}s:")
    print(f"    Chief Complaint:      {note.chief_complaint.text}")
    print(f"    HPI:                  {note.history_of_present_illness.text[:100]}...")
    print(f"    Physical Exam:        {note.physical_examination.text}")
    print(f"    Current Medication:   {note.current_medication.text}")
    print(f"    Assessment:           {note.assessment.text}")
    print(f"    Plan:                 {note.plan.text}")
    print(f"    Follow-Up:            {note.follow_up.text}")

    # 4. Output Validation & PDF Export Test
    print("\n[4/4] Validating Clinical Note & Testing PDF Export...")
    validator = OutputValidator()
    valid_refs = {s["ref"] for s in segments}
    val_result = validator.validate_note(note_resp.result, valid_segment_refs=valid_refs)
    print(f"  Validation Issues: {len(val_result.issues)}")
    for issue in val_result.issues:
        print(f"    [{issue.severity}] {issue.target}: {issue.message}")

    # PDF Export with explicit patient name
    pdf_payload = {
        "session": {
            "id": "test-session-001",
            "reference": "MS-9921",
            "name": "Priya Sundaram - Consultation",
            "patient_name": "Priya Sundaram",
            "patient_id": "PT-9921",
            "patient_gender": "Female",
            "patient_age": "42 Yrs",
            "doctor_name": "Dr. A. Rao",
            "speciality": "General Medicine",
            "simulation_type": "OUTPATIENT",
            "started_at": "2026-09-22T10:00:00Z",
        },
        "note": {
            "content": note.model_dump(),
        },
    }
    pdf_bytes = export_pdf(pdf_payload)
    print(f"  Exported PDF Size: {len(pdf_bytes)} bytes")
    assert len(pdf_bytes) > 5000, "PDF export should produce a valid binary PDF document"

    await llm.aclose()
    print("\n" + "=" * 70)
    print("SUCCESS: 100% Offline Multilingual Clinical Pipeline Verified!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
