"""Tests for the split settings package and legacy config shim."""

from __future__ import annotations

from config import CONFIG as LEGACY_CONFIG
from gaworld.settings import CONFIG as SETTINGS_CONFIG
from gaworld.settings import build_default_config
from gaworld.settings.overrides import deep_update


def test_legacy_config_import_uses_settings_object():
    assert LEGACY_CONFIG is SETTINGS_CONFIG
    assert "llm" in LEGACY_CONFIG
    assert "economy" in LEGACY_CONFIG
    assert "real_work" in LEGACY_CONFIG


def test_default_config_builder_returns_fresh_dicts():
    first = build_default_config()
    second = build_default_config()

    first["agent_ids"].append(999)
    first["llm"]["routing"]["default"] = "changed"

    assert 999 not in second["agent_ids"]
    assert second["llm"]["routing"]["default"] == "minimax"


def test_deep_update_preserves_nested_sections():
    cfg = {"llm": {"routing": {"default": "a", "tasks": {"schedule": "a"}}}}

    deep_update(cfg, {"llm": {"routing": {"default": "b"}}})

    assert cfg["llm"]["routing"]["default"] == "b"
    assert cfg["llm"]["routing"]["tasks"] == {"schedule": "a"}
