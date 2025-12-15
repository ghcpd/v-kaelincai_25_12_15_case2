#!/usr/bin/env bash
set -euo pipefail

# Install Python dependencies
if command -v python -V >/dev/null 2>&1; then
  PYTHON=python
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  echo "Python not found in PATH" >&2; exit 1
fi

$PYTHON -m pip install --upgrade pip
$PYTHON -m pip install -r requirements.txt

echo "Dependencies installed successfully."
