"""Lightweight ``.env`` loader (no python-dotenv dependency).

Loads ``KEY=value`` lines from a file into ``os.environ`` without
overriding values that are already set. Quoted values and comments are
supported; complex shell expansion intentionally is not.
"""

from __future__ import annotations

import os
from typing import Iterable


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load_env_file(path: str = ".env", *, override: bool = False) -> dict[str, str]:
    """Parse ``path`` and merge it into :data:`os.environ`.

    Returns a dict of values that were applied (i.e. non-existing or
    overridden). Missing files are silently ignored — this lets the
    function be called eagerly at import time.
    """
    if not path or not os.path.exists(path):
        return {}
    applied: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export ") :]
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = _strip_quotes(value.strip())
                if not key:
                    continue
                if not override and key in os.environ:
                    continue
                os.environ[key] = value
                applied[key] = value
    except OSError:
        return applied
    return applied


def load_default_env_files(paths: Iterable[str] = (".env",)) -> dict[str, str]:
    """Load a sequence of env files, returning the merged applied dict."""
    merged: dict[str, str] = {}
    for path in paths:
        merged.update(load_env_file(path))
    return merged
