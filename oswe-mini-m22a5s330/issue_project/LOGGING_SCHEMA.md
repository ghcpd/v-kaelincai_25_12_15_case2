Structured Logging Schema

Fields (all entries are JSON objects):
- timestamp: ISO8601 string (required)
- level: string (DEBUG|INFO|WARN|ERROR) (required)
- service: string (e.g., appointment_service) (required)
- request_id: uuid (required for user flows)
- appointment_id: uuid (if applicable)
- idempotency_key: string (if applicable)
- user_id: uuid (if applicable)
- msg: free text message
- duration_ms: numeric (if applicable)
- sensitive_masked: boolean (true)
- error: {type, message, stack?} (if applicable)

Masking rules:
- PII (names, emails, phone numbers) must be removed or replaced with hashed tokens.
- Tokens and secrets must never be logged.

Example log entry:
{
  "timestamp": "2025-12-15T13:45:01.123Z",
  "level": "INFO",
  "service": "appointment_service",
  "request_id": "d9f2b7c6-....",
  "appointment_id": "a1b2c3d4-...",
  "idempotency_key": "key-1",
  "user_id": "user1",
  "msg": "appointment created",
  "duration_ms": 123,
  "sensitive_masked": true
}
