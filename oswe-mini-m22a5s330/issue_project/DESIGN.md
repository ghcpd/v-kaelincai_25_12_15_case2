Design Document — Greenfield Replacement for Legacy Appointment System

1. Clarifications & Missing Data
1.1 Missing data / assumptions
- No DB schema or sample data beyond students.json (assumed to be unrelated).
- No traffic profiles or SLAs available; assume modest traffic (100 TPS peak) and SLOs: p99 latency < 500ms for core flows.
- No exact external API contracts (calendar, notifications); we assume a calendar API that confirms slot booking.
- Authentication and tenancy model unknown—assume single-tenant for MVP and token-based auth for external APIs.

Collection checklist (prioritized)
- Codebase: full source, tests, build/run scripts.
- Logs: recent application logs, structured events, correlation IDs.
- Traffic: request traces, latency percentiles, error budget.
- DB snapshots: schema, sample records, indexes, sizes.
- Config: timeouts, retry settings, circuit-breaker thresholds.
- Secrets: tokens and access patterns for external services.

2. Background Reconstruction (inferred)
- Legacy system schedules and confirms appointments via an external calendar service and persists appointments in a DB.
- Core flow: receive appointment request -> validate -> call calendar -> persist appointment -> send notifications.
- Boundaries: API frontend, scheduler/orchestrator, DB storage, external calendar, notification service.
- Uncertainties: transactional guarantees across external calendar and DB; idempotency keys usage; existing retry and backoff behaviors.

3. Current-State Scan & Root-Cause Analysis
Summary table (Category | Symptom | Likely Root Cause | Evidence / Needed Evidence)

- Functionality | Duplicate appointments / non-idempotent retries | Missing idempotency keys and poor request dedupe | Need logs with request IDs; confirm DB unique constraints
- Performance | High tail latency / timeouts | Blocking sync calls to slow external calendar; no timeouts or bounded retries | Trace samples; p95/p99 latency metrics
- Reliability | Inconsistent state (calendar booked, DB not persisted) | No transactional outbox; two-phase commit not used | Check for orphaned bookings between calendar and DB
- Security | Sensitive fields in logs or missing auth | Unstructured logs contain PII; tokens reused | Log samples & audit trails
- Maintainability | Monolithic code, poor test coverage | Lack of modular services and integration tests | Repo structure and tests coverage metrics
- Cost | Excessive retries causing extra external calls | No circuit breaker or adaptive backoff | Metrics on external calls per logical request

High-priority issue example: Inconsistent state between external calendar and DB
- Hypothesis chain: External calendar call succeeds -> DB write fails -> no compensation/outbox -> booking orphaned in external system -> customer confusion
- Validation: Correlate calendar confirmation IDs with DB appointments. Check for calendar entries without DB records (within a time window).
- Fix path: Add transactional outbox with reliable publisher; use compensation saga to cancel external booking on failure; add audit log for reconciliation.

4. New System Design (Greenfield Replacement)
4.1 Target state and design principles
- Service decomposition: API Gateway -> Appointment Service (orchestrator) -> Calendar Adapter -> Notification Service -> Persistent Store + Outbox
- Each service owns a bounded context: Appointment Service owns appointment lifecycle and reconciliation; Calendar Adapter implements retries/timeouts and idempotency to external calendar.
- Single source of truth: appointment DB; outbox table for eventual side-effects; reconcile worker to ensure consistency.
- Reliability patterns: idempotency keys on create; bounded retries with exponential backoff; circuit breaker (short-circuit after threshold); request timeouts; compensation sagas for partial failure.

4.2 Architecture & Data Flow (ASCII)

Client -> API Gateway -> Appointment Service -> (persist draft) -> Calendar Adapter -> (calendar confirmed) -> persist final + outbox -> Notification worker
                                     |                                   ^
                                     v                                   |
                                Reconciliation worker <------------------+

