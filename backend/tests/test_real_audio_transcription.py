"""Real audio must produce a real transcript - or a clear error. Never demo text.

These tests pin the contract that was violated by the original implementation:
microphone/upload audio reached a script-driven ASR provider, so speaking into
the microphone produced the demo conversation verbatim.
"""

from __future__ import annotations

import base64
import io
import math
import struct
import wave

import pytest

from app.core.config import ASRProviderName, settings
from app.models.enums import AudioSource, SessionMode
from app.services.asr import UnavailableASRProvider, build_asr_provider
from app.services.asr.gemini_provider import DIARIZATION_HINT_KEY, GeminiASRProvider
from app.services.asr.mock_provider import MockASRProvider
from app.services.demo.conversations import get_script
from app.services.diarization import build_diarization_provider
from app.services.diarization.gemini_provider import GeminiDiarizationProvider
from app.services.pipeline import pipeline
from app.services.types import AudioFrame

SPOKEN_SENTENCE = "Patient reports a new headache for the past three days with mild nausea."


def speech_like_wav(seconds: float = 2.0, sample_rate: int = 16000) -> bytes:
    """A WAV loud enough to pass voice-activity detection."""
    frames = bytearray()
    for index in range(int(seconds * sample_rate)):
        t = index / sample_rate
        envelope = 0.5 * (1.0 + math.sin(2 * math.pi * 4.0 * t - math.pi / 2))
        value = 0.7 * envelope * math.sin(2 * math.pi * 140.0 * t)
        frames += struct.pack("<h", int(max(-1.0, min(1.0, value)) * 26000))

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))
    return buffer.getvalue()


class StubGeminiASR(GeminiASRProvider):
    """GeminiASRProvider with only the network call replaced.

    Everything else - payload encoding, JSON parsing, timestamp handling and the
    diarization handoff - is the production code path.
    """

    def __init__(self, response: str) -> None:
        super().__init__(model="stub-model")
        self._response = response
        self.calls: list[tuple[int, str]] = []

    def _generate(self, payload: bytes, mime_type: str) -> str:
        self.calls.append((len(payload), mime_type))
        return self._response


# --------------------------------------------------------------- provider choice
def test_simulated_audio_uses_the_script() -> None:
    provider = build_asr_provider(script=get_script(None), audio_source=AudioSource.SIMULATION)
    assert isinstance(provider, MockASRProvider)


@pytest.mark.parametrize("source", [AudioSource.MICROPHONE, AudioSource.UPLOAD])
def test_real_audio_never_gets_the_scripted_provider(source: AudioSource, monkeypatch) -> None:
    """The core regression: real audio must not be answered with demo text."""
    monkeypatch.setattr(settings, "asr_provider", ASRProviderName.MOCK)
    provider = build_asr_provider(script=get_script(None), audio_source=source)
    assert not isinstance(provider, MockASRProvider)
    assert isinstance(provider, UnavailableASRProvider)


def test_missing_api_key_is_reported_not_faked(monkeypatch) -> None:
    monkeypatch.setattr(settings, "asr_provider", ASRProviderName.GEMINI)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    provider = build_asr_provider(audio_source=AudioSource.MICROPHONE)
    assert isinstance(provider, UnavailableASRProvider)
    assert "GEMINI_API_KEY" in provider.reason


def test_default_real_audio_diarizer_is_not_the_mock(monkeypatch) -> None:
    monkeypatch.setattr(settings, "diarization_provider", settings.diarization_provider.GEMINI)
    assert isinstance(build_diarization_provider(audio_source=AudioSource.MICROPHONE), GeminiDiarizationProvider)


async def test_unavailable_provider_raises_instead_of_returning_text() -> None:
    provider = UnavailableASRProvider("no engine configured")
    frame = AudioFrame(
        session_id="s1", sequence=1, pcm=b"\x00\x00", sample_rate=16000, channels=1,
        start_time=0.0, end_time=1.0, speech_ratio=0.9,
    )
    with pytest.raises(Exception) as excinfo:
        await provider.transcribe(frame)
    assert "no engine configured" in str(excinfo.value)


