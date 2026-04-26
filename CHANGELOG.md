# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] — 2026-04 — S1 + S2 refactor

### Added

- **Project tooling**
  - `pyproject.toml` with ruff / black / mypy / pytest / coverage configuration.
  - `.github/workflows/ci.yml` — lint + format check + mypy (advisory) + pytest with coverage on Python 3.11 and 3.12.
  - `requirements-dev.txt` for development extras (`pytest`, `pytest-cov`, `ruff`, `black`, `mypy`).
  - `.env.example` documenting required environment variables (LLM API keys, log level, config overrides).

- **`gaworld/` package** as the new home for cross-cutting concerns:
  - `gaworld.logging_setup` — central rotating logger with structured context (`agent_id`, `day`, `stage`, `provider`, `task`).
  - `gaworld.env_loader` — zero-dependency `.env` loader.
  - `gaworld.config` — typed `SimulationConfig` / `LLMConfig` / `PathsConfig` dataclasses with `from_legacy(CONFIG)` factory; pydantic-free.
  - `gaworld.core.agent` — `Agent` dataclass adapter that owns the legacy ``dict`` agent layout while exposing typed accessors (`a.id`, `a.state`, `a.need(...)`).
  - `gaworld.io.web_scrape` — extracted HTML / news content extraction (used to live inline in the main simulator).
  - `gaworld.llm` — re-exports the existing provider router; provides a stable import path for new code.

- **New tests**
  - `tests/test_gaworld_core_agent.py`
  - `tests/test_gaworld_config.py`
  - `tests/test_gaworld_io_web_scrape.py`

### Changed

- **`llm_providers.py`**
  - Replaced the private `requests.models.complexjson.loads(...)` API with stdlib `json.loads`.
  - Added bounded exponential-backoff retry around all three providers for transient errors (timeouts, connection errors, 408/425/429/5xx).
  - Every `call_llm` invocation is now logged with provider / task / agent / prompt size / latency / outcome under the `gaworld.llm` logger.

- **Bare `except Exception` clean-up** — collapsed silent broad catches to specific exception types in:
  - `dashboard_server.py` (HTTP 500 boundary still broad, but now `_LOG.exception` traces are emitted)
  - `distributed_comm.py`
  - `environment.py`
  - `extensibility.py` (third-party hook trust boundary, now logged)
  - `human_realism.py`
  - `generative_city_sim.py` (8 callsites)

- **`generative_city_sim.py`** now imports HTML helpers (`_strip_html`, `_extract_title`, `_normalize_text`, `_extract_meta_content`, `_extract_news_main_content`, `fetch_news_excerpt`, etc.) from `gaworld.io.web_scrape`. The legacy regex bodies were removed; the public names remain available as module-level aliases.

- **`requirements.txt`** — pinned with conservative `>= … , < …` ranges instead of unpinned `pandas / numpy / requests / matplotlib / networkx`.

### Notes

- **Python ≥ 3.11** is now required (the existing `from datetime import UTC` import in `simulation_visualizer.py` already required it; the build metadata now declares it).
- The HTML extraction port silently fixes a pair of double-escape bugs in the original regex (`</\\1>` and `\\s+`); behaviour on real HTML pages is unchanged or improved.
- All 18 sandbox-runnable legacy tests continue to pass; coverage of new code is tracked by 19 new tests across the three `gaworld/` subpackages.
- The full migration plan (S3 — concurrency, S4 — research-grade observability) is documented in `GAWorld_改进建议.docx`.

### Migration tips for downstream code

```python
# Old:                                    # New (preferred):
from generative_city_sim import (         from gaworld.io.web_scrape import (
    _strip_html, _extract_title,              strip_html, extract_title,
    fetch_news_excerpt,                       fetch_news_excerpt,
)                                         )

# Old (legacy dict):                      # New (typed adapter, same dict under the hood):
agent["state"]["energy"]                  agent.state["energy"]
                                          agent.need("energy", default=0.5)

# Old:                                    # New (typed view of CONFIG):
from config import CONFIG                 from gaworld.config import load_simulation_config
sim_days = CONFIG["sim_days"]             cfg = load_simulation_config()
                                          sim_days = cfg.sim_days
```
