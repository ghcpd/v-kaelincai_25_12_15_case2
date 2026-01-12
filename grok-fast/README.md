# Appointment Booking System (Greenfield Replacement)

## Overview

This is a greenfield replacement for the legacy student ranking system, redesigned as a robust appointment booking system with proper state management, idempotency, and fault tolerance.

## Architecture

- **Framework**: Flask with SQLAlchemy
- **State Machine**: init → booked/failed/cancelled
- **Idempotency**: Request ID based
- **Fault Tolerance**: Retry with backoff, circuit breaker, Saga compensation

## API

### POST /appointments
Book an appointment.

Request:
```json
{
  "idempotency_key": "unique-key",
  "user_id": "user123",
  "datetime": "2025-12-15T10:00:00Z"
}
```

Response:
```json
{
  "appointment_id": "apt123",
  "status": "booked",
  "datetime": "2025-12-15T10:00:00Z"
}
```

## Setup

1. Run setup.sh to install dependencies
2. Run run_tests.sh to execute tests

## Migration

From legacy ranking system: No direct migration needed as domains differ. Use data migration scripts if required.