#!/usr/bin/env bash
set -e
pytest -q tests/test_appointment_integration.py --junitxml=results/results_post.xml || true
python -c "import json,xmltodict,sys;print('results written')" || true
