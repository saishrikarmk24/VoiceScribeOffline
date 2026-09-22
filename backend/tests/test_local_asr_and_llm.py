"""Local transcription / diarization and LLM JSON parsing — no network."""

from __future__ import annotations

import json
import math
import struct

from app.core.config import DiarizationProviderName, settings
from app.models.enums import AudioSource
from app.services.diarization import build_diarization_provider
from app.services.diarization.local_provider import LocalDiarizationProvider
from app.services.llm.json_parse import extract_json_object
from app.services.llm.prompts import build_extraction_prompt
from app.services.llm.schemas import ExtractionResult, NoteUpdate, coerce_llm_payload
from app.services.types import AudioFrame


def _tone(seconds: float, hz: float, sample_rate: int = 16000) -> bytes:
    frames = bytearray()
    n = int(seconds * sample_rate)
    for index in range(n):
        value = 0.65 * math.sin(2 * math.pi * hz * index / sample_rate)
        frames += struct.pack("<h", int(max(-1.0, min(1.0, value)) * 24000))
    return bytes(frames)


def _parse(text: str, schema):
    return schema.model_validate(coerce_llm_payload(extract_json_object(text), schema))


def test_default_real_audio_diarizer_is_local(monkeypatch) -> None:
    monkeypatch.setattr(settings, "diarization_provider", DiarizationProviderName.LOCAL)
    provider = build_diarization_provider(audio_source=AudioSource.MICROPHONE)
    assert isinstance(provider, LocalDiarizationProvider)


async def test_local_diarizer_splits_two_pitches() -> None:
    pcm = _tone(1.0, 110.0) + _tone(1.0, 240.0)
    frame = AudioFrame(
        session_id="local-diar",
        sequence=1,
        pcm=pcm,
        sample_rate=16000,
        channels=1,
        start_time=0.0,
        end_time=2.0,
        source=AudioSource.MICROPHONE,
        speech_ratio=0.9,
        speech_regions=[(0.0, 1.0), (1.0, 2.0)],
    )
    turns = await LocalDiarizationProvider().diarize(frame)
    labels = {turn.speaker_id for turn in turns}
    assert "speaker_0" in labels
    assert "speaker_1" in labels


def test_llm_extracts_json_from_reasoning_text() -> None:
    text = (
        "The patient mentioned fever. Final answer:\n"
        '{"entities": [{"entity_type": "SYMPTOM", "value": "fever", "status": "PRESENT",'
        ' "source_segment_ids": ["seg_001"]}], "unsupported_content": []}'
    )
    parsed = _parse(text, ExtractionResult)
    assert parsed.entities[0].value == "fever"


def test_llm_repairs_truncated_json() -> None:
    text = '{"entities": [{"entity_type": "SYMPTOM", "value": "fever", "status": "PRESENT"'
    parsed = _parse(text, ExtractionResult)
    assert parsed.entities[0].value == "fever"


def test_extraction_prompt_includes_confidence_example() -> None:
    prompt = build_extraction_prompt(
        session_context={"reference": "MS-1"},
        segments=[{"ref": "seg_001", "start_time": 0.0, "role": "PATIENT", "speaker_label": "speaker_1", "confidence": 0.9, "text": "I have a fever."}],
    )
    assert "confidence" in prompt
    assert '"entity_type": "SYMPTOM"' in prompt or '"entity_type":"SYMPTOM"' in prompt


def test_llm_parses_entities_missing_confidence() -> None:
    payload = {
        "entities": [
            {
                "entity_type": "SYMPTOM",
                "value": "fever",
                "status": "PRESENT",
                "source_segment_ids": ["seg_001"],
            }
        ]
    }
    parsed = _parse(json.dumps(payload), ExtractionResult)
    assert parsed.entities[0].value == "fever"
    assert parsed.entities[0].confidence == 0.75


def test_llm_parses_note_without_confidence() -> None:
    payload = {
        "note": {
            "chief_complaint": {"text": "Fever", "source_segment_ids": ["seg_001"]},
            "history_of_present_illness": {"text": "", "source_segment_ids": []},
            "relevant_medical_history": {"text": "", "source_segment_ids": []},
            "assessment": {"text": "", "source_segment_ids": []},
            "plan": {"text": "", "source_segment_ids": []},
            "follow_up": {"text": "", "source_segment_ids": []},
        },
        "changed_sections": ["chief_complaint"],
    }
    parsed = _parse(json.dumps(payload), NoteUpdate)
    assert parsed.note.chief_complaint.text == "Fever"
    assert parsed.note.chief_complaint.confidence == 0.75


def test_llm_parses_fenced_json() -> None:
    text = """```json
{"entities": [{"entity_type": "SYMPTOM", "value": "chest pain", "status": "PRESENT",
"confidence": 0.9, "source_segment_ids": ["seg_001"]}], "unsupported_content": []}
```"""
    parsed = _parse(text, ExtractionResult)
    assert parsed.entities[0].value == "chest pain"
