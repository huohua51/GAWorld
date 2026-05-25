#!/bin/bash
# Run Life-History Agent tests
#
# Usage:
#   bash run_life_history_tests.sh              # uses default conda Python
#   bash run_life_history_tests.sh python3 -m pytest -v  # custom command
#
# Python interpreter: must have pytest installed.
# Known working interpreter on this server:
#   /home/glf/miniconda3/bin/python
#
# If your default python3 has pytest:
#   python3 -m pytest tests/test_profile_context_diversity.py -v
#
# To install pytest:
#   pip install pytest
#
# Test file:
#   tests/test_profile_context_diversity.py

set -e

PYTHON="${1:-/home/glf/miniconda3/bin/python}"
PYTEST_FILE="tests/test_profile_context_diversity.py"

CMD="$PYTHON -m pytest $PYTEST_FILE -v"
echo "Running: $CMD"
eval "$CMD"
