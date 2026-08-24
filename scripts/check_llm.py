#!/usr/bin/env python3
"""Ping the configured LLM without printing secrets."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import CONFIG  # noqa: E402
from llm_providers import LLMRouter  # noqa: E402


def main() -> int:
    routing = CONFIG.get("llm", {}).get("routing", {})
    name = routing.get("default", "")
    providers = CONFIG.get("llm", {}).get("providers", {})
    cfg = providers.get(name) or {}
    key_env = cfg.get("api_key_env", "OPENAI_API_KEY")
    present = bool(os.environ.get(key_env) or os.environ.get("MINIMAX_API_KEY"))
    print(f"provider={name}")
    print(f"type={cfg.get('type')}")
    print(f"model={cfg.get('model')}")
    print(f"base_url={cfg.get('base_url') or cfg.get('url') or ''}")
    print(f"api_key_env={key_env} present={present}")
    if not present and cfg.get("type") != "ollama":
        print("FAIL: API key env is empty. Write GAWorld/.env first.")
        return 2
    router = LLMRouter(CONFIG)
    try:
        reply = router.call("只回复一个字：好", task="interview")
    except Exception as exc:
        resp = getattr(exc, "response", None)
        if resp is not None:
            print(f"FAIL status={resp.status_code}")
            print(f"body={(resp.text or '')[:400]!r}")
        else:
            print(f"FAIL {type(exc).__name__}: {exc}")
        return 1
    preview = (reply or "").replace("\n", " ").strip()[:40]
    print(f"ok chars={len(reply or '')} preview={preview!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
