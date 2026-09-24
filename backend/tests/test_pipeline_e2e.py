"""End-to-end Demo Mode: audio in, evidence-linked clinical note out.

Runs entirely offline (mock ASR, mock diarization, deterministic structuring),
which is exactly the configuration Demo Mode must support when no external
speech or AI service is reachable.
"""

from __future__ import annotations

import asyncio

from app.models.enums import EntityStatus, EntityType, NoteStatus, SpeakerRole
from app.schemas.events import EventType
from app.services.pipeline import pipeline
from app.websocket.manager import manager


async def _wait_for_segments(client, session_id: str, expected: int, timeout: float = 20.0) -> list[dict]:
    deadline = asyncio.get_running_loop().time() + timeout
    segments: list[dict] = []
    while asyncio.get_running_loop().time() < deadline:
        segments = (await client.get(f"/api/sessions/{session_id}/transcript")).json()
        if len(segments) >= expected:
            return segments
        await asyncio.sleep(0.05)
    return segments


async def test_demo_session_produces_evidence_linked_note(client, created_session) -> None:
    session_id = created_session["id"]
    assert (await client.post(f"/api/sessions/{session_id}/start")).status_code == 200

    segments = await _wait_for_segments(client, session_id, expected=10)
    assert len(segments) == 10, f"expected the whole script, got {len(segments)}"

    # ---- transcript: speakers, roles, timestamps, confidence -----------------
    first, second = segments[0], segments[1]
    assert first["text"].startswith("Good morning")
    assert second["text"].startswith("I've been having chest discomfort")
    assert first["speaker_label"] != second["speaker_label"]
    assert first["role"] == SpeakerRole.DOCTOR.value
    assert second["role"] == SpeakerRole.PATIENT.value
    assert first["end_time"] > first["start_time"]
    assert second["start_time"] >= first["start_time"]
    assert 0.0 < first["confidence"] <= 1.0
    assert [segment["ref"] for segment in segments[:3]] == ["seg_001", "seg_002", "seg_003"]

    # ---- audio actually flowed through preprocessing -------------------------
    chunks = (await client.get(f"/api/sessions/{session_id}/audio-chunks")).json()["chunks"]
    assert len(chunks) == 10
    assert all(chunk["sample_rate"] == 16000 and chunk["channels"] == 1 for chunk in chunks)
    assert all(chunk["speech_ratio"] > 0.0 for chunk in chunks)

    stopped = (await client.post(f"/api/sessions/{session_id}/stop")).json()
    assert stopped["status"] == "REVIEW"

    # ---- clinical entities ---------------------------------------------------
    entities = (await client.get(f"/api/sessions/{session_id}/entities")).json()
    by_value = {(entity["entity_type"], entity["value"].lower()): entity for entity in entities}

    chest = by_value.get((EntityType.SYMPTOM.value, "chest discomfort"))
    assert chest is not None
    assert chest["status"] == EntityStatus.PRESENT.value
    assert chest["source_segment_refs"] == ["seg_002"]
    assert chest["evidence"], "entity evidence was not linked"
    assert chest["evidence"][0]["speaker_role"] == SpeakerRole.PATIENT.value
    assert chest["evidence"][0]["source_text"].startswith("I've been having chest discomfort")

    sob = by_value.get((EntityType.SYMPTOM.value, "shortness of breath"))
    assert sob is not None and sob["status"] == EntityStatus.NEGATED.value

    assert (EntityType.MEDICATION.value, "metformin") in by_value
    assert any(key[0] == EntityType.ALLERGY.value for key in by_value)
    assert not [key for key in by_value if key[0] == EntityType.DIAGNOSIS_MENTIONED.value]
    assert all(entity["normalized_code"] is None for entity in entities)

    # ---- note ---------------------------------------------------------------
    note = (await client.get(f"/api/sessions/{session_id}/note")).json()
    assert note["status"] in (NoteStatus.DRAFT.value, NoteStatus.REVIEW_REQUIRED.value)
    assert note["version"] >= 1

    content = note["content"]
    assert "chest discomfort" in content["chief_complaint"]["text"].lower()
    assert content["chief_complaint"]["evidence"], "chief complaint has no evidence"
    assert content["chief_complaint"]["evidence"][0]["transcript_segment_ref"] == "seg_002"
    assert "shortness of breath" in content["history_of_present_illness"]["text"].lower()
    assert content["assessment"]["text"] == "Not mentioned"  # no diagnosis was stated
    assert [entity["value"].lower() for entity in content["medications"]] == ["metformin"]

    # ---- evidence provenance chain ------------------------------------------
    evidence = (await client.get(f"/api/sessions/{session_id}/evidence")).json()
    assert evidence
    section_links = [link for link in evidence if link["target_kind"] == "SECTION"]
    assert section_links
    for link in section_links:
        assert link["validated"] is True
        assert link["segment_ref"] in {segment["ref"] for segment in segments}
        assert link["timestamp"] is not None

    detail = (await client.get(f"/api/sessions/{session_id}/evidence/chief_complaint/detail")).json()
    assert detail["validated_count"] >= 1
    assert any(item["segment"]["text"].startswith("I've been having chest discomfort") for item in detail["chain"])


