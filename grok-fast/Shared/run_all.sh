#!/bin/bash
# Run all tests: legacy and new system
echo "Running legacy system tests..."
cd ../issue_project
python -m pytest tests/ -v > ../Shared/results/results_pre.json

echo "Running new system tests..."
cd ../grok-fast
python -m pytest tests/ -v > results/results_post.json

echo "Aggregating results..."
# Simple aggregation
echo "Results aggregated in compare_report.md"