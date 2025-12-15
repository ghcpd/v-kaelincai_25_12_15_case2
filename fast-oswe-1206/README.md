# Fast OSWE 1206 - Greenfield Ranking Service (v2)

This repository contains a **greenfield replacement** for the legacy student ranking system in the `issue_project` sample. The goal is to demonstrate how a clean, testable, idempotent, and observable service can be built to replace a buggy legacy implementation.

## Requirements
- Python 3.8+ (we use 3.12-ish for the workspace)
- `pip` to install dependencies

## Quick Start
```
# Install dependencies
pip install -r requirements.txt

# Run unit/integration tests
pytest -q

# Run the service example
python src\ranking_v2.py
```

## Files & Structure
```
fast-oswe-1206/
├── src/                # v2 runtime code
│   └── ranking_v2.py
├── tests/              # integration tests
│   └── test_ranking_v2.py
├── data/               # test dataset
│   └── test_data.json
├── mocks/              # API mocks / stubs (future placeholders)
├── logs/               # logs collected during runs (run-time)
├── results/            # results of automation runs
├── requirements.txt
├── setup.sh            # install deps (helper)
├── run_tests.sh        # run test harness
├── run_all.sh          # run whole flow (prep + run + compare)
├── compare_report.md   # expected diffs & SLOs
└── README.md           # this file
```

## How to use
- `setup.sh` -> install packages.
- `run_tests.sh` -> run `pytest` for tests in `tests/`.
- `run_all.sh` -> present a linear run that runs setup, tests, and prints an artifacts summary.

## Notes
- The service uses deterministic ordering (score desc, name asc) so results are repeatable.
- idempotency_key is allowed for logging and tracing, not strictly required for the service logic.
- Structured logging is used; tests include a placeholder for log capture. In a real system you'd capture and assert on logs.

# Next steps
- Add proper mocks for downstream APIs if the ranking service integrates with e.g. notification/email services.
- Add more tests for boundary conditions and error scenarios.
- Add `compare_report.md` that compares legacy vs v2 outputs for canonical scenarios.

