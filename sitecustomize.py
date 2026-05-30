"""Local runtime compatibility hooks for GAWorld development.

This module is imported automatically by Python when the repo root is on
``sys.path``. It is intentionally conservative:

- Patch ``datetime.UTC`` for Python versions before 3.11 so the project can
  still run under the local 3.10 environment used in this workspace.
- Optionally swap in the deterministic mock LLM when
  ``GAWORLD_USE_MOCK_LLM=1`` is set. This is only for local integration
  testing and does not affect normal runs.
"""

from __future__ import annotations

import os


def _patch_datetime_utc() -> None:
    try:
        import datetime as _dt
    except Exception:
        return
    if not hasattr(_dt, "UTC"):
        _dt.UTC = _dt.timezone.utc


def _maybe_install_mock_llm() -> None:
    if os.environ.get("GAWORLD_USE_MOCK_LLM") != "1":
        return
    try:
        import llm_providers
        from tests.fixtures.mock_llm import MockLLM
    except Exception:
        return
    llm_providers.call_llm = MockLLM()  # type: ignore[assignment]


_patch_datetime_utc()
_maybe_install_mock_llm()
