# Greenfield Replacement: Student Ranking Service — Analysis & Design

Project: issue_project (legacy) → Greenfield: oswe-mini-uiberry-1210/src (ranking_v2)

Author: Senior architecture & delivery engineer
Date: 2025-12-15

SUMMARY
1) Quick finding: Legacy code used array indices as ranks which produced incorrect results when scores tie. The new service implements dense ranking and hardened runtime features (idempotency, outbox, retry/backoff, circuit-breaker, compensation and reconciliation).
2) Delivered: runnable scaffold (src/, mocks/, tests/, data/, logs/, results/), integration tests (≥5 scenarios), one-click scripts, structured logging, and a migration/rollout plan.

-----------------------------------------------------------------
0. Clarifications & Assumptions (Missing data checklist)

Missing data / assumptions (needs confirmation):

- Production traffic profile (QPS, burst patterns). ASSUMED: low-volume batch ranking requests (<=100 reqs/min) for this exercise.
- Data size per request (max students per request). ASSUMED: <= 10k students in worst-case; current in-memory implementation OK for PoC but DB required for scale.
- Persistence layer semantics: legacy uses in-memory lists. ASSUMED: Replace with transactional DB (e.g., Postgres) in prod.
- Downstream consumers & delivery guarantees (at-most-once / at-least-once). ASSUMED: At-least-once delivery required; outbox ensures eventual delivery.
- SLOs (latency, availability). ASSUMED target: p95 latency < 500ms, availability 99.9%.

Collection checklist (what to collect to reduce risk):

- Codebase: full repo, versions, and dependencies (collected).
- Tests & CI logs: pytest runs and failures (available in tests/).
- Reproduction logs: failing test traces (KNOWN_ISSUE.md and README provided reproduction).
- Traffic & access patterns: sample request logs, peak QPS.
- DB snapshots: schema and sample data for reconciliation testing.
- Monitoring: CPU, memory, error rates, request latency histograms.
- Downstream system behavior: error modes, timeouts, SLA for notifier.

-----------------------------------------------------------------
1. Background Reconstruction (inferred from visible assets)

Business context (inferred):
- A school grade management system computes rankings for students (used by honor roll, scholarships, reports).
- Core flow: ingest list of students & scores → compute ranking → persist and notify downstream systems.
- Boundary: ranking algorithm is the core; external dependencies include event/notifier systems.

Dependencies & constraints (inferred):
- Lightweight Python app, pytest for verification.
- Legacy code lacks robust production features: idempotency, retries, outbox, circuit-breaker.

Uncertainties:
- Expected ranking method exactly: README indicates dense ranking (ties same rank, next rank increments by 1) but KNOWN_ISSUE had overlapping descriptions—need product confirmation.
- Downstream consumer contract and durability/ordering requirements.

-----------------------------------------------------------------
2. Current-State Scan & Root-Cause Analysis

High-level issues by category

| Category | Symptom | Likely Root Cause | Evidence / Needed Evidence |
|---|---|---|---|
| Functionality | Incorrect ranks for tied scores (e.g., 95,95,90 → 1,2,3) | Ranking uses index+1 rather than tie-aware logic | README, KNOWN_ISSUE.md, src/ranking_system.py (index used) |
| Reliability | No retry/backoff/outbox; downstream failures may drop events | No transactional outbox; no publisher retry | No publisher code; absence of outbox in repo |
| Performance | N/A for small inputs; algorithm is O(n log n) | Sorting approach is fine; but no scaling design for very large cohorts | Need request size profile and latency traces |
| Maintainability | Monolithic script-style code, limited separation of concerns | Single-file implementation without clear boundary or interfaces | src/ranking_system.py, small codebase |
| Security | No secrets handling but minimal exposure; no PII masking in logs | Structured logs absent; sensitive fields not masked | Code prints names in plain text; no logging scheme |
| Cost | Not applicable for PoC; in prod, in-memory persistence costly/ephemeral | No external DB, no event store | Need deployment and retention requirements |

High-priority issue (functional tie bug)

- Hypothesis chain: index-based assignment → ties increment index → ranks become ordinal instead of dense → downstream stakeholders see unfair ranks → business impact (scholarships, trust).
- Validation: run failing pytest cases (tests/test_ranking.py) or provided reproducer (README). Confirmed by running existing tests.
- Fix path: update calculate_rankings to dense ranking (three suggested approaches in KNOWN_ISSUE.md). Implemented Approach: increment rank on score change (dense ranking). Tests must be updated/added and run.

-----------------------------------------------------------------
3. Greenfield Replacement: Target State & Design

Design goals:

