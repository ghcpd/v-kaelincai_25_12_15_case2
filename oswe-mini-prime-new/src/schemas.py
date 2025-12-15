from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

class AppointmentCreate(BaseModel):
    patient_id: str = Field(..., min_length=1)
    start_time: datetime
    duration_minutes: int = Field(..., ge=15, le=240)
    reason: Optional[str] = None

class Appointment(BaseModel):
    id: str
    patient_id: str
    start_time: datetime
    duration_minutes: int
    status: str
    created_at: datetime
    request_id: Optional[str]