4.3 Key interfaces / Schemas
- CreateAppointmentRequest { idempotency_key: string (required, 36 chars), user_id: uuid, start_time: iso8601, duration_minutes: int(1-480), metadata: object }
- CreateAppointmentResponse { appointment_id: uuid, status: enum(draft|confirmed|failed), calendar_id?: string }
- Validation: start_time in future, duration between 1 and 480, idempotency_key required and unique per user for window of 24h.

4.4 Idempotency and retries
- Writes: appointments table has unique constraint on (user_id, start_time, idempotency_key).
- External calls: Calendar Adapter attaches same idempotency key to outgoing requests.
- Retries: use exponential backoff with jitter, max attempts=5, total timeout per external op 10s.
- Circuit breaker: Sliding window of failures (5 failures in 60s) trips circuit to prevent cascading failures.
- Compensation: Saga for CreateAppointment: if DB commit fails after calendar confirmed, schedule a compensating CancelCalendarBooking via outbox.

4.5 Migration & Parallel run
- Parallel run via shadow traffic to v2: API Gateway splits traffic (feature flag) and routes a copy of v1 traffic to v2 (non-intrusive shadow write to calendar only after DB success in v2).
- Backfill: Reconciliation worker reads legacy DB exports and idempotently writes to v2 appointment store via Create API.
- Cutover path: Start with read-only queries from v2, then re-route writes to v2 with dual-write and background reconciliation, then switch reads.

5. Testing & Acceptance
5.1 Integration Test Matrix (≥5 tests)
- Test A: Idempotency on create
  - Preconditions: Calendar mock returns success.
  - Steps: send same request payload twice with same idempotency key.
  - Expected: second call returns same appointment_id and no duplicate calendar bookings.
  - Observability: logs show idempotency key found; DB shows single appointment.

- Test B: Retry with backoff when calendar transiently fails
  - Preconditions: Calendar mock fails first 2 times, succeeds on 3rd.
  - Steps: create appointment request.
  - Expected: appointment confirmed, retry count recorded as 3.
  - Observability: metric retry_count==3; logs show backoff timings.

- Test C: Timeout and circuit-breaker behavior
  - Preconditions: Calendar mock responds slowly (> per-call timeout)
  - Steps: repeated requests to trip circuit
  - Expected: after threshold, calls fail fast with circuit open; metric circuit_state=open.
  - Observability: circuit metrics, error counters.

- Test D: Compensation / Saga (calendar success then DB failure)
  - Preconditions: Simulate DB commit failure after confirmation (test injection) -> Calendar booked
  - Steps: create appointment (force DB failure)
  - Expected: compensating cancel scheduled in outbox; reconcile worker invokes cancel and no calendar orphan remains.
  - Observability: outbox record present; cancel API called; audit logs include original request and compensation events.

- Test E: Audit & reconciliation
  - Preconditions: Orphan calendar booking present (calendar has booking not in DB)
  - Steps: run reconciliation worker
  - Expected: reconcile creates DB entry or cancels booking per policy; metrics reconcile.count>0
  - Observability: reconciliation logs and reconciliation report.

5.2 Acceptance criteria (Given-When-Then)
- Given: calendar service is within normal latencies, when creating appointments, then 99% of creations succeed end-to-end within 1s and p99 < 5s with retry/backoff.
- Idempotency: Given same idempotency key, duplicate POST returns same appointment_id and no duplicate external bookings.
- Reliability: Given calendar transient issues (5xx/timeout), system recovers with retries, circuit-breaker opens if persistent failures exceed threshold.

6. Observability and Logging
- Structured logging: { timestamp, level, service, request_id, appointment_id?, idempotency_key?, user_id?, msg, sensitive_masked:true }
- Metrics: request.latency.{p50,p95,p99}, external.calls.count, external.calls.errors, circuit_state, retries.count, outbox.pending
- Traces: trace request through API -> Appointment service -> Calendar adapter -> DB -> outbox

7. One-click Test Fixture
- run_all.sh: setups env, starts mock calendar, runs pytest integration suites, collects results in results/results_post.json and creates compare_report.md

Appendices: scripts, templates and sample JSON payloads included in repo.
