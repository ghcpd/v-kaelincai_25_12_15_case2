#!/usr/bin/env bash
set -euo pipefail
# Start mock legacy on 8001
uvicorn mocks.legacy_mock:app --port 8001 --host 127.0.0.1 &
PID_LEGACY=$!
# Start appointment service on 8000
uvicorn src.app:app --port 8000 --host 127.0.0.1 &
PID_APP=$!
# wait a moment
sleep 1
# Run tests
./run_tests.sh
RESULT=$?
# collect logs
echo "Result: $RESULT" > results/last_run_status.txt
# cleanup
kill $PID_APP || true
kill $PID_LEGACY || true
exit $RESULT
