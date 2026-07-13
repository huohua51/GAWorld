# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] — 2026-07-11 — Microkernel plugin architecture (K1 + K2-lite)

Society-centric microkernel inspired by Agent-Kernel (arXiv:2512.01610). Design doc: `docs/proposals/2026-07-11-microkernel-plugin-architecture.md`; author guide: `docs/PLUGIN_AUTHORING.md`. Behavior-preserving: full suite 551 passed / 6 pre-existing failures, identical to baseline.

### Added

- **`gaworld/kernel/`** — six kernel services (<800 lines total): `Clock` (deterministic sim time, advanced only by the main loop), `EventBus` (observe/collect/filter hook semantics with priorities; drop-in HookBus superset that loads the same `CONFIG["extensions"]` hooks), `PluginRegistry` + `Plugin` base (assembly from `CONFIG["plugins"]` class paths and `gaworld.plugins` entry points, dependency-ordered setup/teardown, trust-boundary error containment), `Controller` (priority-ordered action validator chain + audited named interventions — skeleton until K4 routes actions through it), `Recorder` (unified JSONL event stream under `output/records/`, auto `_day`/`_time` stamping), `SimContext` (single runtime source of truth; `plugin_state()` and `agent_ext()` namespace helpers replace bare agent-dict keys for plugin state).
- **`generative_city_sim.py`** — two cognition dispatch points inside the step loop, no-ops with zero subscribers: `perception.compose` (collect → snippets merged into the step env context) and `action.selected` (filter over the chosen action). Kernel bootstrap replaces the HookBus instance; all 7 legacy extension phases fire unchanged.
- **`tests/test_kernel.py`** — 23 unit tests for the six services; **`tests/test_kernel_plugin_e2e.py`** — end-to-end proof that a plugin declared only in `CONFIG["plugins"]` is assembled, injects perception that reaches an LLM prompt, and filters selected actions (zero simulator source edits).
- **`docs/PLUGIN_AUTHORING.md`** — plugin author guide (lifecycle, hook semantics, event catalog, state ownership, controller usage).

### Changed

- **`generative_city_sim.py::run_simulation`** — hook dispatch now goes through `gaworld.kernel.EventBus`; `sim_ctx.clock` is advanced at day start and each timeline tick; plugin `setup_all`/`teardown_all` wrap the simulation lifecycle. `gaworld/hooks.py` (HookBus) remains for legacy callers.

### K2 — cognition pipeline (configurable agent step)

