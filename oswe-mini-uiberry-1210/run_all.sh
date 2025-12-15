#!/usr/bin/env bash
set -euo pipefail

echo "Run all demos: tests + simple reconciliation demo"
./run_tests.sh

echo "Running reconciliation demo script (python) to show reconciliation behavior"
python -m src.ranking_v2 --reconcile || true

echo "All done. See results/ and logs/"
