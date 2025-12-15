#!/bin/bash
# run_tests.sh - Execute all integration tests

set -e

echo "=========================================="
echo "Ranking Service v2 - Integration Tests"
echo "=========================================="
echo ""

cd "$(dirname "$0")"

echo "Running pytest with verbose output..."
echo ""

python -m pytest tests/ -v --tb=short -s | tee logs/test_output_v2.log

echo ""
echo "=========================================="
echo "Test execution complete!"
echo "Results: logs/test_output_v2.log"
echo "=========================================="
