# OSWE Mini Prime — Greenfield Replacement Prototype

## Overview
This repository contains a small prototype for a greenfield replacement of an appointment scheduling subsystem. It demonstrates: idempotency, retry+backoff, timeout behavior, outbox pattern (simulated), structured logging, and an integration test suite capturing crash points.

## Quickstart
1. Create a virtualenv and install deps:
   python -m venv .venv && .\.venv\Scripts\activate && pip install -r requirements.txt

2. Run (Linux/WSL/macOS):
   ./run_all.sh

3. Or run services individually (Windows PowerShell):
   uvicorn mocks.legacy_mock:app --port 8001
   uvicorn src.app:app --port 8000
   python -m pytest --json-report --json-report-file=results/results_post.json -q

## Files of interest
- `src/` — service implementation (idempotency & outbox simulation)
- `mocks/` — legacy service behaviors (immediate/pending/delayed/fail)
- `tests/` — pytest-based integration tests (>=5 cases)
- `data/test_data.json` — canonical cases
- `run_tests.sh`, `run_all.sh` — one-click test runner
- `results/` — test artifacts

## Structured logging
All logs include `request_id` or `appointment_id`. Sensitive fields (ssn) are masked by default.

## Next steps
- Expand outbox persistence and delivery
- Add circuit-breaker & metrics (Prometheus)
- Add CI job and Canary rollout automation
