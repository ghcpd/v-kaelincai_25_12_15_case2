#!/usr/bin/env bash
# Setup script: create venv and install requirements
set -euo pipefail

PYTHON=${PYTHON:-python}

echo "Creating virtual environment .venv (if missing)"
$PYTHON -m venv .venv || true
echo "Activate the venv and run: source .venv/bin/activate  (or .venv\\Scripts\\activate on Windows)"
echo "Installing requirements..."
.venv/bin/pip install --upgrade pip || true
.venv/bin/pip install -r requirements.txt || true

echo "Setup complete. Run ./run_tests.sh to execute integration scenarios."
