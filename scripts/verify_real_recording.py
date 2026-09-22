"""Verify the real recording path end to end against a running backend.

Uploads spoken audio that does not exist anywhere in the demo scripts and
asserts that the resulting transcript and clinical note came from that audio.

    python scripts/make_test_speech.ps1   (generates verification_speech.wav)
    python scripts/verify_real_recording.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000/api"
REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIO = REPO_ROOT / "verification_speech.wav"

# Spoken in the test audio; absent from every bundled demo conversation.
EXPECTED_PHRASES = ["headache", "three days", "nausea"]
HEADERS = {"X-User-Email": "dev.clinician@medscribe.local", "X-User-Role": "DOCTOR"}


def main() -> int:
    if not AUDIO.exists():
        print(f"FAIL missing {AUDIO}. Run scripts/make_test_speech.ps1 first.")
        return 1

    with httpx.Client(base_url=BASE, headers=HEADERS, timeout=300.0) as client:
        status = client.get("/status").json()
        asr = status["providers"]["asr"]
        print(f"ASR provider: {asr['name']} (mock={asr['mock']}, model={asr.get('model')})")
        if asr["mock"]:
            print("FAIL the backend is configured to script transcripts instead of transcribing audio.")
            return 1

        session = client.post(
            "/sessions",
            json={
                "name": "Real microphone verification",
                "patient_id": "SIM-PT-VERIFY",
                "scenario": "New headache with nausea",
                "simulation_type": "OUTPATIENT",
                "doctor_name": "Dr. Whitfield",
                "mode": "MICROPHONE",
                "audio_source": "MICROPHONE",
            },
        ).json()
        session_id = session["id"]
        print(f"session {session['reference']} ({session_id})")

        client.post(f"/sessions/{session_id}/start").raise_for_status()

        audio = AUDIO.read_bytes()
        print(f"uploading {len(audio)} bytes of spoken audio...")
        started = time.perf_counter()
        response = client.post(
            f"/sessions/{session_id}/audio/upload",
            files={"file": (AUDIO.name, audio, "audio/wav")},
        )
        elapsed = time.perf_counter() - started
        if response.status_code != 200:
            print(f"FAIL upload returned {response.status_code}: {response.text[:400]}")
            return 1
        body = response.json()
        print(f"upload ok={body['ok']} in {elapsed:.1f}s :: {body['message']}")
        if not body["ok"]:
            return 1

        segments = client.get(f"/sessions/{session_id}/transcript").json()
        print(f"\n--- transcript ({len(segments)} segments) ---")
        for segment in segments:
            print(f"  [{segment['role']:<8} {segment['speaker_label']}] {segment['text']}")

        transcript = " ".join(segment["text"] for segment in segments).lower()

        missing = [phrase for phrase in EXPECTED_PHRASES if phrase not in transcript]
        if missing:
            print(f"\nFAIL transcript is missing spoken content: {missing}")
            return 1
        print("\nPASS transcript contains the actually spoken words")

        # The demo script must not have leaked in.
        sys.path.insert(0, str(REPO_ROOT / "backend"))
        from app.services.demo.conversations import get_script

        leaked = [
            utterance.text
            for utterance in get_script(None).utterances
            if utterance.text.lower() in transcript
        ]
        if leaked:
            print(f"FAIL demo script lines appear in the transcript: {leaked[:3]}")
            return 1
        print("PASS no demo/scripted content in the transcript")

        # Force the structuring pass so the note reflects the whole recording.
        client.post(f"/sessions/{session_id}/retry-processing", timeout=300.0)
        stopped = client.post(f"/sessions/{session_id}/stop", timeout=300.0).json()
        print(f"session stopped -> {stopped['status']}")

        note = client.get(f"/sessions/{session_id}/note").json()
        print(f"\n--- clinical note ({note['status']}) ---")
        sections = note.get("content", {}).get("sections", {})
        for key, section in sections.items():
            text = (section or {}).get("text") or ""
            if text:
                print(f"  {key}: {text}")

        note_text = " ".join(
            (section or {}).get("text") or "" for section in sections.values()
        ).lower()
        entities = client.get(f"/sessions/{session_id}/clinical-info").json()
        entity_texts = " ".join(entity["text"].lower() for entity in entities.get("entities", []))
        print(f"\nentities: {[entity['text'] for entity in entities.get('entities', [])]}")

        grounded = "headache" in note_text or "headache" in entity_texts
        if not grounded:
            print("FAIL the clinical note/entities do not reflect the spoken content")
            return 1
        print("PASS the clinical note was generated from the spoken transcript")

    print("\nAll real-recording checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
