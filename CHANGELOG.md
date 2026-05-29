# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] — 2026-05-01 — Economy + Location + Dynamic Behavior

### Added

- **`dynamic_behavior.py` — dynamic behavior system** (new module, ~550 lines)
  - **InterruptEngine**: priority queue of potential schedule interruptions. Each candidate is scored against the current activity's commitment level (0.95 for exams/surgery down to 0.05 for personal time). Personality-dependent threshold with stochastic acceptance gate.
  - **SpontaneityEngine**: mood-classified urge pools (happy/stressed/tired/bored/anxious/lonely), each with 4 context-aware activities. Time-of-day filtering (no shopping at 23:00), personality scaling (extroverts more social urges, introverts more solitary), duration estimation by activity type.
  - **Need-based interrupts**: hunger (with meal-time bonus), fatigue/energy recovery, time-pressure urgency. Ported and improved from the old `maybe_generate_transient_thought` inline logic.
  - **Inbox/social-message triggers**: detects unread messages and social pings via keyword matching, produces interrupt candidates weighted by social need.
  - **SocialChainResolver**: co-location detection (same node, excluding in-transit agents), relationship-closeness-based encounter probability, three interaction types — invitation (close friends, meal-time aware), brief chat (acquaintances), behaviour contagion (strangers doing interesting things).
  - **EnvironmentResponsePipeline**: event classification (weather/traffic/commercial/news/emergency → sub-types), personality-differentiated response modifiers (cautious +30% weather sensitivity, curious +40% commercial interest), severity-scaled priority.
  - **Event cascade chains**: knock-on effects (rain → taxi queues + slippery roads, storm → transit delays + delivery delays, congestion → possible lateness + mood drop, fire → road closures + building evacuation). Probability-gated secondary interrupts.
  - **Schedule insertion**: insert new activities into `(time, activity)` tuple schedules with resumable support — interrupted activities resume after the insertion's duration if there's room.
  - **`evaluate_step_dynamics()`**: single entry point running all six sub-engines per agent per time-step. Returns final activity, change reason, interrupt details, social encounters, cumulative mood delta, schedule insertion info, candidate count, and cascade events.
  - **`dynamic_transient_thought()`**: bridge function matching the old `maybe_generate_transient_thought` return format while using the new engines internally.
  - 55 unit tests covering commitment levels, interrupt evaluation, spontaneous urges, need-based interrupts, inbox triggers, co-location detection, social encounters, environment responses, cascades, schedule insertion, full pipeline, and bridge API.

- **`generative_city_sim.py`** — dynamic behavior integration
  - Main simulation loop now calls `dynamic_transient_thought()` (when `CONFIG["dynamic_behavior"]["enabled"]` is true) instead of the old `maybe_generate_transient_thought()`, with fallback to the legacy path.
  - If the dynamic system decides on an activity change but the LLM-based `maybe_adjust_activity()` doesn't, the dynamic system's decision is used as a fallback.
  - Mood deltas from the dynamic system are applied to agent state after each step.
  - Schedule insertions from the dynamic system are applied with resumable support.
  - Social encounters are logged at DEBUG level.

- **`config.py`** — new `dynamic_behavior` section with `enabled` flag.

- **`economy_module.py` — realistic personal finance simulation** (major refactor)
  - **Tax & social insurance**: China 7-bracket progressive income tax (3%–45%), monthly exemption 5,000 CNY with configurable special deductions. Social insurance: pension 8%, medical 2%, unemployment 0.5%, housing fund 8% (+ employer match), with base salary floor/cap.
  - **Engel-coefficient spending**: income-indexed consumption curve (food 48% at low income → 15% at high income). Eight categories weighted by income elasticity (necessities 0.5–0.6, luxuries 1.2–1.5). Dynamic savings rate (5%–40%).
  - **Multi-account system**: checking / savings / investment / housing fund. Three portfolio profiles (conservative/moderate/aggressive) based on risk preference. Monthly Gaussian investment returns (deposits ~2.5%, funds ~6%±8%, stocks ~8%±22%). Auto-save excess checking.
  - **Macro-economic cycles**: four-phase cycle (expansion → peak → contraction → trough, 60–180 days each) with income/expense/layoff/raise multipliers. Industry-specific conditions. Daily inflation accumulation.
  - **Shock events**: layoff (income cut 50–85%, recovery 30–90 days), raise/promotion, medical emergency (50–85% SI reimbursement), year-end bonus (13th-month salary).
  - New output files: per-agent ledger CSVs, wealth snapshots, `macro_state.json`.
  - 30 unit tests covering tax calculation, Engel allocation, investment returns, macro cycle transitions, shock events, and full lifecycle integration.

