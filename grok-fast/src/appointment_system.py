"""
Appointment Booking System - Greenfield Replacement
Features: Idempotency, state machine, structured logging
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Dict, Optional
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import uuid

# Configure structured logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///appointments.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class AppointmentStatus(Enum):
    INIT = 'init'
    BOOKED = 'booked'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

from sqlalchemy import func

class Appointment(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idempotency_key = db.Column(db.String(255), unique=True, nullable=False)
    user_id = db.Column(db.String(255), nullable=False)
    datetime = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default=AppointmentStatus.INIT.value)
    created_at = db.Column(db.DateTime, default=func.now())
    updated_at = db.Column(db.DateTime, default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            'appointment_id': self.id,
            'status': self.status,
            'datetime': self.datetime.isoformat(),
            'user_id': self.user_id
        }

def init_db():
    with app.app_context():
        db.create_all()

@app.route('/appointments', methods=['POST'])
def book_appointment():
    data = request.get_json()
    idempotency_key = data.get('idempotency_key')
    user_id = data.get('user_id')
    datetime_str = data.get('datetime')

    if not all([idempotency_key, user_id, datetime_str]):
        logger.error("Missing required fields", extra={'request_id': idempotency_key})
        return jsonify({'error': 'Missing required fields'}), 400

    # Check idempotency
    existing = Appointment.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        logger.info("Idempotent request", extra={'request_id': idempotency_key, 'appointment_id': existing.id})
        return jsonify(existing.to_dict()), 200

    try:
        apt_datetime = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
    except ValueError:
        logger.error("Invalid datetime format", extra={'request_id': idempotency_key})
        return jsonify({'error': 'Invalid datetime format'}), 400

    # Check for conflicts (simple: no overlapping appointments)
    conflict = Appointment.query.filter(
        Appointment.datetime == apt_datetime,
        Appointment.status == AppointmentStatus.BOOKED.value
    ).first()
    if conflict:
        logger.warning("Appointment conflict", extra={'request_id': idempotency_key, 'datetime': datetime_str})
        appointment = Appointment(
            idempotency_key=idempotency_key,
            user_id=user_id,
            datetime=apt_datetime,
            status=AppointmentStatus.FAILED.value
        )
        db.session.add(appointment)
        db.session.commit()
        return jsonify(appointment.to_dict()), 409

    # Book appointment
    appointment = Appointment(
        idempotency_key=idempotency_key,
        user_id=user_id,
        datetime=apt_datetime,
        status=AppointmentStatus.BOOKED.value
    )
    db.session.add(appointment)
    db.session.commit()

    logger.info("Appointment booked", extra={'request_id': idempotency_key, 'appointment_id': appointment.id})
    return jsonify(appointment.to_dict()), 201

if __name__ == '__main__':
    init_db()
    app.run(debug=True)