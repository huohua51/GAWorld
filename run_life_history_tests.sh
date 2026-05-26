#!/bin/bash
# Run Life-History Agent tests (non-integration only)
#
# Usage:
#   bash run_life_history_tests.sh              # default: conda Python + non-integration tests
#   bash run_life_history_tests.sh python3 -v   # custom Python (non-integration tests still applied)
#
# Defaults:
#   Python: /home/glf/miniconda3/bin/python (has pytest + all dependencies)
#   Tests:  tests/test_profile_context_diversity.py
#   Scope:  -m 'not integration' (excludes live-LLM tests)
#
# Integration tests (require live LLM):
#   /home/glf/miniconda3/bin/python -m pytest tests/test_profile_context_diversity.py::TestPlanActionDiversity -v

set -e

PYTHON="${1:-/home/glf/miniconda3/bin/python}"
PYTEST_FILE="tests/test_profile_context_diversity.py"
PYTEST_ARGS="-m 'not integration'"

CMD="$PYTHON -m pytest $PYTEST_FILE $PYTEST_ARGS -v"
echo "Running: $CMD"
eval "$CMD"
