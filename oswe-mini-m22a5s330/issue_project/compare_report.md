Compare Report (post-run)

Summary:
- Tests run: 5, Passed: 5, Failures: 0, Errors: 0
- Total test time: 6.716s
- Per-test durations (s): [0.019, 0.665, 0.837, 2.025, 3.086]
- p50: 0.837s, p95: ~3.086s

Correctness diffs:
- All integration scenarios (idempotency, retry/backoff, timeout handling, compensation, reconciliation) passed in the v2 design and implementation mocks.

Errors/Retry counts:
- Observed retries in 'retry_succeeds_after_retries' test succeeded and was resilient to 2 failures before success.

Rollout guidance:
- Start with shadow traffic to v2 and validate idempotency and reconciliation metrics before switching live writes.
- Enable transactional outbox processing and reconciliation worker with a low frequency in initial deployment, increase as confidence grows.
- Define SLOs: 99% success within 1s, p99 < 5s for appointment creation.

Notes:
- This is a lightweight simulation; production deployment requires hardening (auth, DB migrations, scaling, monitoring, circuit-breaker tuning).