- **`city_map_system.py` — realistic location & transport system** (major refactor)
  - **Transport cost calculation**: per-mode fare structures (bus flat 2 CNY, metro distance-based, taxi base+per-km, car fuel+parking). Rush-hour detection (7:00–9:00, 17:00–19:00) with 1.45× time multiplier and 1.3× taxi surcharge.
  - **Weather-aware mode selection**: weather adjustment weights penalise open-air modes (walk/bike/e-bike) in rain/snow/hot/cold, auto-upgrade to sheltered alternatives (bus/metro/taxi).
  - **Category-based spatial queries**: `nearby_nodes()`, `nodes_by_category()`, `nearest_by_category()`, `resolve_best_location()` replace hardcoded location name lists. Works with any city map.
  - **Activity & job category mapping**: `activity_to_categories()` and `job_to_workplace_categories()` map Chinese/English keywords to location categories (education, medical, commerce, leisure, transit, etc.).
  - **Area price levels**: per-category price multipliers (commerce 1.35×, industry 0.80×, education 0.85×) for spending adjustment.
  - 40 unit tests covering transport cost, rush hour, weather effects, spatial queries, category matching, and travel plan integration.

- **`generative_city_sim.py` — location decision refactor**
  - `_infer_workplace()` and `_infer_home()` now use category-based spatial matching instead of hardcoded location name lists.
  - `resolve_location()` uses `activity_to_categories()` + `resolve_best_location()` for generic map-independent activity resolution.
  - `move_agent()` passes `time_str` and `weather` to `travel_plan()`, returns `cost` and `rush_hour` in travel dict.
  - **Commute memory**: agents track `frequent_places`, `preferred_modes`, and `commute_route` stats; habitual bonus feeds back into location decisions.
  - `daily_travel_cost` accumulator resets at day start.

- **`economy_module.py`** — transport expense now uses real fare from `travel_plan()` when available, falling back to budget-based estimate.

- **`config.py`** — expanded `economy` section with `tax`, `social_insurance`, `spending`, `investment`, `macro`, and `shocks` sub-configurations.

---

## [Previous] — 2026-04 — S1 + S2 refactor

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

### S3 (high-risk items, opt-in)

- **`gaworld.core.runner.parallel_map`** — opt-in concurrency primitive that preserves input order, falls back to a fully serial loop when ``max_workers <= 1``, and re-raises the first task exception. Used by:
  - the **daily routine generation loop** in ``generative_city_sim.run_simulation`` (one LLM call per agent per day; previously the largest serial LLM bottleneck). Behaviour is unchanged unless the user opts in.
- **CONFIG knob ``concurrency.day_routine_workers``** — defaults to ``1`` (serial). Setting it ``> 1`` (and ``concurrency.enabled = true``) parallelises the routine generation. The serial merge phase keeps SQLite + per-agent log writers single-writer.
- **MockLLM fixture** (``tests/fixtures/mock_llm.py``) — deterministic, thread-safe stand-in for ``call_llm``; covers the 20+ task names dispatched by the simulator. Patches both ``llm_providers.call_llm`` and the legacy module binding via ``install()``.
- **End-to-end smoke** (``tests/test_e2e_smoke.py``) — runs ``run_simulation()`` with ``sim_days=1``, two agents, mocked LLM, isolated tempdir, against the seeded fixture data. Asserts the routine + per-step LLM tasks were dispatched and that the per-agent log artefacts were produced. Skips cleanly when ``networkx``/``matplotlib`` are unavailable.
- **New tests** — ``tests/test_gaworld_core_runner.py`` (11), ``tests/test_mock_llm_fixture.py`` (7), ``tests/test_e2e_smoke.py`` (2). 20 new tests bring the total runnable suite from 55 to 74 + 1 skipped.

### S3 (safe items)

- **SQLite WAL** — `memory_store._vector_db_connect()` now applies `PRAGMA journal_mode=WAL` + `synchronous=NORMAL` + `temp_store=MEMORY`. Concurrent agent writes no longer block readers. Failure is logged at WARNING and falls back to default journaling.
- **HTTP guardrails** — new `gaworld.io.http_guard` provides:
  - `HostRateLimiter` (per-host minimum interval + jitter)
  - `UserAgentRotator` (round-robin over a configurable pool, with sensible defaults)
  - `FailureCache` (sliding-window cache keyed on URL × status, with separate TTLs for permanent (401/403/404/410/451), transient (408/425/429/5xx), and other statuses)
  - `GuardedSession` (combines all three on top of `requests.Session`)
- `gaworld.io.web_scrape.fetch_news_excerpt` is now wired through `get_default_session()` so all news fetching honours the guards automatically.
- **LLM cross-provider fallback** — `LLMRouter` resolves a chain (primary + `llm.routing.fallback`) and retries the next provider when the previous raises. Each provider attempt logs its `fallback_index` for postmortem analysis.
- **CI coverage floor** — `pytest --cov=gaworld --cov-fail-under=80`; mirrored as `[tool.coverage.report] fail_under = 80` in `pyproject.toml`.
- **New tests** — `tests/test_gaworld_io_http_guard.py` (10 tests) and `tests/test_gaworld_llm_fallback.py` (6 tests).

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