# ------------------------------------------------------------ gemini asr provider
async def test_gemini_asr_returns_spoken_words_and_speaker_turns() -> None:
    response = (
        '{"turns":['
        '{"speaker":"speaker_0","text":"Good morning, what brings you in?",'
        '"start":0.0,"end":2.0,"confidence":0.95},'
        '{"speaker":"speaker_1","text":"' + SPOKEN_SENTENCE + '",'
        '"start":2.0,"end":6.0,"confidence":0.91}'
        "]}"
    )
    provider = StubGeminiASR(response)
    frame = AudioFrame(
        session_id="s1", sequence=3, pcm=b"\x10\x00" * 16000, sample_rate=16000, channels=1,
        start_time=10.0, end_time=16.0, speech_ratio=0.8,
    )

    segments = await provider.transcribe(frame)

    assert [segment.text for segment in segments] == [
        "Good morning, what brings you in?",
        SPOKEN_SENTENCE,
    ]
    # Audio is sent as WAV, and timestamps are offset onto the session timeline.
    assert provider.calls and provider.calls[0][1] == "audio/wav"
    assert segments[0].start_time == 10.0
    assert segments[1].end_time == 16.0

    turns = frame.hints[DIARIZATION_HINT_KEY]
    assert [turn.speaker_id for turn in turns] == ["speaker_0", "speaker_1"]
    assert await GeminiDiarizationProvider().diarize(frame) == turns


async def test_gemini_asr_reports_no_speech_as_empty_not_invented() -> None:
    provider = StubGeminiASR('{"turns":[]}')
    frame = AudioFrame(
        session_id="s1", sequence=1, pcm=b"\x10\x00" * 8000, sample_rate=16000, channels=1,
        start_time=0.0, end_time=1.0, speech_ratio=0.5,
    )
    assert await provider.transcribe(frame) == []


async def test_gemini_asr_skips_silence_without_calling_the_api() -> None:
    provider = StubGeminiASR('{"turns":[{"speaker":"speaker_0","text":"hello"}]}')
    frame = AudioFrame(
        session_id="s1", sequence=1, pcm=b"\x00\x00" * 8000, sample_rate=16000, channels=1,
        start_time=0.0, end_time=1.0, speech_ratio=0.0,
    )
    assert await provider.transcribe(frame) == []
    assert provider.calls == []


async def test_gemini_asr_rejects_containers_it_cannot_send() -> None:
    provider = StubGeminiASR('{"turns":[]}')
    frame = AudioFrame(
        session_id="s1", sequence=1, pcm=b"\x1aE\xdf\xa3webm-bytes", sample_rate=16000, channels=1,
        start_time=0.0, end_time=2.0, decoded=False,
        hints={"container_mime_type": "audio/webm;codecs=opus"},
    )
    with pytest.raises(Exception) as excinfo:
        await provider.transcribe(frame)
    assert "cannot be transcribed" in str(excinfo.value)


async def test_gemini_asr_forwards_supported_compressed_containers() -> None:
    provider = StubGeminiASR(f'{{"turns":[{{"speaker":"speaker_0","text":"{SPOKEN_SENTENCE}"}}]}}')
    frame = AudioFrame(
        session_id="s1", sequence=1, pcm=b"OggS-bytes", sample_rate=16000, channels=1,
        start_time=0.0, end_time=3.0, decoded=False,
        hints={"container_mime_type": "audio/ogg; codecs=opus"},
    )
    segments = await provider.transcribe(frame)
    assert segments[0].text == SPOKEN_SENTENCE
    assert provider.calls[0][1] == "audio/ogg"
    # No timestamps from the model: bounds fall back inside the clip duration.
    assert 0.0 <= segments[0].start_time < segments[0].end_time <= 3.0


