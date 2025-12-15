#!/bin/bash
# setup.sh - Initialize v2 ranking service environment

set -e

echo "Setting up Ranking Service v2 environment..."

# Create virtual environment (optional, comment out if not needed)
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment (for bash/zsh)
# source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

echo "Setup complete! Ready to run tests."
echo ""
echo "Next steps:"
echo "  1. Run tests: ./run_tests.sh"
echo "  2. Run mock API: ./run_mock_api.sh"
echo "  3. Compare v1 vs v2: ./run_comparison.sh"
