# Run tests and collect results (PowerShell)
pytest tests/test_appointment_integration.py --junitxml=results/results_post.xml -q -r a
python scripts/collect_results.py
Write-Host "Wrote results/results_post.json"
