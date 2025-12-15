#!/usr/bin/env bash
set -euo pipefail
python -m pytest --json-report --json-report-file=results/results_post.json -q
