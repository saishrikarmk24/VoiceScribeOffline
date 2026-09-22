"""Human review, approval gating and the three export formats."""

from __future__ import annotations

import asyncio
import json

from app.models.enums import NoteStatus


async def run_demo_session(client, session_payload) -> dict:
    session = (await client.post("/api/sessions", json=session_payload)).json()
    await client.post(f"/api/sessions/{session['id']}/start")
    deadline = asyncio.get_running_loop().time() + 20
    while asyncio.get_running_loop().time() < deadline:
        segments = (await client.get(f"/api/sessions/{session['id']}/transcript")).json()
        if len(segments) >= 10:
            break
        await asyncio.sleep(0.05)
    await client.post(f"/api/sessions/{session['id']}/stop")
    return session


async def test_human_edit_creates_a_version_and_clears_flags(client, session_payload) -> None:
    session = await run_demo_session(client, session_payload)
    note = (await client.get(f"/api/sessions/{session['id']}/note")).json()

    edited = await client.patch(
        f"/api/notes/{note['id']}",
        json={
            "chief_complaint": "Intermittent central chest pressure since yesterday evening.",
            "editor": "Dr. Reviewer",
        },
    )
    assert edited.status_code == 200
    body = edited.json()
    assert body["content"]["chief_complaint"]["text"].startswith("Intermittent central chest pressure")
    assert body["content"]["chief_complaint"]["edited_by_human"] is True
    assert body["version"] > note["version"]

    versions = (await client.get(f"/api/sessions/{session['id']}/note/versions")).json()
    assert any(version["author_type"] == "HUMAN" for version in versions)


async def test_empty_edit_is_rejected(client, session_payload) -> None:
    session = await run_demo_session(client, session_payload)
    note = (await client.get(f"/api/sessions/{session['id']}/note")).json()
    assert (await client.patch(f"/api/notes/{note['id']}", json={})).status_code == 400


async def test_approval_requires_human_acknowledgement(client, session_payload) -> None:
    session = await run_demo_session(client, session_payload)
    note = (await client.get(f"/api/sessions/{session['id']}/note")).json()

    refused = await client.post(f"/api/notes/{note['id']}/approve", json={"acknowledgement": False})
    assert refused.status_code == 409

    approved = await client.post(
        f"/api/notes/{note['id']}/approve",
        json={"approved_by": "Dr. Reviewer", "acknowledgement": True},
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == NoteStatus.APPROVED.value
    assert body["approved_by"] == "Dr. Reviewer"
    assert body["approved_at"] is not None

    session_after = (await client.get(f"/api/sessions/{session['id']}")).json()
    assert session_after["status"] == "APPROVED"

    audit = (await client.get(f"/api/sessions/{session['id']}/audit")).json()
    assert any(entry["action"] == "NOTE_APPROVED" for entry in audit["entries"])


async def test_note_is_never_auto_approved(client, session_payload) -> None:
    session = await run_demo_session(client, session_payload)
    note = (await client.get(f"/api/sessions/{session['id']}/note")).json()
    assert note["status"] != NoteStatus.APPROVED.value
    assert note["approved_by"] is None


async def test_approved_note_can_be_reopened(client, session_payload) -> None:
    session = await run_demo_session(client, session_payload)
    note = (await client.get(f"/api/sessions/{session['id']}/note")).json()
    await client.post(f"/api/notes/{note['id']}/approve", json={"acknowledgement": True})
    reopened = await client.post(f"/api/notes/{note['id']}/reopen")
    assert reopened.status_code == 200
    assert reopened.json()["status"] == NoteStatus.DRAFT.value


async def test_json_export_contains_the_full_provenance_chain(client, session_payload) -> None:
    session = await run_demo_session(client, session_payload)
    response = await client.post(f"/api/sessions/{session['id']}/export?format=JSON")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]

    payload = json.loads(response.content)
    assert payload["export_format"] in ("VOICESCRIBE_JSON_V1", "MEDSCRIBE_JSON_V1")
    assert "human review" in payload["disclaimer"].lower()
    assert payload["session"]["reference"] == session["reference"]
    assert len(payload["transcript"]) == 10
    assert payload["clinical_entities"]
    assert payload["evidence_links"]
    assert payload["clinical_note"]["content"]["chief_complaint"]["evidence"]


async def test_pdf_export_returns_a_pdf_document(client, session_payload) -> None:
    session = await run_demo_session(client, session_payload)
    response = await client.post(f"/api/sessions/{session['id']}/export?format=PDF")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:5] == b"%PDF-"
    assert len(response.content) > 2000


async def test_fhir_export_produces_a_compatible_bundle(client, session_payload) -> None:
    session = await run_demo_session(client, session_payload)
    response = await client.post(f"/api/sessions/{session['id']}/export?format=FHIR")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/fhir+json")

    bundle = json.loads(response.content)
    assert bundle["resourceType"] == "Bundle"
    resource_types = [entry["resource"]["resourceType"] for entry in bundle["entry"]]
    assert "Patient" in resource_types
    assert "Encounter" in resource_types
    assert "Observation" in resource_types
    assert "MedicationStatement" in resource_types
    assert "DiagnosticReport" in resource_types
    assert any("not conformance validated" in tag["display"] for tag in bundle["meta"]["tag"])

    # No fabricated terminology codes.
    for entry in bundle["entry"]:
        resource = entry["resource"]
        for field in ("code", "medicationCodeableConcept"):
            concept = resource.get(field)
            if isinstance(concept, dict) and "coding" in concept:
                for coding in concept["coding"]:
                    assert coding.get("code") is not None


async def test_export_marks_approved_note_as_exported(client, session_payload) -> None:
    session = await run_demo_session(client, session_payload)
    note = (await client.get(f"/api/sessions/{session['id']}/note")).json()
    await client.post(f"/api/notes/{note['id']}/approve", json={"acknowledgement": True})

    response = await client.post(f"/api/sessions/{session['id']}/export?format=JSON")
    assert response.headers["X-MedScribe-Human-Approved"] == "true"

    after = (await client.get(f"/api/sessions/{session['id']}/note")).json()
    assert after["status"] == NoteStatus.EXPORTED.value
    assert after["exported_at"] is not None


async def test_export_preview_reports_fhir_resource_counts(client, session_payload) -> None:
    session = await run_demo_session(client, session_payload)
    preview = (await client.get(f"/api/sessions/{session['id']}/export/preview")).json()
    assert preview["fhir_resource_counts"]["Patient"] == 1
    assert preview["json_export"]["clinical_note"]["content"]["symptoms"]


async def test_unapproved_export_is_marked_as_such(client, session_payload) -> None:
    session = await run_demo_session(client, session_payload)
    response = await client.post(f"/api/sessions/{session['id']}/export?format=JSON")
    assert response.headers["X-MedScribe-Human-Approved"] == "false"
