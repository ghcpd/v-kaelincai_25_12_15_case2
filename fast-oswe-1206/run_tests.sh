#!/usr/bin/env bash
set -euo pipefail

# Run pytest for the fast-oswe-1206 test suite
if command -v pytest >/dev/null 2>&1; then
  pytest -q tests
else
  echo "pytest not found - make sure to run setup.sh first" >&2
  exit 1
fi
