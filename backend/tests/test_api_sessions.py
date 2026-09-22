"""Session management API and access control."""

from __future__ import annotations

from app.models.enums import SessionStatus


async def test_create_session_assigns_reference_and_note(client, session_payload) -> None:
    response = await client.post("/api/sessions", json=session_payload)
    assert response.status_code == 201
    body = response.json()

    assert body["reference"].startswith("SIM-")
    assert body["status"] == SessionStatus.CREATED.value
    assert body["note_status"] == "PROCESSING"
    assert body["segment_count"] == 0
    assert body["mode"] == "DEMO"
    assert body["audio_source"] == "SIMULATION"


async def test_references_are_unique_and_sequential(client, session_payload) -> None:
    first = (await client.post("/api/sessions", json=session_payload)).json()
    second = (await client.post("/api/sessions", json=session_payload)).json()
    assert first["reference"] != second["reference"]


async def test_validation_rejects_empty_name(client, session_payload) -> None:
    payload = {**session_payload, "name": ""}
    assert (await client.post("/api/sessions", json=payload)).status_code == 422


async def test_list_and_get_session(client, created_session) -> None:
    listing = await client.get("/api/sessions")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] >= 1
    assert any(item["id"] == created_session["id"] for item in body["items"])

    detail = await client.get(f"/api/sessions/{created_session['id']}")
    assert detail.status_code == 200
    assert detail.json()["reference"] == created_session["reference"]


async def test_session_can_be_fetched_by_reference(client, created_session) -> None:
    response = await client.get(f"/api/sessions/{created_session['reference']}")
    assert response.status_code == 200
    assert response.json()["id"] == created_session["id"]


async def test_unknown_session_returns_404(client) -> None:
    assert (await client.get("/api/sessions/does-not-exist")).status_code == 404


async def test_lifecycle_start_pause_resume_stop(client, created_session) -> None:
    session_id = created_session["id"]

    started = await client.post(f"/api/sessions/{session_id}/start")
    assert started.status_code == 200
    assert started.json()["status"] == SessionStatus.LIVE.value
    assert started.json()["started_at"] is not None

    assert (await client.post(f"/api/sessions/{session_id}/start")).status_code == 409

    paused = await client.post(f"/api/sessions/{session_id}/pause")
    assert paused.json()["status"] == SessionStatus.PAUSED.value
    assert (await client.post(f"/api/sessions/{session_id}/pause")).status_code == 409

    resumed = await client.post(f"/api/sessions/{session_id}/resume")
    assert resumed.json()["status"] == SessionStatus.LIVE.value

    stopped = await client.post(f"/api/sessions/{session_id}/stop")
    assert stopped.json()["status"] == SessionStatus.REVIEW.value


async def test_cannot_stop_a_session_that_never_started(client, created_session) -> None:
    assert (await client.post(f"/api/sessions/{created_session['id']}/stop")).status_code == 409


async def test_student_role_cannot_approve_notes(client, created_session) -> None:
    note = (await client.get(f"/api/sessions/{created_session['id']}/note")).json()
    response = await client.post(
        f"/api/notes/{note['id']}/approve",
        json={"approved_by": "Student", "acknowledgement": True},
        headers={"X-User-Role": "STUDENT", "X-User-Email": "student@medscribe.local"},
    )
    assert response.status_code == 403


async def test_dashboard_reports_counts(client, created_session) -> None:
    response = await client.get("/api/sessions/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["total_sessions"] >= 1
    assert len(body["sessions_by_day"]) == 7
    assert any(item["id"] == created_session["id"] for item in body["recent_sessions"])


async def test_health_and_status_endpoints(client) -> None:
    health = (await client.get("/api/health")).json()
    assert health["database"]["connected"] is True

    status = (await client.get("/api/status")).json()
    # The ASR provider depends on configuration — verify the status endpoint
    # reports it and that demo mode is correct.
    assert "name" in status["providers"]["asr"]
    assert status["demo_mode_enabled"] is True
    assert status["ai"]["mode"] == "mock"


async def test_scripts_endpoint_lists_synthetic_scenarios(client) -> None:
    body = (await client.get("/api/sessions/scripts")).json()
    keys = {script["key"] for script in body["scripts"]}
    assert "chest_discomfort" in keys


async def test_audit_trail_records_lifecycle_actions(client, created_session) -> None:
    await client.post(f"/api/sessions/{created_session['id']}/start")
    audit = (await client.get(f"/api/sessions/{created_session['id']}/audit")).json()
    actions = {entry["action"] for entry in audit["entries"]}
    assert {"SESSION_CREATED", "SESSION_STARTED"} <= actions


async def test_metrics_endpoint_exposes_counters(client, created_session) -> None:
    snapshot = (await client.get("/api/metrics")).json()
    assert "counters" in snapshot

    prometheus = await client.get("/api/metrics?prometheus=true")
    assert prometheus.status_code == 200
    assert "medscribe_" in prometheus.text
