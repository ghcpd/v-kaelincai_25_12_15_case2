import logging
import uuid
from fastapi import FastAPI, Header, HTTPException, Request
from typing import Optional
from datetime import datetime
from .schemas import AppointmentCreate, Appointment
from . import legacy_client
from .outbox import push

app = FastAPI()

# In-memory stores for prototype
DB = {}
IDEMPOTENCY = {}

logger = logging.getLogger("appointment_service")
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')

SENSITIVE_FIELDS = {"patient_ssn", "ssn", "credit_card"}

def mask_sensitive(payload: dict) -> dict:
    out = {}
    for k, v in payload.items():
        if k in SENSITIVE_FIELDS and isinstance(v, str):
            out[k] = v[:2] + "*" * max(0, len(v) - 4) + v[-2:]
        else:
            out[k] = v
    return out

@app.post("/appointments")
async def create_appointment(req: AppointmentCreate, request: Request, x_idempotency_key: Optional[str] = Header(None)):
    request_id = str(uuid.uuid4())
    logger.info("create_appointment_received", extra={"request_id": request_id, "payload": mask_sensitive(req.dict())})
    if x_idempotency_key:
        if x_idempotency_key in IDEMPOTENCY:
            stored = IDEMPOTENCY[x_idempotency_key]
            logger.info("idempotent_hit", extra={"idempotency_key": x_idempotency_key, "request_id": request_id})
            return stored
    # allocate appointment
    appt_id = str(uuid.uuid4())
    appt = Appointment(
        id=appt_id,
        patient_id=req.patient_id,
        start_time=req.start_time,
        duration_minutes=req.duration_minutes,
        status="pending",
        created_at=datetime.utcnow(),
        request_id=request_id,
    )
    DB[appt_id] = appt.dict()

    # push to outbox for downstream systems
    await push({"id": str(uuid.uuid4()), "type": "appointment.created", "appointment_id": appt_id, "ts": datetime.utcnow().isoformat()})

    # Call legacy system (sync path: for replacement we prefer async orchestration)
    try:
        logger.info("calling_legacy_callable", extra={"callable": repr(getattr(legacy_client, 'schedule_legacy', None)), "request_id": request_id})
        legacy_resp = await legacy_client.schedule_legacy({"appointment_id": appt_id, "start": req.start_time.isoformat()}, request_id=request_id)
        DB[appt_id]["status"] = "confirmed"
        logger.info("appointment_confirmed", extra={"appointment_id": appt_id, "legacy": legacy_resp})
    except Exception as ex:
        # leave appointment pending and record failure; compensation/outbox will handle
        DB[appt_id]["status"] = "failed_to_confirm"
        await push({"id": str(uuid.uuid4()), "type": "appointment.confirmation_failed", "appointment_id": appt_id, "error": str(ex)})
        logger.error("legacy_confirm_failed", extra={"appointment_id": appt_id, "err": str(ex)})

    result = DB[appt_id]
    if x_idempotency_key:
        IDEMPOTENCY[x_idempotency_key] = result
    return result

@app.get("/appointments/{appointment_id}")
async def get_appointment(appointment_id: str):
    if appointment_id not in DB:
        raise HTTPException(status_code=404, detail="not found")
    return DB[appointment_id]

@app.post("/outbox/flush")
async def flush_outbox():
    from .outbox import flush
    ready = await flush()
    return {"flushed": len(ready)}
