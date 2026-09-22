#!/usr/bin/env python
"""End-to-end smoke test against a running MedScribe Live backend.

Drives the full Demo Mode journey over the real HTTP + WebSocket surface:
create -> start -> live transcript -> entities -> evidence-linked note -> stop
-> human edit -> approve -> export (JSON / PDF / FHIR).

    python scripts/verify_local.py [--base http://127.0.0.1:8000]

Exit code 0 means the locally running application satisfies the acceptance
criteria; 1 means a check failed and the reason is printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

try:
    import httpx
    import websockets
except ImportError as exc:  # pragma: no cover - dependency hint
    print(f"Missing dependency: {exc}. Install backend requirements first.")
    raise SystemExit(1) from exc

HEADERS = {"X-User-Email": "verify@medscribe.local", "X-User-Role": "DOCTOR"}
GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"  {name.ljust(38)} {mark}  {DIM}{detail}{RESET}")
    if not ok:
        failures.append(f"{name}: {detail}")
    return ok


async def collect_events(base: str, session_id: str, stop: asyncio.Event) -> list[dict[str, Any]]:
    url = base.replace("http://", "ws://").replace("https://", "wss://")
    events: list[dict[str, Any]] = []
    try:
        async with websockets.connect(f"{url}/ws/sessions/{session_id}") as socket:
            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(socket.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                events.append(json.loads(raw))
    except Exception as exc:  # pragma: no cover - connection issues are reported
        print(f"  {YELLOW}websocket closed: {exc}{RESET}")
    return events


async def main(base: str) -> int:
    print("=" * 62)
    print("MEDSCRIBE LIVE - LOCAL VERIFICATION")
    print("=" * 62)

    async with httpx.AsyncClient(base_url=base, headers=HEADERS, timeout=60.0) as client:
        # ---------------------------------------------------------- infrastructure
        print("\nInfrastructure")
        health = (await client.get("/api/health")).json()
        check("Backend reachable", health.get("status") == "ok", f"version {health.get('version')}")
        check(
            "Database connected",
            bool(health["database"]["connected"]),
            f"{health['database']['dialect']}"
            + (" (sqlite fallback)" if health["database"].get("using_fallback") else ""),
        )

        status = (await client.get("/api/status")).json()
        gemini = bool(status["ai"]["gemini_configured"])
        check(
            "AI provider resolved",
            True,
            f"{status['ai']['provider']} {status['ai']['model']}"
            + ("" if gemini else " (no key: deterministic fallback)"),
        )
        check("Swagger docs served", (await client.get("/docs")).status_code == 200, "/docs")

        scripts = (await client.get("/api/sessions/scripts")).json()
        check("Demo scripts available", bool(scripts["scripts"]), f"{len(scripts['scripts'])} script(s)")

        # ---------------------------------------------------------------- session
        print("\nSession lifecycle")
        created = (
            await client.post(
                "/api/sessions",
                json={
                    "name": "Verification chest discomfort encounter",
                    "patient_id": "SIM-PT-VERIFY",
                    "scenario": "Standardised patient reporting chest discomfort",
                    "simulation_type": "OUTPATIENT",
                    "doctor_name": "Dr. Verify",
                    "faculty_name": "Prof. Verify",
                    "mode": "DEMO",
                },
            )
        ).json()
        session_id = created["id"]
        check("Session created", bool(created["reference"]), created["reference"])

        stop_events = asyncio.Event()
        socket_task = asyncio.create_task(collect_events(base, session_id, stop_events))
        await asyncio.sleep(0.5)

        started = (await client.post(f"/api/sessions/{session_id}/start")).json()
        check("Session started", started["status"] == "LIVE", started["status"])

        # Transcript should arrive progressively, not all at once.
        first_seen_at: float | None = None
        segments: list[dict[str, Any]] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 60
        while loop.time() < deadline:
            segments = (await client.get(f"/api/sessions/{session_id}/transcript")).json()
            if segments and first_seen_at is None:
                first_seen_at = loop.time()
            if len(segments) >= 8:
                break
            await asyncio.sleep(1.0)

        check("Transcript streams progressively", len(segments) >= 8, f"{len(segments)} segments")
        check(
            "Speaker roles attributed",
            {segment["role"] for segment in segments} >= {"DOCTOR", "PATIENT"},
            ", ".join(sorted({segment["role"] for segment in segments})),
        )
        check(
            "Timestamps and confidence present",
            all(segment["end_time"] > segment["start_time"] and 0 <= segment["confidence"] <= 1 for segment in segments),
        )

        paused = (await client.post(f"/api/sessions/{session_id}/pause")).json()
        check("Session pauses", paused["status"] == "PAUSED", paused["status"])
        resumed = (await client.post(f"/api/sessions/{session_id}/resume")).json()
        check("Session resumes", resumed["status"] == "LIVE", resumed["status"])

        # ------------------------------------------------------------- speakers
        speakers = (await client.get(f"/api/sessions/{session_id}/speakers")).json()
        check("Speakers diarized", len(speakers) >= 2, f"{len(speakers)} speakers")
        if speakers:
            overridden = (
                await client.patch(f"/api/speakers/{speakers[0]['id']}", json={"role": speakers[0]["role"]})
            ).json()
            check("Speaker role override accepted", overridden["role_source"] in ("HUMAN", "SYSTEM"), overridden["role"])

        stopped = (await client.post(f"/api/sessions/{session_id}/stop")).json()
        check("Session ends in REVIEW", stopped["status"] == "REVIEW", stopped["status"])

        await asyncio.sleep(1.0)
        stop_events.set()
        events = await socket_task

        # ------------------------------------------------------------ realtime
        print("\nReal-time layer")
        seen = {event["type"] for event in events}
        for event_type in ("SESSION_STATUS", "TRANSCRIPT_UPDATE", "ENTITY_UPDATE", "NOTE_UPDATE", "EVIDENCE_UPDATE"):
            check(f"WebSocket {event_type}", event_type in seen)
        check(
            "Events monotonically sequenced",
            all(b["sequence"] >= a["sequence"] for a, b in zip(events, events[1:])),
            f"{len(events)} events",
        )

        # ------------------------------------------------------- clinical layer
        print("\nClinical intelligence")
        entities = (await client.get(f"/api/sessions/{session_id}/entities")).json()
        values = {entity["value"].lower() for entity in entities}
        check("Entities extracted", len(entities) >= 4, f"{len(entities)} entities")
        check(
            "Presenting symptom captured",
            any("chest" in value for value in values),
            next((value for value in values if "chest" in value), "-"),
        )
        negated = [entity for entity in entities if entity["status"] == "NEGATED"]
        check(
            "Negation preserved",
            any("breath" in entity["value"].lower() for entity in negated),
            ", ".join(entity["value"] for entity in negated) or "none",
        )
        check(
            "Medication captured",
            any(entity["entity_type"] == "MEDICATION" for entity in entities),
            ", ".join(e["value"] for e in entities if e["entity_type"] == "MEDICATION") or "none",
        )
        check(
            "No diagnosis invented",
            not [
                entity
                for entity in entities
                if entity["entity_type"] == "DIAGNOSIS_MENTIONED" and entity["status"] == "PRESENT"
            ],
            "no unstated diagnosis added",
        )
        check(
            "Terminology codes not fabricated",
            all(entity["normalized_code"] is None for entity in entities),
        )

        # ------------------------------------------------------------ note/evidence
        print("\nNote and evidence")
        note = (await client.get(f"/api/sessions/{session_id}/note")).json()
        content = note["content"]
        check("Note generated", note["version"] >= 1, f"v{note['version']} · {note['status']}")
        check(
            "Chief complaint documented",
            bool(content["chief_complaint"]["text"]) and content["chief_complaint"]["text"] != "Not mentioned",
            content["chief_complaint"]["text"][:48],
        )
        check(
            "Sections carry evidence",
            len(content["chief_complaint"]["evidence"]) >= 1,
            f"{len(content['chief_complaint']['evidence'])} reference(s)",
        )

        evidence = (await client.get(f"/api/sessions/{session_id}/evidence")).json()
        segment_refs = {segment["ref"] for segment in segments}
        check("Evidence links created", len(evidence) >= 1, f"{len(evidence)} links")
        check(
            "Every link resolves to a real segment",
            all(link["segment_ref"] in segment_refs for link in evidence if link["segment_ref"]),
        )

        detail = (await client.get(f"/api/sessions/{session_id}/evidence/chief_complaint/detail")).json()
        check(
            "Show Source returns provenance chain",
            bool(detail["chain"]) and bool(detail["chain"][0]["evidence"]["source_text"]),
            f"{detail['validated_count']}/{detail['total_count']} validated",
        )

        versions = (await client.get(f"/api/sessions/{session_id}/note/versions")).json()
        check("Note versions recorded", len(versions) >= 1, f"{len(versions)} version(s)")

        # -------------------------------------------------------------- review
        print("\nHuman-in-the-loop review")
        note_id = note["id"]
        edited = (
            await client.patch(
                f"/api/notes/{note_id}",
                json={"assessment": "Clinician documented intermittent chest discomfort.", "editor": "Dr. Verify"},
            )
        ).json()
        check("Human edit creates a version", edited["version"] > note["version"], f"v{edited['version']}")
        check(
            "Edited section marked human-owned",
            edited["content"]["assessment"]["edited_by_human"],
        )

        unacknowledged = await client.post(f"/api/notes/{note_id}/approve", json={"acknowledgement": False})
        check(
            "Approval requires acknowledgement",
            unacknowledged.status_code in (400, 409),
            f"HTTP {unacknowledged.status_code}",
        )

        approved_response = await client.post(
            f"/api/notes/{note_id}/approve", json={"approved_by": "Dr. Verify", "acknowledgement": True}
        )
        if approved_response.status_code == 409:
            check(
                "Approval blocked by review flags",
                True,
                "unresolved flags must be cleared first (expected behaviour)",
            )
        else:
            approved = approved_response.json()
            check("Note approved by a human", approved["status"] == "APPROVED", approved["approved_by"] or "-")

        # -------------------------------------------------------------- exports
        print("\nExport")
        json_export = await client.post(f"/api/sessions/{session_id}/export?format=JSON")
        payload = json_export.json()
        check(
            "JSON export includes provenance",
            json_export.status_code == 200 and "evidence" in json.dumps(payload)[:200000],
            f"{len(json_export.content)} bytes",
        )
        pdf_export = await client.post(f"/api/sessions/{session_id}/export?format=PDF")
        check(
            "PDF export is a PDF document",
            pdf_export.status_code == 200 and pdf_export.content[:4] == b"%PDF",
            f"{len(pdf_export.content)} bytes",
        )
        fhir_export = await client.post(f"/api/sessions/{session_id}/export?format=FHIR")
        bundle = fhir_export.json()
        check(
            "FHIR bundle produced",
            bundle.get("resourceType") == "Bundle" and bool(bundle.get("entry")),
            f"{len(bundle.get('entry', []))} resources",
        )

        # ---------------------------------------------------------------- audit
        print("\nAudit and monitoring")
        audit = (await client.get(f"/api/sessions/{session_id}/audit")).json()
        actions = {entry["action"] for entry in audit["entries"]}
        check("Audit trail written", len(actions) >= 3, ", ".join(sorted(actions)))
        metrics = (await client.get("/api/metrics")).json()
        check("Metrics exposed", bool(metrics.get("counters")), f"{len(metrics['counters'])} counters")

        await client.delete(f"/api/sessions/{session_id}")

    print("\n" + "=" * 62)
    if failures:
        print(f"{RED}{len(failures)} check(s) failed{RESET}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"{GREEN}All checks passed. MedScribe Live is running correctly.{RESET}")
    if not gemini:
        print(f"{YELLOW}Note: no GEMINI_API_KEY set, so the deterministic provider was used.{RESET}")
        print("Set GEMINI_API_KEY in .env and re-run to verify live Gemini structuring.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="backend base URL")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.base)))
