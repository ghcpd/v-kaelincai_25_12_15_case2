Student Ranking Service — Greenfield Replacement

This repository is a greenfield replacement for a legacy Student Ranking System (legacy project located in ../issue_project).
It demonstrates a resilient design with idempotency, retry/backoff, circuit-breaker, outbox (transactional event publish), compensation (simple saga), structured logging, and repeatable integration tests.

Quick start (Windows / Git Bash / WSL):

1) Create a virtualenv and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows PowerShell
pip install -r requirements.txt
```

2) Run all tests (writes results/ and logs/)

```bash
./run_tests.sh
```

3) Run the reconciliation demo

```bash
python -m src.ranking_v2 --reconcile
```

Project layout (created as part of deliverable):

src/               # v2 runtime: ranking service, circuit breaker, utils
mocks/             # controllable external notifier mock (to simulate failures/timeouts)
data/              # test input cases and expected outputs
tests/             # pytest integration tests (≥5 scenarios)
logs/              # structured logs produced by tests and runtime
results/           # test run artifacts: results_post.json, aggregated_metrics.json
requirements.txt
setup.sh
run_tests.sh
run_all.sh
compare_report.md  # automated diff + rollout guidance
Shared/            # schemas and examples

See compare_report.md for the analysis summary and rollout recommendations.