- Correctness: dense ranking semantics for ties.
- Resilience: idempotency, retry + exponential backoff, circuit-breaker, outbox for at-least-once delivery.
- Observability: structured logs, request/appointment IDs, metrics for publish attempts & reconciliations.
- Testability: reproducible integration tests that simulate real failure modes.

Service decomposition (small, pragmatic for PoC):

- RankingService (core): compute rankings, persist results, manage outbox, perform reconciliation.
- Publisher (pluggable): external notifier interface (mockable in tests). Wrap with CircuitBreaker.
- Reconciler (control plane): background or on-demand job to flush outbox (read/write cutover strategy uses outbox).

Unified state machine (request lifecycle mapped to appointment-like states)

Lifecycle states (mapped to appointment semantics):

- INIT (received): request accepted, validation passed, persisted as pending
- IN_PROGRESS (processing): compute rankings, append event to outbox
- PUBLISHED / SUCCESS (completed): event published to downstream, status=completed
- FAILED (transient/permanent): publish attempts exhausted or circuit open → compensation executed
- RECONCILING (replay): outbox events retried until success

Crash points (observed / anticipated): uncaught exceptions during compute, timeout during publish, lack of idempotency on replay.

State transitions (ASCII):

     Receive
       |
      INIT
       |
  compute rankings
       |
    IN_PROGRESS
       | append outbox
       v
   try publish ---[success]---> COMPLETED
       |
     [fail]
       v
    FAILED  <--(compensation may rollback DB)
       |
    reconcile (admin or scheduler)
       v
    IN_PROGRESS (retry) ...

Idempotency, retries, timeouts, circuit-breaker, compensation

- Idempotency key: request_id (string). Producer must supply unique request_id; server should generate if missing. Idempotency prevents duplicate effects for replay.
- Retry + backoff: exponential backoff with jitter recommended. Tests use small deterministic backoff for speed.
- Circuit-breaker: protects publisher from overload; open after N consecutive failures; half-open tests to close.
- Compensation / Saga: if publish permanently fails, perform compensating action (e.g., rollback transient DB write) and retain event in outbox for manual or scheduled reconciliation.
- Transactional outbox: write DB + outbox in same transaction (PoC uses in-memory atomic append; in prod use DB + durable queue/outbox table).

Architecture & data flow (prose + ASCII)

1) Client -> Ranking API (ingest request)
2) API validates, computes dense rankings, writes result row and outbox event (single DB transaction)
3) Publisher worker/loop reads outbox rows and publishes to downstream (with retry & CB)
4) On permanent publish failure, sink remains in outbox for reconciliation; a compensation step may be used depending on business choice

ASCII Diagram

Client --> Ranking API --> [DB] {results row + outbox}
                         |
                         v
                     Publisher (retry/backoff + CB)
                         |
                         v
                    Downstream Notifier

Key interfaces / Schemas / Validation

Request (JSON):

{
  "request_id": "string (optional, alpha-num - recommend UUID)",
  "students": [
    {"name": "string (1..256)", "score": number (0..100)}
  ]
}

Constraints:
- request_id: required for idempotency in prod, pattern ^[A-Za-z0-9_\-]+$
- students: minItems=1, each name length 1..256, score number between 0 and 100

Event (outbox payload):

{
  "type": "ranking.computed",
  "request_id": "...",
  "payload": [{"name":"...","score":...,"rank":...}, ...]
}

See Shared/schemas.json for machine-readable schema.

Migration and parallel run plan

Goal: Greenfield rollout without breaking downstream consumers.

Option A — Shadow deploy + dual-write (recommended for low risk):

1) Deploy new RankingService with read-only shadow mode. Consumer traffic still served by legacy.
2) Inject shadow traffic: send live requests to new system (no effect on production consumers) and compare outputs to legacy in staging.
3) Run backfill: for historical requests, replay to new system and record diffs.
4) When parity confirmed (correctness + performance), perform incremental cutover: route a small % of traffic (5%) to new service with monitoring and quick rollback.
5) Validate metrics (p50/p95, error rates, idempotency) and gradually increase traffic until 100%.

Dual-write & read-after-write concerns:

- Dual-write must be idempotent; use request_id to avoid double processing.
- For reads, choose canonical source (prefer new service DB after cutover) or use read-for-write strategy during transition.

Rollback paths:

- If regressions found, redirect traffic back to legacy, disable new system, and reconcile any events produced by new system via outbox replay.

-----------------------------------------------------------------
4. Testing & Acceptance (Dynamically generated from risk points)

Test matrix: at least 5 integration tests derived from crash points/risks

