from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time
import random

app = FastAPI()

class Payload(BaseModel):
    appointment_id: str
    start: str

@app.post("/legacy/schedule")
async def schedule(payload: Payload, mode: str = "immediate"):
    # mode: immediate | pending | delayed | fail
    if mode == "immediate":
        return {"status": "ok", "scheduled_id": payload.appointment_id}
    elif mode == "pending":
        # Accept and return pending: means eventual confirmation via webhook/outbox
        return {"status": "pending", "scheduled_id": payload.appointment_id}
    elif mode == "delayed":
        # simulate network slowness > timeout
        time.sleep(5)
        return {"status": "ok", "scheduled_id": payload.appointment_id}
    else:
        raise HTTPException(status_code=500, detail="simulated failure")
