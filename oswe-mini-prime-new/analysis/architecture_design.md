# Analysis & Greenfield Design

## 1) Clarifications & Missing Data (Assumptions)
- Missing: production traffic traces (qps, p95 latency), DB snapshots, schema of legacy APIs, error logs, SLOs, deployment topology, multi-region requirements.
- Assumptions: Schedule operations are idempotent at business level; typical qps < 50; single primary DB for booking; legacy API may be slow or intermittently failing.

### Collection checklist (code / logs / traffic / DB)
- Code: full repo, dependencies, deployment scripts
- Logs: app logs (structured), gateway logs, legacy logs
- Traffic: request/response traces, top endpoints, p50/p95 latency
- DB snapshots: schema, indexes, hotspots, FK usage
- Monitoring: existing metrics, alert rules
- Test commands: current integration tests and runbooks

## 2) Background reconstruction (inferred)
From available assets: `issue_project` appears to manage student/appointments ranking; the scheduling flow calls a legacy scheduler, confirmation is non-transactional; idempotency is missing and failures leave inconsistent states.

Uncertainties: exact business invariants for scheduling (double-book prevention?), whether legacy provides webhooks for eventual confirmations.

## 3) Current-state scan & Root-cause (summary table)
| Category | Symptom | Likely root cause | Evidence / Needed evidence |
|---|---|---|---|
| Functionality | Appointments stuck in pending | No reliable confirm/compensation or idempotency | DB rows with pending status, missing retry/outbox logs |
| Performance | High variance / timeouts on confirmations | Synchronous blocking calls to legacy without timeouts/retries | p95 requests show long tail, stack traces of waiting calls |
| Reliability | Lost messages on failure | No outbox/guaranteed delivery | Missing events; manual reconciliation required |
| Security | Sensitive fields in logs | Raw logging of PII | Log samples showing ssn or PHI |
| Maintainability | Tight coupling with legacy | No clear isolation boundaries | Code that directly calls legacy without abstraction or fallback |
| Cost | Re-tries causing high egress | Uncontrolled retry loops | Traffic metrics and retry spikes |

High-priority issue (lost confirmations): Hypothesis chain: legacy timeout → synchronous block → no outbox persist → state remains pending → manual recon.
Validation: reproduce with simulated delayed legacy response and observe DB state, logs, missing outbox event.
Fix path: add idempotency keys, transactional outbox, async confirmation with retry/backoff, add compensation saga for failed confirmations.

## 4) Target state & Service decomposition
- API Gateway / Edge
- Appointment Service (stateless app) — handles requests, idempotency, orchestration
- Legacy Adapter Service — encapsulate retries/timeouts/circuit-breaker
- Outbox / Delivery Worker — durable event store + deliverer (exactly-once delivery via at-least-once semantics + idempotency)
- Reconciliation/Batch Worker — periodic audits
- Observability: metrics (requests, p50/p95, retries), structured logs, tracing (request_id)

ASCII flow:
Client -> API Gateway -> Appointment Service -> (persist appointment + outbox write) -> Legacy Adapter -> Legacy
                       ^                                                     |
                       |                                                     v
                 Reconciliation <-------------- Delivery Worker <--- Outbox Store

Key interfaces (JSON example):
AppointmentCreate: {"patient_id": "str","start_time":"ISO8601","duration_minutes":int}
Constraints: duration 15..240; patient_id not empty; start_time in future.

Idempotency: require client X-Idempotency-Key header for create operations; server stores result keyed by key for TTL (24h).
Retries: exponential backoff (base 200ms, max 5s), max attempts configurable.
Circuit breaker: open after N failures within window; fallback to pending + alert.

Compensation: Saga pattern — if confirm fails permanently, mark appointment for human reconciliation and emit compensation event; outbox transactional ensures event persisted before commit.

## 5) Migration & Parallel Run
- Shadow traffic: route percentage of requests to new service in read-only or mirror mode (dual-write) while continuing to read from legacy DB.
- Backfill: replay legacy audit logs to populate canonical state in new system.
- Cutover: read-cutover first: switch reads to new service after sync; finally switch writes.
Rollback path: revert routing; keep dual-write for a period.

## 6) Testing & Acceptance (Derived Tests)
At least 5 repeatable integration tests derived from crash points:
1) Idempotency test | pre: idempotency key set | steps: send same create twice | expected: identical response, no duplicate booking | observe: idempotency store hit + single DB row
2) Retry with backoff | pre: legacy transient failures | steps: legacy returns failure then success | expected: success after retry | observe: retry counts metric >=1
3) Timeout propagation / circuit-breaker | pre: legacy extremely slow | steps: cause repeated timeouts | expected: appointment marked pending/failed, circuit opens | observe: circuit-breaker metrics, alerts
4) Compensation/Saga | pre: confirmation permanently fails | steps: simulate persistent failure | expected: appointment marked for reconciliation + compensation event in outbox | observe: outbox has compensation event
5) Audit/Reconciliation | pre: some pending rows exist | steps: run reconciliation job | expected: reconcile state or emit tickets | observe: reconciliation log entries, metrics

Each test records observability assertions: logs with request_id, retry_count metrics, outbox events.

Acceptance Criteria (example):
- Given: 1000 synthetic requests over 10 minutes; When: new service is under comparable load; Then: p95 latency < 300ms for API, confirmation success >= 99%, retry rate < 0.5% (or defined threshold) and no loss of events (outbox durable).

## 7) One-click test fixture
`run_all.sh` (starts mock & service, runs tests, collects `results/results_post.json`, `logs/log_post.txt`). Tests write JSON report via `pytest-json-report`.

# Structured logging schema
- timestamp, level, service, request_id, appointment_id, trace_id, event, message, masked_fields
- Mask PII fields at ingestion

# Next steps
- Implement durable outbox (DB-backed)
- Add circuit-breaker library and metrics export
- Build migration backfill scripts and runbook