# --------------------------------------------------------------------- endpoints
async def _microphone_session(client) -> dict:
    response = await client.post(
        "/api/sessions",
        json={
            "name": "Live microphone encounter",
            "patient_id": "SIM-PT-900",
            "scenario": "chest_discomfort",
            "simulation_type": "OSCE",
            "doctor_name": "Dr. Real",
            "mode": SessionMode.MICROPHONE.value,
            "audio_source": AudioSource.MICROPHONE.value,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    await client.post(f"/api/sessions/{body['id']}/start")
    return body


async def _transcript_texts(client, session_id: str) -> list[str]:
    response = await client.get(f"/api/sessions/{session_id}/transcript")
    assert response.status_code == 200, response.text
    return [segment["text"] for segment in response.json()]


async def test_uploaded_recording_is_transcribed_into_the_session(client) -> None:
    session = await _microphone_session(client)
    runtime = pipeline.runtime(session["id"])
    assert runtime is not None
    runtime.asr = StubGeminiASR(
        '{"turns":[{"speaker":"speaker_0","text":"Good morning, what brings you in today?",'
        '"start":0.0,"end":1.5,"confidence":0.95},'
        '{"speaker":"speaker_1","text":"' + SPOKEN_SENTENCE + '","start":1.5,"end":3.5,"confidence":0.92}]}'
    )
    runtime.diarizer = GeminiDiarizationProvider()

    response = await client.post(
        f"/api/sessions/{session['id']}/audio/upload",
        files={"file": ("take.wav", speech_like_wav(), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True

    texts = await _transcript_texts(client, session["id"])
    assert SPOKEN_SENTENCE in texts

    # And crucially: none of the scripted demo lines leaked in.
    demo_lines = {utterance.text for utterance in get_script(None).utterances}
    assert not demo_lines.intersection(texts)


async def test_microphone_chunk_is_transcribed(client) -> None:
    session = await _microphone_session(client)
    runtime = pipeline.runtime(session["id"])
    assert runtime is not None
    runtime.asr = StubGeminiASR(
        f'{{"turns":[{{"speaker":"speaker_0","text":"{SPOKEN_SENTENCE}","start":0.0,"end":2.0}}]}}'
    )
    runtime.diarizer = GeminiDiarizationProvider()

    response = await client.post(
        f"/api/sessions/{session['id']}/audio/chunk",
        json={
            "audio_base64": base64.b64encode(speech_like_wav()).decode(),
            "mime_type": "audio/wav",
            "sample_rate": 16000,
            "channels": 1,
            "duration_seconds": 2.0,
        },
    )
    assert response.status_code == 200, response.text

    assert await _transcript_texts(client, session["id"]) == [SPOKEN_SENTENCE]


async def test_upload_without_a_transcription_engine_fails_loudly(client, monkeypatch) -> None:
    """Gemini ASR without a key must mean a visible error, not demo content."""
    monkeypatch.setattr(settings, "asr_provider", ASRProviderName.GEMINI)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    session = await _microphone_session(client)
    runtime = pipeline.runtime(session["id"])
    assert runtime is not None
    assert isinstance(runtime.asr, UnavailableASRProvider)  # test env has no key

    response = await client.post(
        f"/api/sessions/{session['id']}/audio/upload",
        files={"file": ("take.wav", speech_like_wav(), "audio/wav")},
    )
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]

    assert await _transcript_texts(client, session["id"]) == []


async def test_recording_with_no_recognisable_speech_is_reported(client) -> None:
    session = await _microphone_session(client)
    runtime = pipeline.runtime(session["id"])
    assert runtime is not None
    runtime.asr = StubGeminiASR('{"turns":[]}')

    response = await client.post(
        f"/api/sessions/{session['id']}/audio/upload",
        files={"file": ("take.wav", speech_like_wav(), "audio/wav")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "No speech was recognised" in body["message"]