async def test_note_versions_are_recorded(client, created_session) -> None:
    session_id = created_session["id"]
    await client.post(f"/api/sessions/{session_id}/start")
    await _wait_for_segments(client, session_id, expected=6)
    await client.post(f"/api/sessions/{session_id}/stop")

    versions = (await client.get(f"/api/sessions/{session_id}/note/versions")).json()
    assert versions
    assert versions[0]["author_type"] == "AI"
    assert versions[-1]["version"] >= 1


async def test_websocket_streams_the_live_pipeline(created_session, database) -> None:
    """Events must arrive without polling, in pipeline order."""
    from fastapi.testclient import TestClient

    from app.main import app

    session_id = created_session["id"]
    received: list[str] = []

    def consume() -> None:
        with TestClient(app) as test_client:
            with test_client.websocket_connect(f"/ws/sessions/{session_id}") as socket:
                snapshot = socket.receive_json()
                received.append(snapshot["type"])
                test_client.post(f"/api/sessions/{session_id}/start")
                deadline = 30
                while deadline > 0:
                    event = socket.receive_json()
                    received.append(event["type"])
                    if event["type"] == EventType.NOTE_UPDATE.value:
                        break
                    deadline -= 1
                socket.send_json({"type": "PING"})
                while True:
                    event = socket.receive_json()
                    received.append(event["type"])
                    if event["type"] == EventType.PONG.value:
                        break

    await asyncio.to_thread(consume)

    assert received[0] == EventType.STATE_SNAPSHOT.value
    assert EventType.SESSION_STARTED.value in received
    assert EventType.AUDIO_STATUS.value in received
    assert EventType.TRANSCRIPT_UPDATE.value in received
    assert EventType.DIARIZATION_UPDATE.value in received
    assert EventType.ENTITY_UPDATE.value in received
    assert EventType.NOTE_UPDATE.value in received
    assert EventType.PONG.value in received

    history = manager.history(session_id)
    sequences = [event.sequence for event in history]
    assert sequences == sorted(sequences)


async def test_websocket_replays_missed_events_on_reconnect(created_session, database) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    session_id = created_session["id"]

    def run() -> list[dict]:
        replayed: list[dict] = []
        with TestClient(app) as test_client:
            test_client.post(f"/api/sessions/{session_id}/start")
            with test_client.websocket_connect(f"/ws/sessions/{session_id}") as socket:
                socket.receive_json()  # snapshot
                socket.send_json({"type": "SYNC", "last_sequence": 1})
                replayed.append(socket.receive_json())
        return replayed

    replayed = await asyncio.to_thread(run)
    assert replayed
    assert replayed[0]["sequence"] > 1 or replayed[0]["type"] == EventType.STATE_SNAPSHOT.value


async def test_pipeline_recovers_when_the_ai_layer_fails(client, created_session, monkeypatch) -> None:
    """Gemini failing must not stop the transcript or lose the note."""
    from app.services.llm import base as llm_base

    session_id = created_session["id"]
    session_response = await client.get(f"/api/sessions/{session_id}")
    assert session_response.status_code == 200

    from app.services import repository as repo
    from app.core.database import db_state

    assert db_state.session_factory is not None
    async with db_state.session_factory() as db:
        session = await repo.get_session(db, session_id)
        runtime = await pipeline.ensure_runtime(session)

    async def broken_extract(**_kwargs):
        raise llm_base.LLMUnavailable("simulated Gemini outage")

    monkeypatch.setattr(runtime.llm, "extract_entities", broken_extract)

    await client.post(f"/api/sessions/{session_id}/start")
    segments = await _wait_for_segments(client, session_id, expected=10)
    assert len(segments) == 10, "transcript must keep flowing when the AI layer fails"

    await client.post(f"/api/sessions/{session_id}/stop")

    note = (await client.get(f"/api/sessions/{session_id}/note")).json()
    assert note["version"] >= 1, "the fallback provider should still produce a note"
    entities = (await client.get(f"/api/sessions/{session_id}/entities")).json()
    assert entities, "the deterministic fallback should still extract entities"
    assert runtime.ai_degraded is True
    assert runtime.last_ai_error is not None


async def test_speaker_role_can_be_reassigned_by_a_human(client, created_session) -> None:
    session_id = created_session["id"]
    await client.post(f"/api/sessions/{session_id}/start")
    await _wait_for_segments(client, session_id, expected=4)

    speakers = (await client.get(f"/api/sessions/{session_id}/speakers")).json()
    assert speakers
    target = speakers[0]

    response = await client.patch(f"/api/speakers/{target['id']}", json={"role": "NURSE"})
    assert response.status_code == 200
    updated = response.json()
    assert updated["role"] == "NURSE"
    assert updated["role_source"] == "HUMAN"
    assert updated["confidence"] == 1.0

    transcript = (await client.get(f"/api/sessions/{session_id}/transcript")).json()
    assert any(segment["role"] == "NURSE" for segment in transcript)

    audit = (await client.get(f"/api/sessions/{session_id}/audit")).json()
    assert any(entry["action"] == "SPEAKER_ROLE_UPDATED" for entry in audit["entries"])

    await client.post(f"/api/sessions/{session_id}/stop")