1) Healthy path (baseline correctness)
- Target issue: ranking correctness for non-tied inputs
- Preconditions/Data: simple_no_ties case in data/test_data.json
- Steps: call process_request, assert returned rankings match expected_postchange.json
- Expected outcome: status=ok, rankings match expected, outbox flushed
- Observability assertions: log contains request_id + publish_success; metrics publish_attempts==1

2) Idempotency (replay protection)
- Target issue: duplicate processing on replay
- Preconditions: request_id provided (two_tied_first), publisher succeeds
- Steps: send same request twice
- Expected outcome: first call computes and publishes; second call returns idempotent=True and does not re-publish duplicate events
- Observability: log entry idempotent_replay with request_id; processed store contains single entry

3) Retry with backoff (transient downstream failures)
- Target issue: transient failures should be retried and succeed
- Preconditions: publisher configured to fail N times then succeed
- Steps: process request; confirm service retried and eventually published
- Expected outcome: status=ok, metrics publish_retries >= N, outbox empty
- Observability: logs show publish_attempt_failed entries + publish_success; metric retry count logged

4) Timeout/circuit-breaker (protect downstream)
- Target issue: downstream persistent failures should open the circuit and fail fast
- Preconditions: publisher always fails
- Steps: send requests until circuit opens; next request should fail fast
- Expected outcome: circuit state == open; subsequent requests fail fast without long waits
- Observability: logs show circuit_open and compensation_performed events

5) Compensation / Outbox & Reconciliation (eventual delivery)
- Target issue: permanent failure does not lose data; events stay in outbox and can be reconciled
- Preconditions: publisher fails; later publisher recovers
- Steps: trigger publish failure → verify outbox contains events → configure publisher to succeed → run reconcile_outbox()
- Expected outcome: reconcile_outbox returns reconciled>0 and outbox empty
- Observability: logs show reconcile_success entries and metrics.reconciled increments

Acceptance criteria & SLOs (examples)

- Functional correctness: all ranking scenarios in data/expected_postchange.json must match (automated tests). Given: a request with ties; When: processed; Then: ranks follow dense ranking rules.
- Idempotency: replaying same request_id produces no duplicate side-effects (SLO: 100% idempotent within same window).
- Availability/Latency: p95 latency for ranking calculation + publishing (in synthetic test harness) <= 500ms.
- Reliability: publisher success rate >= 99% under normal workload; reconciliation success rate > 99% within 1 hour.

-----------------------------------------------------------------
5. Observability & Logging

Structured logging schema (one-line JSON entry):

{
  "ts": 1670000000000,
  "msg": "publish_success",
  "request_id": "case-2",
  "event": "ranking.computed",
  "attempts": 2,
  "sensitive_masked": true
}

Requirements:
- Every entry must include ts (ms), request_id, msg, and optional error field.
- Mask PII: student names should be masked in logs (e.g., A**** for Alice) unless debug mode explicitly enabled.

-----------------------------------------------------------------
6. One-click test fixture & artifacts

- run_tests.sh: runs pytest and emits artifacts into results/ and logs/
- Artifacts produced by CI run:
  - results/results_post.json (test summary & outputs)
  - results/aggregated_metrics.json (retry counts, reconciled counts)
  - logs/log_post.txt (structured logs)

How to run locally:

1) bash ./setup.sh
2) bash ./run_tests.sh

Or run individual modules for debugging:

python -m src.ranking_v2 --reconcile

-----------------------------------------------------------------
7. Rollout Guidance

1) Start with shadow/dual-write mode and run comparison over a sample window (1 day) to ensure parity.
2) Monitor key metrics (rank diffs by request, p50/p95 latency, publish success, reconciliation rates).
3) Gradual traffic ramp: 5% → 25% → 50% → 100% with automated rollback on anomaly thresholds (e.g., rank-diff > 0.01% or errors > 0.1%).

Rollback steps:

- Re-route traffic to legacy, keep new system running in read-only to collect telemetry.
- Reconcile any produced events if new system produced side-effects.

-----------------------------------------------------------------
8. Next steps / Deliverables

- Confirm ambiguous business rule: dense ranking vs standard competition ranking. (Assumption: dense ranking)
- Provide production-grade persistence (Postgres + outbox table) and move publisher into its own worker process.
- Add metrics (Prometheus) and tracing (request_id propagation) for production observability.
- Add performance tests for 10k+ students per request and scale guidance.

Appendices
- Shared/schemas.json — machine-readable schema exists in Shared/
- Tests — pytest suite under tests/ (integration scenarios)
- One-click scripts — run_tests.sh and run_all.sh
