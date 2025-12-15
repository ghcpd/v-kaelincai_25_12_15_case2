#!/usr/bin/env bash
set -e
./setup.sh
# start calendar mock in background
python -m issue_project.mocks.calendar_mock &
CAL_PID=$!
sleep 0.5
./run_tests.sh
kill $CAL_PID || true
