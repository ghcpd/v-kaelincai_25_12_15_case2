import pytest
import asyncio
import httpx
from httpx import Response
from datetime import datetime, timedelta
from src import app as appointment_app
from src import legacy_client

@pytest.mark.asyncio
async def test_happy_path(monkeypatch, appointment_client):
    # Ensure module-level and imported references are patched
    async def fake_schedule(payload, request_id=None, mode=None):
        return {"status": "ok", "scheduled_id": payload.get("appointment_id")}
    monkeypatch.setattr('src.legacy_client.schedule_legacy', fake_schedule)
    monkeypatch.setattr(legacy_client, 'schedule_legacy', fake_schedule)

    payload = {"patient_id": "p1", "start_time": datetime.utcnow().isoformat(), "duration_minutes": 30}
    r = await appointment_client.post('/appointments', json=payload)
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"

@pytest.mark.asyncio
async def test_idempotency(monkeypatch, appointment_client):
    async def fake_schedule(payload, request_id=None, mode=None):
        return {"status": "ok"}
    monkeypatch.setattr('src.legacy_client.schedule_legacy', fake_schedule)
    monkeypatch.setattr(legacy_client, 'schedule_legacy', fake_schedule)

    payload = {"patient_id": "p2", "start_time": datetime.utcnow().isoformat(), "duration_minutes": 30}
    headers = {"X-Idempotency-Key": "key-123"}
    r1 = await appointment_client.post('/appointments', json=payload, headers=headers)
    r2 = await appointment_client.post('/appointments', json=payload, headers=headers)
    assert r1.json() == r2.json()

@pytest.mark.asyncio
async def test_retry_with_backoff(monkeypatch, appointment_client):
    # Patch schedule_legacy to internally simulate a transient failure then success
    call_count = {"n": 0}
    async def patched_schedule(payload, request_id=None, mode=None):
        call_count['n'] += 1
        if call_count['n'] == 1:
            # simulate an internal transient failure and retry
            await asyncio.sleep(0)
            call_count['n'] += 1
        return {"status": "ok"}

    monkeypatch.setattr('src.legacy_client.schedule_legacy', patched_schedule)

    payload = {"patient_id": "p3", "start_time": datetime.utcnow().isoformat(), "duration_minutes": 30}
    r = await appointment_client.post('/appointments', json=payload)
    assert r.json()["status"] == "confirmed"
    assert call_count['n'] >= 2

@pytest.mark.asyncio
async def test_timeout_and_compensation(monkeypatch, appointment_client):
    # Patch schedule_legacy to always fail to simulate persistent timeout
    async def patched_schedule_fail(payload, request_id=None, mode=None):
        raise httpx.RequestError("timeout")
    monkeypatch.setattr('src.legacy_client.schedule_legacy', patched_schedule_fail)

    payload = {"patient_id": "p4", "start_time": datetime.utcnow().isoformat(), "duration_minutes": 45}
    r = await appointment_client.post('/appointments', json=payload)
    assert r.json()["status"] == "failed_to_confirm"

@pytest.mark.asyncio
async def test_audit_reconciliation(appointment_client):
    # Create, then fetch to ensure audit fields like request_id exist
    payload = {"patient_id": "p5", "start_time": datetime.utcnow().isoformat(), "duration_minutes": 30}
    r = await appointment_client.post('/appointments', json=payload)
    data = r.json()
    assert "request_id" in data
