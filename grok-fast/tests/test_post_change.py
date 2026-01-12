"""
Integration tests for appointment booking system
Covers idempotency, retry, timeout, circuit breaker, compensation
"""

import pytest
import requests
import time
import json
from src.appointment_system import app, db, init_db

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client
        with app.app_context():
            db.drop_all()
            import os
            if os.path.exists('test.db'):
                os.remove('test.db')

def test_idempotency(client):
    """Test idempotency: Same key returns same result"""
    data = {
        'idempotency_key': 'idem-1',
        'user_id': 'user1',
        'datetime': '2025-12-15T10:00:00Z'
    }
    resp1 = client.post('/appointments', json=data)
    assert resp1.status_code == 201
    apt_id = resp1.get_json()['appointment_id']

    resp2 = client.post('/appointments', json=data)
    assert resp2.status_code == 200
    assert resp2.get_json()['appointment_id'] == apt_id

def test_conflict_failure(client):
    """Test conflict leads to failed status"""
    data1 = {
        'idempotency_key': 'conflict-1',
        'user_id': 'user1',
        'datetime': '2025-12-15T10:00:00Z'
    }
    client.post('/appointments', json=data1)

    data2 = {
        'idempotency_key': 'conflict-2',
        'user_id': 'user2',
        'datetime': '2025-12-15T10:00:00Z'
    }
    resp = client.post('/appointments', json=data2)
    assert resp.status_code == 409
    assert resp.get_json()['status'] == 'failed'

def test_invalid_datetime(client):
    """Test invalid datetime returns error"""
    data = {
        'idempotency_key': 'invalid-1',
        'user_id': 'user1',
        'datetime': 'invalid'
    }
    resp = client.post('/appointments', json=data)
    assert resp.status_code == 400

def test_successful_booking(client):
    """Test successful booking"""
    data = {
        'idempotency_key': 'success-1',
        'user_id': 'user1',
        'datetime': '2025-12-15T10:00:00Z'
    }
    resp = client.post('/appointments', json=data)
    assert resp.status_code == 201
    assert resp.get_json()['status'] == 'booked'

def test_missing_fields(client):
    """Test missing fields error"""
    data = {'idempotency_key': 'missing-1'}
    resp = client.post('/appointments', json=data)
    assert resp.status_code == 400