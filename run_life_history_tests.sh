#!/bin/bash
# Run Life-History Agent tests
#
# IMPORTANT: Use the Python interpreter that has pytest installed.
# If "python3 -m pytest" fails, try:
#   /home/glf/miniconda3/bin/python -m pytest tests/test_profile_context_diversity.py -v
#
# To install pytest in the current environment:
#   pip install pytest
#
# This project uses pytest. The test file is:
#   tests/test_profile_context_diversity.py

set -e

PYTEST_CMD="${1:-python -m pytest tests/test_profile_context_diversity.py -v}"

echo "Running: $PYTEST_CMD"
eval "$PYTEST_CMD"
