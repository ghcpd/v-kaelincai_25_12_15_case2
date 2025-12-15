#!/usr/bin/env bash
set -euo pipefail

echo "Running pytest integration suite..."
pytest -q

echo "Tests finished. Artifacts placed in results/ and logs/."
ls -lah results || true
ls -lah logs || true
