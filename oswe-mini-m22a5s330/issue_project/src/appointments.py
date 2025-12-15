import sqlite3
import uuid
import requests
import time
import logging
# tenacity is optional in this environment, provide a fallback retry
try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    TENACITY_AVAILABLE = True
except Exception:
    TENACITY_AVAILABLE = False


logger = logging.getLogger("appointment_service")

DB_PATH = "issue_project_state.db"

# Simple initialization
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        appointment_id TEXT PRIMARY KEY,
        user_id TEXT,
        start_time TEXT,
        duration INTEGER,
        status TEXT,
        idempotency_key TEXT,
        calendar_id TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        appointment_id TEXT,
        action TEXT,
        payload TEXT,
        processed INTEGER DEFAULT 0
    )""")
    conn.commit()
    conn.close()

# Send to calendar with retries and timeout
def call_calendar(payload, timeout=3, max_attempts=5):
    logger.info("call_calendar attempt", extra={"payload": payload})
    attempt = 0
    while True:
        attempt += 1
        try:
            r = requests.post("http://127.0.0.1:5001/api/v2/calendar", json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as ex:
            logger.warning("call_calendar failed", extra={"attempt": attempt, "error": str(ex)})
            if attempt >= max_attempts:
                raise
            sleep_secs = min(0.2 * (2 ** (attempt - 1)), 4)
            time.sleep(sleep_secs)

# Basic create appointment flow with idempotency

def create_appointment(user_id, start_time, duration, idempotency_key=None, metadata=None):
    if not idempotency_key:
        raise ValueError("idempotency_key is required")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Check idempotency
    cur.execute("SELECT appointment_id, status, calendar_id FROM appointments WHERE idempotency_key=?", (idempotency_key,))
    row = cur.fetchone()
    if row:
        appointment_id, status, calendar_id = row
        logger.info("idempotent_hit", extra={"idempotency_key": idempotency_key, "appointment_id": appointment_id})
        conn.close()
        return {"appointment_id": appointment_id, "status": status, "calendar_id": calendar_id}

    appointment_id = str(uuid.uuid4())
    # persist draft
    cur.execute("INSERT INTO appointments (appointment_id, user_id, start_time, duration, status, idempotency_key) VALUES (?,?,?,?,?,?)",
                (appointment_id, user_id, start_time, duration, 'draft', idempotency_key))
    conn.commit()

    # call calendar
    try:
        payload = {"idempotency_key": idempotency_key, "user_id": user_id, "start_time": start_time, "duration": duration}
        cal_resp = call_calendar(payload)
        calendar_id = cal_resp.get("calendar_id")
        cur.execute("UPDATE appointments SET status=?, calendar_id=? WHERE appointment_id=?", ('confirmed', calendar_id, appointment_id))
        # add notification to outbox
        cur.execute("INSERT INTO outbox (appointment_id, action, payload) VALUES (?,?,?)", (appointment_id, 'notify', '{}'))
        conn.commit()
        return {"appointment_id": appointment_id, "status": 'confirmed', "calendar_id": calendar_id}
    except Exception as ex:
        logger.exception("calendar_failed")
        # leave draft and schedule compensation
        cur.execute("INSERT INTO outbox (appointment_id, action, payload) VALUES (?,?,?)", (appointment_id, 'compensate_cancel', '{}'))
        conn.commit()
        raise
    finally:
        conn.close()

# Outbox processor

def process_outbox_once():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, appointment_id, action FROM outbox WHERE processed=0 ORDER BY id LIMIT 10")
    rows = cur.fetchall()
    for id_, appointment_id, action in rows:
        try:
            if action == 'notify':
                # simulate notify
                logger.info("notify", extra={"appointment_id": appointment_id})
            elif action == 'compensate_cancel':
                # call calendar cancel
                # In real code we'd call external cancel API
                logger.info("compensate_cancel", extra={"appointment_id": appointment_id})
            cur.execute("UPDATE outbox SET processed=1 WHERE id=?", (id_,))
            conn.commit()
        except Exception:
            logger.exception("outbox_handler_failed")
    conn.close()