- **`gaworld/sim/pipeline.py`** (`StagePipeline`, `DEFAULT_AGENT_STEP_ORDER`) — the ~770-line inline per-agent step body in `run_simulation` is now 12 named stages: `prepare / perceive / interrupts / plan / adjust_activity / move / select_action / reflect / update_state / broadcast / memorize / record`. Stage bodies are verbatim moves (closures over the loop's locals); cross-stage data rides the step dict — hook-visible keys keep their legacy names, working keys are underscore-prefixed, so pre/post-step hook consumers (economy, intervention plugin) are untouched.
- **Pipeline order is configuration**: `CONFIG["pipeline"]["agent_step"]` accepts builtin stage names, `"module:function"` import paths (custom stages), and `{"name", "call"}` dicts. Omitting a builtin name ablates that stage. Acceptance tests (`tests/test_pipeline_ablation.py`): removing `reflect` runs a full mock-LLM simulation with zero reflection LLM calls; a path-inserted custom stage runs once per agent-step with the step data bus and kernel clock visible.

### Fixed

- **Routine changes were silently disabled on the mainline path** (since commit `3f7edba`, ~5 months): the loop re-read `step_ctx["activity"]` unconditionally after `maybe_adjust_activity`, and the key was seeded with `scheduled_activity` at step start — so absent a pre-step hook override, the seeded value clobbered every LLM/dynamic activity adjustment. Fixed post-K2: a hook override wins only when it actually changed the seeded value. Red-green verified in `tests/test_routine_change_mainline.py`. **This changes simulation dynamics — agents now actually execute routine changes; re-baseline ongoing experiments.**

### K5 — runtime intervention API (migration complete)

- **`gaworld/kernel/interventions.py`** — every kernel ships three domain-free interventions, all audited: `set_agent_state` (immediate state write), `update_config` (dotted-path write into live CONFIG), and `remove_agent` (queued; the main loop applies removals at the day boundary and scrubs the removed ids from every remaining agent's `social_neighbors`). `LifeEventsPlugin` registers `inject_life_event`. The intervention API is the in-process programmatic surface — a dashboard HTTP bridge and `add_agent` (needs a seed-ingestion design) are tracked as follow-ups.
- `visualize_agent_state_changes` now plots each series against its own step range — state histories have unequal lengths once an agent is removed mid-run.
- Acceptance (`tests/test_interventions.py`): an agent removed via the API on day 1 no longer acts on day 2 of a real mock-LLM run.
- **This closes the K1–K5 microkernel migration** (design doc: `docs/proposals/2026-07-11-microkernel-plugin-architecture.md`).

### K4 — Controller validation gate wired into the move stage

- Structured moves now pass `Controller.validate` (an `ActionRequest("move", {to, activity})`) after location resolution. A denial keeps the agent where it is (move_agent falls back to the origin), is audited to `output/records/action.denied.jsonl`, and the reason surfaces in the agent's **next perception** as a "刚才的行动受阻：…" line — the structured feedback loop that catches hallucinated destinations.
- **`LocalPhysicalPlugin`** registers the first two validators: `location_exists` (**on by default** — `resolve_location` only yields map nodes, so it never fires in normal operation; it catches rogue rewrites from plugins/hooks, verified by a zero-denial control test) and `venue_open` (**off by default** — hard-blocking closed venues would change dynamics since the P0/P2 layers handle closures reactively; opt in via `CONFIG["controller"]["validators"]["venue_open"] = True`). An economy affordability validator is deferred until a concrete pre-move cost rule is defined.
- Acceptance (`tests/test_action_gate.py`): a config-declared plugin rewriting destinations to a nonexistent place gets denied, audited, and fed back into a subsequent perception prompt, end to end.

### K3i — dynamic behavior + spatial preferences migrated (K3 complete)

- **`gaworld/behavior/plugin.py`** (`DynamicBehaviorPlugin`) — interrupt/thought computation rides the new **`interrupts.compose`** filter. The engines return `{}` for "no change" (never `None`), so `None` flowing out of the filter means no producer ran — the interrupts stage then falls back to the legacy spontaneity path, exactly matching the old `dynamic_behavior.enabled` if/else. Third-party interrupt producers can pre-empt at higher priority. The `dynamic_result` *application* (activity change, mood delta, schedule insertion, P3 replanning) deliberately stays in the adjust_activity stage as the generic contract between interrupt producers and the pipeline; after application the stage emits the new **`interrupt.applied`** observe event.
- **`gaworld/world/plugin.py`** (`SpatialPreferencesPlugin`) — the P4 location-aversion layer: stateful load on `agents.built`, recency decay on `on_day_start`, aversion-aware redirection on the new **`location.resolve`** filter (move stage), anomaly-experience recording on `interrupt.applied` (with the pre-migration replan-gate nesting preserved as a documented parity quirk).
- With this, **all eight built-in subsystems ride the plugin surface**; `run_simulation` retains only the pipeline scaffolding, the legacy spontaneity fallback, and generic contract application.

### K3h — real-work task system migrated to a plugin

- **`gaworld/work/plugin.py`** (`RealWorkPlugin`) — owns the `RealWorkRuntime` lifecycle: create/start on `on_simulation_start`, job-market day tick on `on_day_start`, and dispatch/absorption on the new **`action.outcome`** filter event (fires in the select_action stage after the outcome line is built). Disabled runs store a `None` runtime and every hook no-ops, as before. Small improvement over the inline code: `teardown` now actually stops the worker pool (it previously leaked past simulation end).

### K3g — local physical perception migrated to a plugin

- **`gaworld/world/plugin.py`** (`LocalPhysicalPlugin`) — the P0 physical-perception layer rides the plugin surface: per-tick map refresh (sim time + occupancy) on `on_time_tick`, and the per-agent snapshot on `perception.compose` at priority 30 (stores `agent["_local_physical"]` for the interrupt engine and contributes the "身边的物理环境：…" line ahead of the life-event/intervention contributions — text order preserved exactly). `env_system` joins `city_map` in `sim_ctx.extras`. The spatial-preference layer (P4) deliberately stays inline: it is entangled with dynamic-behavior interrupt results and migrates together with that plugin.

### K3f — economy formalized as a plugin

- **`gaworld/economy/plugin.py`** (`EconomyPlugin`) — the six `gaworld.economy.finance` lifecycle handlers move from `CONFIG["extensions"]["hooks"]` declarations (`gaworld/settings/integrations.py`, now an empty user-extension map) to first-class builtin plugin assembly. Same handlers, same events, same self-gating and `extension_state["economy_module"]` runtime; ordering parity preserved (intervention post-step and interests day-end priorities still run first). The `test_extension_hooks_resolve` guard was re-expressed for the new wiring and now also verifies every builtin plugin sets up cleanly.

### K3e — life events migrated to a plugin (first event *producer*)

- **`gaworld/events/plugin.py`** (`LifeEventsPlugin`) — the life-event queue and its five consumers now ride dispatch points: ghost injection on `on_day_start` (human_realism-gated, same 0.18 dice), tick drain + env-timeline mirror on `on_time_tick` (priority 10), per-agent contribution/recording/`step["life_events"]` on the new **`env.events.compose`** collect event, the "人生事件：…" context line on `perception.compose` (priority 20), state deltas on the new **`state.effects`** observe event (emitted in the update_state stage before social influence), and the visualizer frame merge on the new **`env.events.tick`** collect event. Five inline sites and four helper functions removed from `run_simulation`.
- Behavior note: the perception context line now renders after the local-physical snippet instead of before it (same reordering class as the K3a intervention note).

### K3d — interest/skill-growth lifecycle migrated to a plugin

- **`gaworld/interests_plugin.py`** (`InterestsPlugin`) — owns the growth-profile lifecycle: bootstrap on `agents.built` (disabled runs still seed `{}` for schema parity), per-episode progress on the new **`episode.compose`** observe event (the memorize stage pre-sets empty `growth_matches`/`growth_progress` defaults, so the episode schema survives without the plugin), and day-end decay/evolution/🌱 line on `on_day_end` at priority 10 (ahead of the economy's config-registered settlement, matching the old inline order). Three inline blocks removed from `run_simulation`.
- Interim coupling documented in the plugin docstring: the profile stays at `agent["growth_profile"]` because two read-side consumers are still inline (schedule-prompt context via `format_growth_context`, location/action matching via `match_growth_items`); the key moves to `agent["ext"]["interests"]` when those migrate. Wiring pinned by `tests/test_interests_plugin.py`.

### K3c — Skill library migrated to a plugin

- **`gaworld/skills/plugin.py`** (`SkillsPlugin`) — skill injection moved from a hard-wired call inside `_cognition.perception` to the new `perception.sections` collect event (dispatched in the perceive stage; contributions render at the exact prompt position the old suffix occupied, so prompt structure is unchanged). Skill distillation moved from `memory/lifecycle.py` to the new `memory.consolidate` observe event emitted per agent at the day boundary, honoring the same `CONFIG["memory"]["skill_consolidation"]` cadence. `perception()` gained an `extra_sections` parameter; `_agent_skill_block` is gone and `gaworld/sim/_cognition.py` no longer imports the skills domain. Wiring pinned by `tests/test_skills_plugin.py` (inject / suppress / cadence).

### K3a — intervention subsystem migrated to a plugin

- **`gaworld/policy/plugin.py`** (`InterventionPlugin`) + **`gaworld/plugins/__init__.py`** (`builtin_plugins()`, the one domain-side aggregation point). The inline feed/metrics/init code is removed from `run_simulation`; the plugin rides `agents.built` (new pre-snapshot observe event), `perception.compose`, and `on_agent_post_step`. Metric state keys are still seeded when the feature is disabled (schema parity). `tests/test_intervention_plugin.py` pins the wiring both ways.
- **Behavior changes (intervention-enabled runs only)**: the feed snippet now *appends* to the step env context instead of rebuilding it from `env_context` — the inline version silently dropped the life-event context whenever a feed existed (latent bug); snippet ordering moved after the local-physical line; per-step metrics update happens at `on_agent_post_step` (after the step log/visualizer snapshot instead of before), so those auxiliary artifacts show metrics one step stale. Simulation dynamics are otherwise unchanged; `intervention_metrics.csv` schema is identical.

## [Unreleased] — 2026-07-04 — Personal Growth v2 (learning dynamics + interest evolution)

Multi-disciplinary redesign of the interest/skill-growth system (design doc: `docs/proposals/2026-07-04-personal-growth-v2.md`). All new mechanics are pure rules — no extra LLM calls; the persisted `agent_N_growth.json` schema is unchanged and backward compatible.

### Added

- **`gaworld/interests.py`** — learning dynamics: power-law diminishing returns (gains shrink with mastery), streak momentum (unbroken practice compounds), and milestone events (入门/熟练/精通 threshold crossings surfaced in `episode["growth_progress"]["milestones"]`). New `growth_phase()` derives the Hidi & Renninger four-phase label (触发期/维持期/浮现期/成熟期) from level + practice volume; `format_growth_context` now shows it, so prompt self-image evolves with development.
- **`gaworld/interests.py::apply_daily_growth_decay`** — day-end forgetting tick: unpracticed items lose level after a grace period, retention rises with accumulated practice (consolidated skills barely decay), decay is phase-aware (triggered ×1.5, well-developed ×0.5), idle gaps break streaks.
- **`gaworld/interests.py::evolve_growth_profile`** — day-end interest-set turnover: stale triggered-phase items are retired (never below 1 item); new interests are adopted by social contagion from the day's social partners (bounded by `adopt_chance`, `max_new_per_day`, `max_items`; deterministic via injectable rng).
- **`generative_city_sim.py`** — day-end growth tick wired into PHASE 3c: gathers partner growth focus from the day's episodes, runs decay + evolution, persists when stateful, prints a 🌱 change line.
- **`gaworld/settings/behavior.py`** — `interests.decay` and `interests.evolution` config blocks (both enabled by default, individually switchable).
- **`tests/test_interest_growth_dynamics.py`** — 18 cases: diminishing returns, streak momentum, milestones, decay (grace/retention/floor/streak-break/disabled), phase boundaries, evolution (retire/keep-last/adopt/chance/dedupe/caps/disabled).

### Fixed

- **`gaworld/sim/_summary.py::_growth_diff`** — read the actual `GrowthProfile` schema (`items` / float `level` / `total_minutes`) instead of the never-existing `interests` / int level / `minutes`, so end-of-run growth diffs are no longer always empty.

### Docs

- **`README.md` / `README.zh-CN.md`** — feature bullet, `interests` config note, and an expanded **Interest And Skill Growth / 兴趣爱好与技能成长系统** section covering the v2 dynamics, bilingual.
- **`docs/TUTORIAL.v2.md`** — §5.5 expanded with the v2 mechanics and their config keys; config-table row updated.
- **`docs/FEATURES.md`** — feature-table row updated with the day-end mechanics and config pointers.
- **`docs/PROJECT_STRUCTURE.md`** — `gaworld/interests.py` entry now mentions decay and interest-set evolution.
- **`docs/proposals/2026-07-04-personal-growth-v2.md`** — the design document (four-perspective expert review, mechanism specs, non-goals, validation).

## [Unreleased] — 2026-07-04 — Agent Studio (single-agent builder/inspector)

A visual builder/inspector for a single agent, integrated into the local dashboard. Seven steps bound to GAWorld's real seed model — identity + the nine `[0,1]` state variables, skills, tiered memory, Dunbar social circles, behavior dials, and review/deploy — with read/write back to the state CSV and profile Markdown.

### Added

- **`site/dashboard/studio.html` / `studio.css` / `studio.js`** — the Agent Studio front-end: a 7-step wizard (Identity, State & Personality, Abilities & Skills, Memory, Social & Relationships, Behavior & Goals, Review & Deploy) with an editable state radar, dependency-free SVG visualizations, an optional LLM interview hook, and a create-new-agent flow. Reachable from the console toolbar (**Agent Studio ↗**) or directly at `/site/dashboard/studio.html`.
- **`gaworld/apps/dashboard_server.py`** — Studio backend endpoints: `GET /api/agents/{id}/state`, `GET /api/agents/{id}/detail` (aggregate state + profile + memory counts + finance + social + skills), `GET /api/skills`, `POST /api/agents/{id}/state` (write to the state CSV), `POST /api/agents` (create agent). State writes are mirrored into the profile Markdown's `**核心状态变量**` / `**研究增强变量初始化**` lines so the CSV and MD don't drift; creation reuses the imported-agent format and preserves the CSV BOM. Social/finance readers pull from `output/memory` and `output/economy` and degrade gracefully before a run.
- **`site/dashboard/index.html`** — console toolbar link to the Studio.
- **`tests/test_dashboard_studio.py`** — 8 unittest cases: state round-trip + profile sync, identity edit, `[0,1]` clamping, create-agent (CSV row + profile block + BOM preserved), and social-snapshot parsing.

### Docs

- **`README.md` / `README.zh-CN.md`** — feature bullet, structure note, and a new **Agent Studio** subsection (7 steps, write-back rules, API table), bilingual.
- **`docs/FEATURES.md`** — feature-table row with the entry URL.
- **`docs/TUTORIAL.v2.md`** — new §12.1 Agent Studio (steps × data sources, write-back rules, API, tests) plus TOC anchor.
- **`docs/PROJECT_STRUCTURE.md`** / **`AGENTS.md`** — `site/dashboard/` studio note and `site/` tree entry.

## [Unreleased] — 2026-05-22 — Robustness Audit (S4)

Static-analysis sweep over the post-S3 codebase. Confirmed that the LLM provider retry framework, worker-pool fault chain, and per-adapter LLM guards were already production-ready; identified and closed 5 surviving silent-failure spots.

### Fixed

- **`generative_city_sim.py` L155 + L4889**: `print("⚠️  ...")` warnings during ghost event injection and off-screen social roster bootstrap now go through `_LOG.warning(...)` so they show up in structured logs.
- **`generative_city_sim.py` L4727**: Invalid `RANDOM_SEED` config no longer silently runs unseeded — emits `_LOG.warning(...)` so the user knows reproducibility was lost.
- **`gaworld/memory/store.py` L99**: Log-cache warm-up `OSError` no longer silently swallowed; emits `_LOG.debug(...)` breadcrumb. Behaviour unchanged (still falls back to whatever lines were already ingested).
- **`gaworld/memory/store.py` L418**: Vector DB close errors during teardown no longer silently swallowed; emits `_LOG.debug(...)` breadcrumb. First logger in that module.

### Docs

- **`docs/PHASE4_AUDIT.md`** — written. Documents every `except Exception` (27), silent `except: pass` (13), and live HTTP call (9) in the post-S3 repo, explains why each is either correct or was fixed, and records *why* the phase-0 "fragile error handling" baseline overstated the problem.

## [Unreleased] — 2026-05-22 — Architecture Refactor (S3)

Module reorganisation, monolith decomposition, performance fix, and bilingual docs refresh.

### Added

- **`gaworld/<sub>/` package homes for 11 previously top-level modules.** Each legacy file is now a 16-line `sys.modules` aliasing shim — the legacy import path keeps working, but new code should use the canonical `gaworld.<sub>.<module>` path.

  | Legacy import path | New canonical path |
  | --- | --- |
  | `memory_store` | `gaworld.memory.store` |
  | `social_network` | `gaworld.social.network` |
  | `city_map_system` | `gaworld.world.city_map` |
  | `environment` | `gaworld.env.system` |
  | `economy_module` | `gaworld.economy.finance` |
  | `dynamic_behavior` | `gaworld.behavior.dynamic` |
  | `llm_providers` | `gaworld.llm.providers` |
  | `human_realism` | `gaworld.cognition.realism` |
  | `intervention_policy` | `gaworld.policy.intervention` |
  | `life_events` | `gaworld.events.life` |
  | `distributed_comm` | `gaworld.distributed.comm` |

  Aliasing uses `sys.modules[__name__] = _module` so the legacy and canonical names resolve to the *same* module object — module-level state, private attribute reassignment, and monkey-patching all propagate transparently.

- **`gaworld/sim/` — extracted sub-modules from the `generative_city_sim.py` monolith.** Pulled out as cohesive groups rather than line-count slices, with re-exports left at the original locations so importers keep working:
  - `_utils.py` (~300 lines) — pure helpers (time, dates, env-context cleanup, weekday/weekend logic, JSON markers, path utilities).
  - `agents_loader.py` (~180 lines) — profile parsing (`parse_profile`, payload coercion/normalisation, profile-block formatting).
  - `_schedule.py` (~450 lines) — schedule plumbing (`_parse_schedule`, `_heuristic_schedule`, `ensure_sleep_in_schedule`, `format_plan_text`, `_compact_text`, recall labels).
  - `_location.py` (~370 lines) — agent movement (`_infer_workplace`, `_infer_home`, `assign_agent_locations`, `_update_commute_memory`, `_update_transit_progress`, `move_agent`).
  - `_rag.py` (~60 lines) — external-RAG hint helpers (`_agent_has_external_rag`, `_external_rag_hint`).
  - `_cognition.py` (~130 lines) — `get_social_context`, `perception`, `social_influence`. Uses the module-attribute LLM dispatch pattern so test mocks propagate.
  - `_diary.py` (~230 lines) — long-term memory + daily diary (`_append_memory_record`, `daily_summary`, `generate_daily_diary`, `save_daily_diary`, `_top_day_episode_lines`, `_fallback_daily_diary`).
  - `_news.py` (~760 lines, 20 names) — external information acquisition: source plumbing (`fetch_social_page_profile_source`, `load_news_sources`, `load_news_cache`, `update_news_cache`), interest scoring (`_extract_interest_keywords`, `_score_news_relevance`, `choose_news_for_agent`, `_domain_from_url`, `_build_agent_preferred_sites`, `_choose_info_target`), acquisition pipelines (`info_seek_and_store`, `search_web_and_store`, `read_news_and_store`), search-engine plumbing (`web_search`, `_extract_google_results`, `_extract_baidu_results`, `_extract_bing_results`, `_extract_generic_results`, `_build_search_query`, `_estimate_curiosity`). Kept the legacy `re.findall(r"\\(...)\\)"` over-escape verbatim — looks like a bug in source, but per Surgical Changes we don't "fix" it during extraction.
  - `_prompt.py` (~280 lines, 5 names) — prompt-fragment builders that turn agent state into Chinese prompt sections: `_band_label` (3-tier scalar → label), `_state_brief_for_prompt` (emotion/stress/energy/hunger/fatigue/time-pressure/self-control/social-need summary), `_yesterday_recap_for_prompt` (top-k prior-day episodes), `_recent_life_events_for_prompt` (consumed life events in window), `_social_pulse_for_prompt` (top-weighted relationships with recent interaction).
  - `_schedule.py` extended (+170 lines, +8 names) — six normalisation helpers (`_jitter_schedule_times`, `normalize_schedule_to_base`, `_dedupe_schedule_items`, `_enforce_schedule_min_gap`, `_has_enough_schedule_anchors`, `normalize_flexible_schedule`) plus the JSON-block extractor / schedule-change parser pair (`_extract_json_block`, `_parse_schedule_change`). `normalize_flexible_schedule` now reads its six `DAILY_PLAN_*` knobs at *call time* via `CONFIG.get(...)` — module-load snapshots break under tests that replace `CONFIG[section]` wholesale (same lesson as the S3 Phase 3 `_bootstrap_agent_external_rag` perf-fix).
  - `_rag.py` extended (~180 lines, +5 names) — `_append_external_payload_to_agent`, `_heuristic_bootstrap_external_items`, `_parse_bootstrap_external_items`, `_llm_bootstrap_external_items`, `_summarize_bootstrap_web_item`. The `_bootstrap_agent_external_rag` orchestrator stays in gen_city_sim because tests do `patch.object(sim, "_llm_bootstrap_external_items", ...)` and the orchestrator's bare-name lookups must resolve in `sim`'s globals.
  - `_action.py` (new, ~100 lines, 3 names) — pure JSON parsers used by `choose_action` and friends: `_parse_action_space`, `_parse_location_bias`, `_parse_policy_effect`. The `choose_action` orchestrator itself is deferred — see `docs/RUN_SIMULATION_EXTRACTION_PLAN.md` for the dependency-graph reasoning.
  - `_utils.py` extended (+1 name) — `_sanitize_extra_text` lifted here as a prerequisite for the RAG bootstrap extraction (was a 4-line helper used 19 times in gen_city_sim).

  Net: `generative_city_sim.py` shrank from 7,032 → 5,753 lines after the news + prompt + schedule + RAG + action extractions (≈18% in five slices); total monolith decomposition since S3 began: ~3,000 lines lifted out (≈42%) without breaking the legacy import surface.

### Deferred (with plan)

- **`run_simulation` orchestrator (1,380 lines).** Not extracted in this round — dependency graph too tangled, and lifting it without first migrating the per-step helpers (`evoke_memory`, `_social_relationship_snapshot`, `_activity_matches_keywords`, `_build_recall_context_labels`) would silently break the `patch.object(sim, ...)` test rig. Instead: inserted phase-section banners inside the function body (PHASE 1 init, PHASE 2 social network, PHASE 3 day loop with 3a/3b/3c sub-phases) as a navigation aid for a future lift. Full prerequisites + ordering recorded in `docs/RUN_SIMULATION_EXTRACTION_PLAN.md`.

### Extraction discipline notes

- **Surgical Changes preserved verbatim where it counts.** Spotted two source-code quirks during the news extraction — `r"\\(...)\\)"` over-escaped regex and `"\\n".join(...)` (literal backslash-n instead of newline). Both look like upstream bugs, but per the project rule we restored them byte-for-byte with a comment, rather than "fixing while we're here". Behaviour-preserving refactors should never silently change behaviour.

### Fixed

- **External-RAG bootstrap was firing real network calls during the e2e smoke test.** `_bootstrap_agent_external_rag` was reading the module-load snapshot `EXTERNAL_RAG_CONFIG`, but test fixtures replace `CONFIG["external_rag"]` *wholesale* (a new dict) — so the snapshot kept pointing at the original, fully-enabled config and the disable never took effect. Switched to a runtime lookup `CONFIG.get("external_rag", {}).get("bootstrap", {})`. **Result:** `test_e2e_smoke` went from 9.59 s → 1.50 s (6.4× faster); full unit suite went from 11 s → 3.34 s (3.3× faster).

- **`gaworld/world/city_map.py` path resolution after relocation.** `PROJECT_ROOT = Path(__file__).resolve().parent` evaluated to `gaworld/world/` instead of the repo root once the file moved out of the project root, breaking 15 city-map tests with `IndexError`. Corrected to `Path(__file__).resolve().parents[2]` with a comment explaining the depth.

- **`gaworld/llm/__init__.py` had a reverse-pointing import** (`from llm_providers import …`) that became a circular import the moment the root `llm_providers.py` was turned into a shim importing back into `gaworld.llm`. Rewrote `__init__.py` to import from the `.providers` sibling instead.

### Docs

- **`docs/REFACTOR_PLAN.md`** — full six-phase refactor plan with goal/risk analysis per phase.
- **`docs/REFACTOR_BASELINE.md`** — pre-refactor metrics baseline (337 pass / 4 fail / 11 s; ruff 544 errors; e2e_smoke 9.59 s with the bootstrap hot-spot).
- **`docs/PROJECT_STRUCTURE.md`** — rewritten to reflect the 13 `gaworld/` sub-packages, the 11 shim mapping table, the `gaworld/sim/` sub-modules, the path-resolution gotcha, and the post-S3 test baseline.
- **`README.md` / `README.zh-CN.md` — Project Structure sections rewritten** to list canonical `gaworld.<sub>.<module>` paths and explain the legacy-shim compatibility story.

### Internal patterns established

- **`sys.modules`-aliasing shim** as the standard pattern for legacy import paths — preserves module-level state, monkey-patching, and private attribute access; the alternative (`from X import *`) silently loses all of these.
- **Module-attribute LLM dispatch** (`from gaworld.llm import providers as _llm_providers; _llm_providers.call_llm(...)`) instead of `from gaworld.llm.providers import call_llm`. The test mock installer reassigns the module attribute, which is invisible to `from`-bound names.
- **CONFIG runtime lookup, not module-load snapshot.** Test fixtures replace `CONFIG[section]` wholesale — module-level snapshots like `_THING_CONFIG = CONFIG["thing"]` capture a now-stale dict reference. Always read via `CONFIG.get("thing", {})...` at call sites.
- **Migration pre-check** — before relocating a file, grep for `__file__`, `PROJECT_ROOT`, `Path(...).parent`, and check for pre-existing placeholder `__init__.py` files (which may contain reverse-pointing imports that need to be flipped to siblings).

### Test status

339 pass / 2 pre-existing flaky failures, full suite 3.34 s.

## [Unreleased] — 2026-05-01 — Economy + Location + Dynamic Behavior

### Added

- **`gaworld/interests.py` — interest and skill-growth system**
  - Derives persistent per-agent `growth_profile` data from profile fields, with LLM JSON parsing, hash-based cache reuse, and heuristic fallback when the LLM is unavailable.
  - Tracks hobbies and planned skills with motivation, priority, level, weekly target minutes, preferred time blocks, activity templates, career relevance, sociality, total practice minutes, last practiced day, and streak counters.
  - New runtime artifacts: `output/memory/growth_profiles.json` and `output/memory/agent_<id>_growth.json`.
  - Daily schedule and daily routine prompts now include growth context so low-commitment personal time can become concrete hobby or skill-development activity.
  - Daily intentions can include `growth_focus`; episode records now include `growth_matches` and `growth_progress`.
  - Action choice gives matched hobby/skill actions additional weight while preserving high-commitment activity guardrails.
  - Real-work capability matching can incorporate planned growth skills/interests without changing the `AgentCapabilities` schema.
  - Added unit tests for profile derivation, fallback/cache, progress updates, daily-intention budget behavior, mock LLM coverage, and daily routine prompt integration.

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
