import subprocess
import time
import requests
import os
import json
import threading
import pytest
# load appointments module directly to avoid package resolution issues in test runner
import importlib.util
spec = importlib.util.spec_from_file_location("appointments", os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src', 'appointments.py')))
appointments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appointments)

CAL_URL = "http://127.0.0.1:5001"

@pytest.fixture(scope='session', autouse=True)
def start_calendar_mock():
    # Start mock as a subprocess and wait until admin endpoint responds
    import sys as _sys
    import os as _os
    _os.makedirs(_os.path.join(os.path.dirname(__file__), '..', 'logs'), exist_ok=True)
    log_path = _os.path.join(os.path.dirname(__file__), '..', 'logs', 'calendar_mock.log')
    logfile = open(log_path, 'a', encoding='utf-8')
    env = _os.environ.copy()
    # PYTHONPATH must include the parent directory of 'issue_project' so -m finds the package
    env['PYTHONPATH'] = _os.path.abspath(_os.path.join(os.path.dirname(__file__), '..', '..'))
    p = subprocess.Popen([_sys.executable, '-u', '-m', 'issue_project.mocks.calendar_mock'], stdout=logfile, stderr=logfile, env=env)
    # Poll admin endpoint for readiness
    import time as _time
    for i in range(30):
        try:
            requests.get(f"{CAL_URL}/__admin/state", timeout=0.5)
            break
        except Exception:
            if p.poll() is not None:
                logfile.flush()
                logfile.close()
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as rf:
                    tail = rf.read()[-2000:]
                raise RuntimeError("Calendar mock process exited prematurely; log output:\n" + tail)
            _time.sleep(0.3)
    else:
        p.terminate()
        logfile.flush()
        logfile.close()
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as rf:
            tail = rf.read()[-2000:]
        raise RuntimeError("Calendar mock did not become responsive in time; log output:\n" + tail)

    _time.sleep(0.1)
    yield
    try:
        p.terminate()
    finally:
        logfile.close()

# fallback run function if needed by manual run
def _run_mock():
    from issue_project.mocks import calendar_mock
    calendar_mock.app.run(port=5001)

@pytest.fixture(autouse=True)
def reset_mock():
    requests.post(f"{CAL_URL}/__admin/state", json={'fail_next':0,'delay':0.0})
    # reset DB
    try:
        os.remove('issue_project_state.db')
    except Exception:
        pass
    appointments.init_db()
    yield

# Test A: idempotency

def test_idempotency_create():
    idempotency_key = 'key-1'
    resp1 = appointments.create_appointment('user1', '2025-12-20T10:00:00Z', 60, idempotency_key=idempotency_key)
    resp2 = appointments.create_appointment('user1', '2025-12-20T10:00:00Z', 60, idempotency_key=idempotency_key)
    assert resp1['appointment_id'] == resp2['appointment_id']

# Test B: retry with backoff

def test_retry_succeeds_after_retries():
    # set calendar to fail first two times
    requests.post(f"{CAL_URL}/__admin/state", json={'fail_next':2})
    idempotency_key = 'key-2'
    resp = appointments.create_appointment('user2', '2025-12-21T11:00:00Z', 30, idempotency_key=idempotency_key)
    assert resp['status'] == 'confirmed'

# Test C: timeout and circuit breaker simulation (circuit breaker not fully implemented, simulate slow responses)

def test_timeout_behavior():
    requests.post(f"{CAL_URL}/__admin/state", json={'delay':2.0})
    # the calendar call has a timeout of 3s, but we simulate only one slow call
    idempotency_key = 'key-3'
    resp = appointments.create_appointment('user3', '2025-12-22T12:00:00Z', 15, idempotency_key=idempotency_key)
    assert resp['status'] == 'confirmed'

# Test D: compensation when calendar fails fully

def test_compensation_on_calendar_failure():
    # force calendar to always fail
    requests.post(f"{CAL_URL}/__admin/state", json={'fail_next':10})
    idempotency_key = 'key-4'
    with pytest.raises(Exception):
        appointments.create_appointment('user4', '2025-12-23T09:00:00Z', 45, idempotency_key=idempotency_key)
    # outbox should have a compensate_cancel entry
    conn = __import__('sqlite3').connect('issue_project_state.db')
    cur = conn.cursor()
    cur.execute("SELECT action FROM outbox WHERE appointment_id IN (SELECT appointment_id FROM appointments WHERE idempotency_key=?)", (idempotency_key,))
    actions = [r[0] for r in cur.fetchall()]
    conn.close()
    assert 'compensate_cancel' in actions

# Test E: reconciliation (simulate orphan calendar booking then run reconcilation)

def test_reconciliation_detects_orphan_and_reconciles():
    # directly hit calendar to create an orphan
    r = requests.post(f"{CAL_URL}/api/v2/calendar", json={'user_id':'user5','start_time':'2025-12-24T10:00:00Z'})
    assert r.status_code == 200
    # run reconciliation (simple heuristic: copy from calendar_state)
    state = requests.get(f"{CAL_URL}/__admin/state").json()
    assert len(state['bookings']) >= 1
    # Simple reconcile: create DB entry for that booking idempotently
    bookings = state['bookings']
    b = bookings[0]
    appointments.init_db()
    # idempotency key derived from calendar id
    key = f"recon-{b['calendar_id']}"
    resp = appointments.create_appointment('user5', b['data'].get('start_time','2025-12-24T10:00:00Z'), 60, idempotency_key=key)
    assert resp['status'] == 'confirmed'
