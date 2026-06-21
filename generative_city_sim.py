import pandas as pd
import time
import random
import numpy as np
import re
import json
import uuid
import requests
from collections import defaultdict
import os
import shutil
import subprocess
import sys
import matplotlib.pyplot as plt
import networkx as nx
from html import unescape

from gaworld.settings import CONFIG
from gaworld.core.runner import parallel_map, resolve_max_workers
from gaworld.interests import (
    bootstrap_growth_profiles,
    format_growth_context,
    match_growth_items,
    save_agent_growth_profile,
    update_growth_from_episode,
)
from gaworld.logging_setup import LOG_MODE, get_logger

_LOG = get_logger("gaworld.sim")

# ---------------------------------------------------------------------------
# Log-mode helpers
# ---------------------------------------------------------------------------
_LOG_SIMPLE: bool = LOG_MODE == "simple"

# Text-cleaning helpers moved to ``gaworld.sim._utils`` during the S3
# refactor. Re-exported here so existing in-file callers keep working.
from gaworld.sim._utils import (  # noqa: E402
    _clean_env_context,
    _clean_reflection,
)

from gaworld.world.city_map import (
    all_locations as city_all_locations,
    distance_between as city_distance_between,
    load_city_map as load_structured_city_map,
    load_city_map_text as load_structured_city_map_text,
    node_by_name as city_node_by_name,
    travel_plan as build_travel_plan,
    nearest_by_category,
    nodes_by_category,
    resolve_best_location,
    activity_to_categories,
    job_to_workplace_categories,
    area_price_level,
    calc_transport_cost,
    is_rush_hour,
    set_sim_time,
)
from gaworld.world.local_physical import (
    local_physical_state,
    physical_state_text,
    update_occupancy_from_agents,
)
from gaworld.memory.spatial_preferences import (
    decay_preferences as decay_env_preferences,
    record_anomaly_experience,
    redirect_for_aversion,
)
from gaworld.distributed.comm import (
    DistributedRelayClient,
    extract_sender_agent_ids,
    format_inbox_context,
)
from gaworld.behavior.dynamic import (
    dynamic_transient_thought,
    evaluate_step_dynamics,
    insert_activity_into_schedule as dynamic_insert_activity,
)
from gaworld.hooks import HookBus
from environment import EnvironmentSystem, RemoteEnvironmentClient
from gaworld.llm.providers import call_llm
from gaworld.work.runtime import RealWorkRuntime
from gaworld.work.ingest import summarise_for_outcome as _rw_summarise
from gaworld.apps.visualizer import (
    SimulationVisualizer,
    build_agent_step_payload,
)
from gaworld.memory.experience import (
    append_agent_episode,
    load_agent_env_preferences,
    load_agent_episodes,
    load_agent_habits,
    load_agent_intentions,
    load_agent_relationships,
    prune_and_decay_episodes,
    save_agent_env_preferences,
    save_agent_habits,
    save_agent_intentions,
    save_agent_relationships,
)
from gaworld.cognition.realism import (
    build_context_key,
    build_daily_intentions,
    compute_episode_salience,
    consolidate_day,
    infer_episode_tags,
    infer_interaction_signal,
    intention_text,
    relationship_update,
    relationship_weight,
    update_habits_from_episode,
    update_needs,
)
from gaworld.social.network import (
    bootstrap_social_roster,
    decay_relationships,
    enforce_dunbar,
    generate_ghost_event,
    migrate_relationships,
)
from gaworld.events.life import (
    add_life_event as _add_life_event,
    life_events_for_agent,
    list_life_events,
)


# Probability per (agent, day) of an off-screen ghost reaching out.
GHOST_EVENT_DAILY_P = 0.18


def _maybe_inject_ghost_event(agent, day, time_str):
    """If the dice roll favours it, generate one off-screen ghost event
    and push it through the life-events pipeline. Returns the event dict
    or ``None``. Failures are swallowed — the sim must never block on
    this path.
    """
    try:
        if random.random() > GHOST_EVENT_DAILY_P:
            return None
        ev = generate_ghost_event(
            agent,
            current_day=day,
            llm_call=lambda prompt, task=None, agent_id=None: call_llm(
                prompt, task=task, agent_id=agent_id
            ),
            rng=random,
        )
        if not ev:
            return None
        agent_id = agent.get("id")
        payload = {
            "title": ev["title"],
            "description": ev["description"],
            "severity": ev.get("severity", 0.55),
            "impact_tags": ev.get("impact_tags", ["relationship", "off_screen"]),
            "state_effects": ev.get("state_effects", {}),
            "schedule_mode": "scheduled",
            "day": int(day),
            "time": str(time_str or "08:30"),
            "agent_ids": [int(agent_id)] if agent_id is not None else [],
            "template_key": ev.get("template_key", "ghost_event"),
            "created_by": "social_network",
        }
        return _add_life_event(payload, CONFIG)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning(
            "ghost event injection failed for %s: %s",
            agent.get("name", "?"),
            exc,
        )
        return None
from gaworld.policy.intervention import (
    INTERVENTION_METRICS,
    append_intervention_metrics,
    build_intervention_feed,
    initialize_agent_intervention_state,
    update_agent_intervention_metrics,
)
from gaworld.events.life import (
    drain_due_life_events,
    format_life_event,
    life_event_dir,
    life_events_for_agent,
)
from gaworld.memory.store import (
    append_agent_log,
    load_agent_actions,
    load_agent_locations,
    load_agent_location_action_bias,
    load_agent_memory,
    load_agent_schedule,
    load_recent_actions,
    load_recent_log_blocks,
    load_sim_state,
    reset_agent_memory,
    retrieve_relevant_memories,
    save_agent_actions,
    save_agent_location_action_bias,
    save_agent_locations,
    save_agent_memory,
    save_agent_schedule,
    save_sim_state,
    seed_vector_db_from_memory,
    vector_db_add_entry,
    VECTOR_DB_TOP_K,
    _format_memory_hint,
    _memory_action_bias,
)
from gaworld.memory.lifecycle import run_daily_memory_lifecycle  # noqa: E402

# =========================================================
# Utils
# =========================================================
# The pure-utility helpers that used to live in this section were extracted
# into ``gaworld.sim._utils`` during the S3 refactor. They are re-exported
# here unchanged so internal callers keep working without any rename.
from gaworld.sim._utils import (  # noqa: E402
    _WEEKDAY_ALIASES,
    _WEEKDAY_ORDER,
    _WEEKDAY_ZH,
    _build_time_grid,
    _build_weekend_indexes,
    _clear_dir,
    _coerce_positive_int_list,
    _format_external_env_event,
    _minutes_to_time_str,
    _parse_sim_start_date,
    _parse_step_minutes,
    _resolve_day_context,
    _sanitize_extra_text,
    _stable_json_marker,
    _time_str_to_minutes,
    _weekday_to_index,
)

# --------------------------------------------------------------------
# HTML extraction helpers — delegated to gaworld.io.web_scrape.
# Legacy private names are kept as aliases so internal callers keep
# working unchanged. New code should import from `gaworld.io` directly.
# --------------------------------------------------------------------
from gaworld.io.web_scrape import (  # noqa: E402
    extract_meta_description as _extract_meta_content,
    extract_news_main_content as _extract_news_main_content,
    extract_title as _extract_title,
    fetch_news_excerpt,
    normalize_text as _normalize_text,
    strip_html as _strip_html,
)
from gaworld.io.web_scrape import (  # noqa: E402
    _extract_article_like_block,
    _extract_ld_json_article_body,
    _extract_paragraph_fallback,
)


# --------------------------------------------------------------------
# External information acquisition (news / search / info-seek) —
# extracted to ``gaworld.sim._news``. Re-exported here for backwards
# compatibility: tests use ``patch.object(sim, "_choose_info_target", ...)``
# and ``patch.object(sim, "_build_agent_preferred_sites", ...)``, and
# ``generate_agent_rag_seed.py`` calls ``sim.web_search`` /
# ``sim._domain_from_url``. New code should import from
# ``gaworld.sim._news`` directly.
# --------------------------------------------------------------------
from gaworld.sim._news import (  # noqa: E402
    fetch_social_page_profile_source,
    load_news_sources,
    load_news_cache,
    update_news_cache,
    _extract_interest_keywords,
    _score_news_relevance,
    choose_news_for_agent,
    _domain_from_url,
    _build_agent_preferred_sites,
    _choose_info_target,
    info_seek_and_store,
    _estimate_curiosity,
    _build_search_query,
    _extract_google_results,
    _extract_baidu_results,
    _extract_bing_results,
    _extract_generic_results,
    web_search,
    search_web_and_store,
    read_news_and_store,
)
from gaworld.sim._curiosity import (  # noqa: E402
    assemble_curiosity_context,
    should_seek_knowledge,
    propose_contextual_keywords,
)


def reset_simulation():
    memory_dir = CONFIG.get("memory_dir", "output/memory")
    log_dir = CONFIG.get("log_dir", "output/logs")
    _clear_dir(memory_dir)
    _clear_dir(log_dir)
    vector_db_path = CONFIG.get("vector_db_path")
    if vector_db_path and os.path.exists(vector_db_path):
        try:
            if os.path.isdir(vector_db_path):
                shutil.rmtree(vector_db_path)
            else:
                os.remove(vector_db_path)
        except OSError:
            pass
    for output_dir in [
        STATE_OUTPUT_DIR,
        NETWORK_OUTPUT_DIR,
        ENV_OUTPUT_DIR,
        DIARY_OUTPUT_DIR,
        VISUALIZATION_OUTPUT_DIR,
        INTERVENTION_OUTPUT_DIR,
        life_event_dir(CONFIG),
    ]:
        if output_dir not in (memory_dir, log_dir):
            _clear_dir(output_dir)
    save_sim_state({
        "last_day": 0,
        "memory_model_version": MEMORY_MODEL_VERSION,
    })

def visualize_social_network(
    agents,
    step=None,
    output_dir="output/network",
    node_color_attr=None
):
    """
    agents:
        - dict: {agent_id: agent_dict}
        - or list: [agent_dict, ...]
    agent_dict 中建议包含：
        - "id" 或 "name"
        - "friends" / "social_connections"
    """

    os.makedirs(output_dir, exist_ok=True)

    G = nx.Graph()

    # ---------- 统一 agent 访问方式 ----------
    if isinstance(agents, dict):
        agent_items = agents.items()
    else:  # list
        agent_items = [(a.get("id", str(i)), a) for i, a in enumerate(agents)]

    # ---------- 加节点 ----------
    for agent_id, agent in agent_items:
        value = agent.get(node_color_attr, 0.5) if node_color_attr else 0.5
        G.add_node(agent_id, value=value)

    # ---------- 加边 ----------
    for agent_id, agent in agent_items:
        friends = (
            agent.get("friends")
            or agent.get("social_connections")
            or []
        )
        for f in friends:
            if G.has_node(f):
                G.add_edge(agent_id, f)

    # ---------- 布局 ----------
    pos = nx.spring_layout(G, seed=42)

    node_values = [G.nodes[n]["value"] for n in G.nodes]

    plt.figure(figsize=(8, 8))
    nodes = nx.draw_networkx_nodes(
        G,
        pos,
        node_size=300,
        node_color=node_values,
        cmap=plt.cm.YlGn
    )
    nx.draw_networkx_edges(G, pos, alpha=0.4)
    nx.draw_networkx_labels(G, pos, font_size=8)

    if node_color_attr:
        plt.colorbar(nodes, label=node_color_attr)

    title = "Social Network"
    if step is not None:
        title += f" (Step {step})"
    plt.title(title)

    plt.axis("off")

    filename = "social_network.png" if step is None else f"social_network_{step:03d}.png"
    plt.savefig(os.path.join(output_dir, filename), dpi=200)
    plt.close()

def visualize_agent_state_changes(
    state_history,
    agent_names,
    output_dir="output/state",
    metrics=None,
):
    os.makedirs(output_dir, exist_ok=True)
    if not metrics:
        sample_history = next(iter(state_history.values()), {})
        metrics = list(sample_history.keys())

    if not metrics:
        return

    cols = 3 if len(metrics) > 4 else 2
    rows = int(np.ceil(len(metrics) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 4.2, rows * 3.2), sharex=True)
    axes = np.array(axes).reshape(-1)

    steps = None
    for i, metric in enumerate(metrics):
        ax = axes[i]
        for agent_id, history in state_history.items():
            series = history.get(metric, [])
            if steps is None:
                steps = list(range(len(series)))
            label = agent_names.get(agent_id, str(agent_id))
            ax.plot(steps, series, label=label, linewidth=1.6)
        ax.set_title(metric)
        ax.set_ylim(0, 1)
        ax.grid(True, alpha=0.2)

    for j in range(len(metrics), len(axes)):
        axes[j].axis("off")

    axes[0].legend(loc="upper right", fontsize=8)
    fig.suptitle("Agent State Changes Over Time")
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    out_path = os.path.join(output_dir, "agent_state_over_time.png")
    plt.savefig(out_path, dpi=200)
    plt.close()

def save_state_history(state_history, output_dir="output/state"):
    os.makedirs(output_dir, exist_ok=True)
    rows = []
    for agent_id, history in state_history.items():
        for metric, series in history.items():
            for step, value in enumerate(series):
                rows.append({
                    "agent_id": agent_id,
                    "step": step,
                    "metric": metric,
                    "value": float(value),
                })
    if not rows:
        return
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(output_dir, "agent_state_history.csv"), index=False)

def append_jsonl(path, row):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _life_event_as_env_event(event):
    return {
        "id": str(event.get("id", "")),
        "type": "life_event",
        "topic": str(event.get("template_key", "custom") or "custom"),
        "name": str(event.get("title", "人生事件") or "人生事件"),
        "description": str(event.get("description", "") or ""),
        "severity": float(event.get("severity", 0.6) or 0.6),
        "scope": "agent",
        "impact_tags": list(event.get("impact_tags", []) or []),
        "life_event": True,
    }


def _format_life_event_context(events):
    lines = [format_life_event(event) for event in (events or [])]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    return "人生事件：" + "；".join(lines)


def _record_life_events_for_agent(agent, events, day, time_str, daily_logs):
    recorded_ids = agent.setdefault("_recorded_life_event_ids", set())
    for event in events or []:
        event_id = str(event.get("id", ""))
        if event_id and event_id in recorded_ids:
            continue
        if event_id:
            recorded_ids.add(event_id)
        text = (
            f"[LifeEvent Day {day} {time_str}] "
            f"{agent.get('name', agent.get('id', 'agent'))}: {format_life_event(event)}"
        )
        print(text)
        daily_logs[agent["id"]] += text + "\n"
        append_agent_log(agent, text + "\n")
        _append_memory_record(
            agent,
            text,
            entry_type="life_event",
            day=day,
            time_str=time_str,
        )


def _apply_life_event_state_effects(agent, events):
    state = agent.setdefault("state", {})
    for event in events or []:
        effects = event.get("state_effects", {})
        if not isinstance(effects, dict):
            continue
        for key, delta in effects.items():
            if key not in state:
                continue
            try:
                state[key] = _clip01(float(state.get(key, 0.5)) + float(delta))
            except (TypeError, ValueError):
                continue


# =========================================================
# 参数
# =========================================================
_BASE_AGENT_IDS = _coerce_positive_int_list(CONFIG.get("agent_ids", []))
DISTRIBUTED_CONFIG = CONFIG.get("distributed", {})
DISTRIBUTED_ENABLED = bool(DISTRIBUTED_CONFIG.get("enabled", False))
_DISTRIBUTED_LOCAL_AGENT_IDS = _coerce_positive_int_list(
    DISTRIBUTED_CONFIG.get("local_agent_ids", [])
)
AGENT_IDS = _DISTRIBUTED_LOCAL_AGENT_IDS if (DISTRIBUTED_ENABLED and _DISTRIBUTED_LOCAL_AGENT_IDS) else _BASE_AGENT_IDS
SIM_DAYS = CONFIG["sim_days"]
SECONDS_PER_DAY = CONFIG["seconds_per_day"]

CSV_PATH = CONFIG["csv_path"]
MD_PATH = CONFIG["md_path"]
STATEFUL = CONFIG["stateful"]
MAP_PATH = CONFIG.get("map_path", "data/citymap.md")
PRINT_AGENT_PROFILE = CONFIG.get("print_agent_profile", False)
BACKGROUND = CONFIG.get("background", "")
MEMORY_MODEL_VERSION = int(CONFIG.get("memory_model_version", 1))
REQUIRE_CLEAN_RESET_ON_MEMORY_MODEL_CHANGE = bool(
    CONFIG.get("require_clean_reset_on_memory_model_change", False)
)
HUMAN_REALISM_CONFIG = CONFIG.get("human_realism", {})
HUMAN_REALISM_ENABLED = bool(HUMAN_REALISM_CONFIG.get("enabled", False))
# HUMAN_MEMORY_CONFIG / RECALL_CONFIG / MEMORY_REVIEW_CONFIG snapshots
# removed in run-split-1 — their only consumers (the evoke_memory cluster)
# moved to ``gaworld.sim._memory_recall`` and now read CONFIG at call time.
INTERESTS_CONFIG = CONFIG.get("interests", {})
INTERESTS_ENABLED = bool(INTERESTS_CONFIG.get("enabled", True))
INTERESTS_MAX_ITEMS = max(1, int(INTERESTS_CONFIG.get("max_items", 6)))
INTERESTS_CACHE_PATH = INTERESTS_CONFIG.get("cache_path", "output/memory/growth_profiles.json")
INTERESTS_PROGRESS_MINUTES = INTERESTS_CONFIG.get("progress_minutes_per_step")
INTERESTS_DAILY_INSERT_CHANCE = float(INTERESTS_CONFIG.get("daily_insert_chance", 0.55))
INTERESTS_WEEKEND_BOOST = float(INTERESTS_CONFIG.get("weekend_boost", 0.25))
STATE_OUTPUT_DIR = CONFIG.get("state_output_dir", "output/state")
NETWORK_OUTPUT_DIR = CONFIG.get("network_output_dir", "output/network")
ENV_OUTPUT_DIR = CONFIG.get("environment_output_dir", "output/environment")
DIARY_OUTPUT_DIR = CONFIG.get("diary_output_dir", "output/diaries")
VISUALIZATION_CONFIG = CONFIG.get("visualization", {})
VISUALIZATION_ENABLED = bool(VISUALIZATION_CONFIG.get("enabled", True))
VISUALIZATION_OUTPUT_DIR = VISUALIZATION_CONFIG.get("output_dir", "output/visualization")
VISUALIZATION_SITE_PATH = VISUALIZATION_CONFIG.get("site_path", "site/simviz/index.html")
VISUALIZATION_FLUSH_EVERY_FRAMES = max(
    0,
    int(VISUALIZATION_CONFIG.get("flush_every_frames", 24)),
)
INTERVENTION_CONFIG = CONFIG.get("intervention", {})
INTERVENTION_ENABLED = bool(INTERVENTION_CONFIG.get("enabled", False))
INTERVENTION_OUTPUT_DIR = INTERVENTION_CONFIG.get("output_dir", "output/intervention")
SIMULATE_REALTIME = bool(CONFIG.get("simulate_realtime", False))
RANDOM_SEED = CONFIG.get("random_seed")
TIME_STEP_MINUTES = _parse_step_minutes(CONFIG.get("time_step_minutes"))
ROUTINE_CHANGE_CONFIG = CONFIG.get("routine_change", {})
ROUTINE_CHANGE_ENABLED = bool(ROUTINE_CHANGE_CONFIG.get("enabled", True))
ROUTINE_CHANGE_BASE_CHANCE = float(ROUTINE_CHANGE_CONFIG.get("base_chance", 0.08))
ROUTINE_CHANGE_EVENT_BOOST = float(ROUTINE_CHANGE_CONFIG.get("event_boost", 0.08))
ROUTINE_CHANGE_POLICY_BOOST = float(ROUTINE_CHANGE_CONFIG.get("policy_boost", 0.05))
ROUTINE_CHANGE_MAX_CHANCE = float(ROUTINE_CHANGE_CONFIG.get("max_chance", 0.45))
SPONTANEITY_CONFIG = CONFIG.get("spontaneity", {})
SPONTANEITY_ENABLED = bool(SPONTANEITY_CONFIG.get("enabled", True))
SPONTANEITY_BASE_THOUGHT_CHANCE = float(SPONTANEITY_CONFIG.get("base_thought_chance", 0.18))
SPONTANEITY_MAX_THOUGHT_CHANCE = float(SPONTANEITY_CONFIG.get("max_thought_chance", 0.68))
SPONTANEITY_EVENT_BOOST = float(SPONTANEITY_CONFIG.get("event_boost", 0.10))
SPONTANEITY_POLICY_BOOST = float(SPONTANEITY_CONFIG.get("policy_boost", 0.08))
SPONTANEITY_SOCIAL_BOOST = float(SPONTANEITY_CONFIG.get("social_boost", 0.08))
SPONTANEITY_LOW_SELF_CONTROL_BOOST = float(SPONTANEITY_CONFIG.get("low_self_control_boost", 0.22))
SPONTANEITY_STRESS_BOOST = float(SPONTANEITY_CONFIG.get("stress_boost", 0.18))
SPONTANEITY_FATIGUE_BOOST = float(SPONTANEITY_CONFIG.get("fatigue_boost", 0.14))
SPONTANEITY_HUNGER_BOOST = float(SPONTANEITY_CONFIG.get("hunger_boost", 0.12))
SPONTANEITY_IMPULSE_ACTIVITY_CHANCE = float(SPONTANEITY_CONFIG.get("impulse_activity_chance", 0.10))
SPONTANEITY_RANDOM_ACTION_CHANCE = float(SPONTANEITY_CONFIG.get("random_action_chance", 0.05))
SPONTANEITY_MAX_OVERRIDE_BONUS = float(SPONTANEITY_CONFIG.get("max_override_bonus", 0.35))
NEWS_CONFIG = CONFIG.get("news", {})
NEWS_ENABLED = bool(NEWS_CONFIG.get("enabled", False))
NEWS_SOURCES_PATH = NEWS_CONFIG.get("sources_path", "data/news_source.md")
NEWS_DAILY_CHANCE = float(NEWS_CONFIG.get("daily_chance", 0.5))
NEWS_MAX_READS_PER_DAY = int(NEWS_CONFIG.get("max_reads_per_day", 1))
NEWS_CACHE_PATH = NEWS_CONFIG.get("cache_path", "data/news_cache.json")
NEWS_USE_CACHE_FIRST = bool(NEWS_CONFIG.get("use_cache_first", True))
INFO_SEEK_CONFIG = NEWS_CONFIG.get("info_seek", NEWS_CONFIG.get("curiosity_search", {}))
INFO_SEEK_ENABLED = bool(INFO_SEEK_CONFIG.get("enabled", True))
INFO_SEEK_BASE_CHANCE = float(INFO_SEEK_CONFIG.get("base_daily_chance", 0.55))
INFO_SEEK_MAX_PER_DAY = int(INFO_SEEK_CONFIG.get("max_seeks_per_day", INFO_SEEK_CONFIG.get("max_searches_per_day", 3)))


def _maybe_curiosity_seek(
    agent,
    *,
    day,
    time_str,
    scheduled_activity,
    recent_events,
    news_cache,
    news_sources,
    preferred_sites,
    seen_urls,
    used_queries,
    curiosity_budget,
    config,
    daily_logs=None,
):
    """Event-driven contextual seek. Returns True if a seek fired.

    Writes nothing itself beyond delegating to ``info_seek_and_store``;
    decrements the per-agent daily budget on a real fire.
    """
    if not config.get("contextual_keywords", True):
        return False
    agent_id = agent["id"]
    budget_left = int(curiosity_budget.get(agent_id, 0))
    context = assemble_curiosity_context(
        agent,
        scheduled_activity=scheduled_activity or "",
        recent_events=recent_events or [],
        day=day,
        time_str=time_str,
    )
    trigger, _reason = should_seek_knowledge(
        agent, context, budget_left=budget_left, config=config
    )
    if not trigger:
        return False
    keywords = propose_contextual_keywords(agent, context, config=config)
    if not keywords:
        return False
    memory_entry, info_log, result_url, query = info_seek_and_store(
        agent,
        day=day,
        time_str=time_str,
        news_cache=news_cache,
        news_sources=news_sources,
        preferred_sites=preferred_sites,
        seen_urls=seen_urls,
        used_queries=used_queries,
        keywords=keywords,
        config=config,
    )
    if query:
        used_queries.add(query)
    if result_url:
        seen_urls.add(result_url)
    if not memory_entry:
        return False
    curiosity_budget[agent_id] = budget_left - 1
    if info_log:
        print(info_log)
        if daily_logs is not None:
            daily_logs[agent_id] += info_log
        append_agent_log(agent, info_log)
    return True


LOCAL_PHYSICAL_CONFIG = CONFIG.get("local_physical", {}) if isinstance(CONFIG, dict) else {}
LOCAL_PHYSICAL_ENABLED = bool(LOCAL_PHYSICAL_CONFIG.get("enabled", True))
LOCAL_PHYSICAL_INJECT = bool(LOCAL_PHYSICAL_CONFIG.get("inject_into_perception", True))
LOCAL_PHYSICAL_BUSY_RATIO = float(LOCAL_PHYSICAL_CONFIG.get("crowd_busy_ratio", 0.6))
LOCAL_PHYSICAL_PACKED_RATIO = float(LOCAL_PHYSICAL_CONFIG.get("crowd_packed_ratio", 0.9))
LOCAL_PHYSICAL_ANOMALY_RATIO = float(LOCAL_PHYSICAL_CONFIG.get("crowd_anomaly_ratio", 0.9))
LOCAL_PHYSICAL_ANOMALY_JUMP = float(LOCAL_PHYSICAL_CONFIG.get("crowd_anomaly_jump", 0.25))
REPLAN_CONFIG = CONFIG.get("replan", {}) if isinstance(CONFIG, dict) else {}
REPLAN_ENABLED = bool(REPLAN_CONFIG.get("enabled", True))
REPLAN_WINDOW_MINUTES = max(1, int(REPLAN_CONFIG.get("window_minutes", 120)))
REPLAN_DEFER_GAP = max(1, int(REPLAN_CONFIG.get("defer_gap_minutes", 30)))
SPATIAL_PREF_CONFIG = CONFIG.get("spatial_preferences", {}) if isinstance(CONFIG, dict) else {}
SPATIAL_PREF_ENABLED = bool(SPATIAL_PREF_CONFIG.get("enabled", True))
SPATIAL_PREF_WEIGHT = float(SPATIAL_PREF_CONFIG.get("anomaly_weight", 1.0))
SPATIAL_PREF_THRESHOLD = float(SPATIAL_PREF_CONFIG.get("avoid_threshold", 1.5))
SPATIAL_PREF_HALF_LIFE = float(SPATIAL_PREF_CONFIG.get("half_life_days", 7.0))


def _env_weather_state(env_system) -> str:
    """Best-effort read of the environment's current weather label."""
    try:
        state = env_system.export_runtime_state()
        if isinstance(state, dict):
            return str(state.get("weather_state", "") or "")
    except Exception:  # noqa: BLE001 — remote client may lack this method
        pass
    return str(getattr(env_system, "_weather_state", "") or "")


DAILY_PLANNING_CONFIG = CONFIG.get("daily_planning", {})
DAILY_PLAN_ANCHOR_MINUTES = max(1, int(DAILY_PLANNING_CONFIG.get("anchor_minutes", 30)))
DAILY_PLAN_RANDOM_DELAY_MAX_MINUTES = max(0, int(DAILY_PLANNING_CONFIG.get("random_delay_max_minutes", 10)))
DAILY_PLAN_FLEX_CONFIG = DAILY_PLANNING_CONFIG.get("flexible", {})
DAILY_PLAN_FLEX_ENABLED = bool(DAILY_PLAN_FLEX_CONFIG.get("enabled", True))
DAILY_PLAN_MIN_ITEMS = max(3, int(DAILY_PLAN_FLEX_CONFIG.get("min_items", 6)))
DAILY_PLAN_MAX_ITEMS = max(DAILY_PLAN_MIN_ITEMS, int(DAILY_PLAN_FLEX_CONFIG.get("max_items", 12)))
DAILY_PLAN_MAX_SHIFT_MINUTES = max(0, int(DAILY_PLAN_FLEX_CONFIG.get("max_time_shift_minutes", 120)))
DAILY_PLAN_MIN_GAP_MINUTES = max(1, int(DAILY_PLAN_FLEX_CONFIG.get("min_gap_minutes", 15)))
DAILY_PLAN_ALLOW_INSERTIONS = bool(DAILY_PLAN_FLEX_CONFIG.get("allow_insertions", True))
EXTERNAL_RAG_CONFIG = CONFIG.get("external_rag", {})
# EXTERNAL_RAG_TOP_K was moved to gaworld.sim._rag along with its only
# caller (_external_rag_hint); the constant is now re-exported from there.
CALENDAR_CONFIG = CONFIG.get("calendar", {})
SIM_START_DATE = _parse_sim_start_date(CALENDAR_CONFIG.get("start_date", "today"))
SIM_START_WEEKDAY_INDEX = _weekday_to_index(CALENDAR_CONFIG.get("start_weekday", "monday"))
if SIM_START_WEEKDAY_INDEX is None:
    SIM_START_WEEKDAY_INDEX = 0
SIM_WEEKEND_INDEXES = _build_weekend_indexes(CALENDAR_CONFIG.get("weekend_days", ["saturday", "sunday"]))
AGENT_IMPORT_OUTPUT_DIR = CONFIG.get("agent_import_output_dir", "output/imported_agents")

# RECALL_STAGE_ENTRY_TYPES / RECALL_STAGE_HINTS /
# POSITIVE_RECALL_HINTS / NEGATIVE_RECALL_HINTS moved to
# ``gaworld.sim._memory_recall`` and re-exported below at the
# memory-recall import block.  The two POSITIVE/NEGATIVE tuples still
# have an in-file consumer (the affect-sentiment lookup further down);
# the re-export binds them in this module's globals so the bare-name
# lookups continue to resolve.

# =========================================================
# 政策事件
# =========================================================
POLICY_EVENTS = CONFIG["policy_events"]

# =========================================================
# Profile 解析
# =========================================================
def load_profile_from_md(agent_id):
    with open(MD_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    pattern = rf"## Profile {agent_id:02d}｜.*?(?=\n## Profile |\Z)"
    match = re.search(pattern, text, re.S)
    if not match:
        raise ValueError(f"Profile {agent_id} not found")
    return match.group(0)

# Profile parsing + payload coercion helpers moved to
# ``gaworld.sim.agents_loader`` during the S3 refactor. Re-exported here so
# the rest of this file (and external callers like
# ``generate_agent_rag_seed.py``) keep working unchanged.
from gaworld.sim.agents_loader import (  # noqa: E402
    _clip_state_value,
    _safe_float,
    _safe_int,
    _safe_text,
    parse_profile,
)

def _next_profile_id(df, md_path):
    max_id = 0
    if df is not None and not df.empty and "id" in df.columns:
        try:
            max_id = max(max_id, int(pd.to_numeric(df["id"], errors="coerce").max()))
        except (ValueError, TypeError):
            # All-NaN column → max() returns NaN which can't be cast to int.
            pass
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        text = ""
    ids = [int(v) for v in re.findall(r"## Profile\s+(\d+)", text)]
    if ids:
        max_id = max(max_id, max(ids))
    return max_id + 1

def _load_social_source(url=None, file_path=None, text=None):
    if url:
        source = fetch_social_page_profile_source(url)
        source["source_type"] = "url"
        return source
    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as exc:
            raise ValueError(f"读取文件失败：{file_path}") from exc
        trimmed = content.strip()
        return {
            "url": "",
            "title": os.path.basename(file_path),
            "summary": "",
            "content": trimmed,
            "source_type": "file",
        }
    if text:
        trimmed = str(text).strip()
        return {
            "url": "",
            "title": "direct_text",
            "summary": "",
            "content": trimmed,
            "source_type": "text",
        }
    raise ValueError("必须提供 --url、--file 或 --text 之一")

def _parse_agent_seed_payload(text):
    json_blob = _extract_json_block(text)
    if not json_blob:
        return {}
    try:
        raw = json.loads(json_blob)
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}

# Imported-agent payload defaults / normalisation moved to
# ``gaworld.sim.agents_loader`` during the S3 refactor.
from gaworld.sim.agents_loader import (  # noqa: E402
    _default_imported_agent_payload,
    _normalize_imported_agent_payload,
)

def _generate_imported_agent_seed(source, override_name=None):
    content = _safe_text(source.get("content"))
    if not content:
        raise ValueError("页面内容为空，无法创建智能体")
    source_url = _safe_text(source.get("url"), "无")
    source_title = _safe_text(source.get("title"), "无")
    prompt = f"""
你是城市社会模拟器的人物建模器。请根据给定社交媒体页面内容，抽取并补全一个可用于仿真的人物画像。
来源页面标题：{source_title}
来源页面 URL：{source_url}
页面文本：
{content}

要求：
1) 只输出一个 JSON 对象，不要输出其他文字。
2) JSON 字段必须包含：
name, gender, age, hukou, residence, education_income, job, personality, daily_life, social_network, values, source_summary, state
3) `state` 必须是 JSON 对象，包含：
emotion, stress, econ_security, city_identity, policy_sensitivity, platform_dependence, risk_preference, voice_propensity, mobility_intent
4) 所有 state 数值在 0 到 1 之间。
5) 若页面信息不足，可以合理推断，但要保持谨慎，避免编造过细的细节。
6) `residence` 尽量使用杭州城区/片区风格短语；`hukou` 若无法判断可写“未知”。
7) `source_summary` 用 1-2 句概括你主要依据了哪些内容来构造此人。
"""
    response = call_llm(prompt, task="social_profile", agent_id=None)
    raw = _parse_agent_seed_payload(response)
    return _normalize_imported_agent_payload(raw, source, override_name=override_name)

# Markdown profile formatter moved to ``gaworld.sim.agents_loader`` during
# the S3 refactor.
from gaworld.sim.agents_loader import _format_imported_profile_block  # noqa: E402

def _append_imported_agent_records(agent_id, payload, source, csv_path=CSV_PATH, md_path=MD_PATH):
    df = pd.read_csv(csv_path)
    row = {
        "id": int(agent_id),
        "name": payload["name"],
        "gender": payload["gender"],
        "age": int(payload["age"]),
        "hukou": payload["hukou"],
        "residence": payload["residence"],
        "emotion": payload["state"]["emotion"],
        "stress": payload["state"]["stress"],
        "econ_security": payload["state"]["econ_security"],
        "city_identity": payload["state"]["city_identity"],
        "policy_sensitivity": payload["state"]["policy_sensitivity"],
        "platform_dependence": payload["state"]["platform_dependence"],
        "risk_preference": payload["state"]["risk_preference"],
        "voice_propensity": payload["state"]["voice_propensity"],
        "mobility_intent": payload["state"]["mobility_intent"],
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    profile_block = _format_imported_profile_block(agent_id, payload)
    with open(md_path, "a", encoding="utf-8") as f:
        f.write(profile_block)

    os.makedirs(AGENT_IMPORT_OUTPUT_DIR, exist_ok=True)
    artifact_base = os.path.join(AGENT_IMPORT_OUTPUT_DIR, f"agent_{agent_id}")
    artifact_payload = {
        "agent_id": int(agent_id),
        "profile": payload,
        "source": {
            "type": source.get("source_type", ""),
            "url": source.get("url", ""),
            "title": source.get("title", ""),
            "summary": source.get("summary", ""),
        },
    }
    with open(f"{artifact_base}_profile.json", "w", encoding="utf-8") as f:
        json.dump(artifact_payload, f, ensure_ascii=False, indent=2)
    with open(f"{artifact_base}_source.txt", "w", encoding="utf-8") as f:
        f.write(_safe_text(source.get("content")) + "\n")

def _cli_create_agent_from_social(url=None, file_path=None, text=None, name=None):
    source = _load_social_source(url=url, file_path=file_path, text=text)
    df = pd.read_csv(CSV_PATH)
    agent_id = _next_profile_id(df, MD_PATH)
    payload = _generate_imported_agent_seed(source, override_name=name)
    _append_imported_agent_records(agent_id, payload, source, csv_path=CSV_PATH, md_path=MD_PATH)
    print("✅ 已创建新智能体")
    print(json.dumps({
        "agent_id": int(agent_id),
        "name": payload["name"],
        "csv_path": CSV_PATH,
        "profile_path": MD_PATH,
        "artifact_dir": AGENT_IMPORT_OUTPUT_DIR,
        "source_title": source.get("title", ""),
        "source_url": source.get("url", ""),
        "source_summary": payload.get("source_summary", ""),
    }, ensure_ascii=False, indent=2))

def build_agent(agent_id, df, city_map=None):
    row = df[df["id"] == agent_id].iloc[0]
    text = parse_profile(load_profile_from_md(agent_id))
    agent = {
        "id": agent_id,
        **text,
        "gender": row.get("gender", ""),
        "hukou": row.get("hukou", ""),
        "residence": row.get("residence", ""),
        "state": {
            "emotion": float(row["emotion"]),
            "stress": float(row["stress"]),
            "econ_security": float(row["econ_security"]),
            "city_identity": float(row["city_identity"]),
            "policy_sensitivity": float(row.get("policy_sensitivity", 0.5)),
            "platform_dependence": float(row.get("platform_dependence", 0.5)),
            "risk_preference": float(row.get("risk_preference", 0.5)),
            "voice_propensity": float(row.get("voice_propensity", 0.5)),
            "mobility_intent": float(row.get("mobility_intent", 0.5)),
            "fatigue_debt": float(row.get("fatigue_debt", 0.20)),
            "self_control": float(row.get("self_control", 0.60)),
            "time_pressure": float(row.get("time_pressure", 0.25)),
            "stance_score": float(row.get("stance_score", 0.0)),
            "toxicity_score": float(row.get("toxicity_score", 0.0)),
            "misinformation_risk": float(row.get("misinformation_risk", 0.0)),
            "cross_viewpoint_exposure": float(row.get("cross_viewpoint_exposure", 0.0)),
            "intervention_reward": float(row.get("intervention_reward", 0.0)),
        },
        "memory": [],
        "social_neighbors": []
    }
    if city_map is None:
        city_map = load_city_map(MAP_PATH)
    init_agent_locations(agent, city_map)
    return agent

def print_agent_profiles(agent_ids):
    print("\n================= Agent Profiles =================")
    for agent_id in agent_ids:
        try:
            block = load_profile_from_md(agent_id)
        except ValueError as exc:
            print(f"⚠️ {exc}")
            continue
        print(block.strip())
        print()

# =========================================================
# 社交网络构建（核心新增）
# =========================================================
def build_social_network(agents, avg_degree=6, p_cross=0.15):
    groups = defaultdict(list)

    for a in agents:
        age_group = a["age"] // 10 * 10
        job_key = a["job"][:6]
        groups[f"{job_key}_{age_group}"].append(a["id"])

    network = {a["id"]: set() for a in agents}
    all_ids = [a["id"] for a in agents]

    # 组内连接
    for members in groups.values():
        for a in members:
            others = [m for m in members if m != a]
            k = min(len(others), avg_degree)
            for b in random.sample(others, k=k) if others else []:
                network[a].add(b)
                network[b].add(a)

    # 跨组弱连接
    for a in all_ids:
        if random.random() < p_cross:
            b = random.choice(all_ids)
            if b != a:
                network[a].add(b)
                network[b].add(a)

    return {k: list(v) for k, v in network.items()}

# =========================================================
# Map & Location
# =========================================================
def load_city_map(map_path):
    return load_structured_city_map(map_path)

def load_city_map_text(map_path):
    return load_structured_city_map_text(map_path)

def _all_locations(city_map):
    return city_all_locations(city_map)

# Location inference, agent-location assignment, and commute memory
# moved to gaworld.sim._location during the S3 refactor.
from gaworld.sim._location import (  # noqa: E402
    _infer_home,
    _infer_workplace,
    _pick_first_available,
    _update_commute_memory,
    assign_agent_locations,
)

def init_agent_locations(agent, city_map):
    cached_locations = load_agent_locations(agent["id"]) if STATEFUL else {}
    if cached_locations:
        agent["locations"] = cached_locations
        agent["locations"].setdefault("current", agent["locations"].get("home", "Home"))
        agent["locations"].setdefault("destination", agent["locations"].get("current", agent["locations"].get("home", "Home")))
        agent["locations"].setdefault("in_transit", False)
        agent["locations"].setdefault("transport_mode", "")
        agent["locations"].setdefault("travel_minutes", 0)
        agent["locations"].setdefault("travel_progress", 1.0)
        agent["locations"].setdefault("travel_route", [agent["locations"].get("current", agent["locations"].get("home", "Home"))])
        agent["locations"].setdefault("arrival_time", "")
        agent["_persisted_locations_marker"] = _stable_json_marker(agent["locations"])
        return agent["locations"]
    agent["locations"] = assign_agent_locations(agent, city_map)
    if STATEFUL:
        save_agent_locations(agent["id"], agent["locations"])
    agent["_persisted_locations_marker"] = _stable_json_marker(agent["locations"])
    return agent["locations"]


def persist_agent_locations_if_changed(agent):
    marker = _stable_json_marker(agent.get("locations", {}))
    if agent.get("_persisted_locations_marker") == marker:
        return False
    save_agent_locations(agent["id"], agent["locations"])
    agent["_persisted_locations_marker"] = marker
    return True

def resolve_location(agent, activity, time_str, city_map):
    """Resolve where an agent should go for a given activity.

    Uses category-based spatial matching from city_map_system instead of
    hardcoded location names, combined with time-of-day bias and agent
    profile to produce a weighted choice.
    """
    location_set = set(_all_locations(city_map))
    home = agent["locations"].get("home", "Home")
    work = agent["locations"].get("workplace", home)
    current = agent["locations"].get("current", home)

    def _time_to_minutes(t):
        if not re.match(r"^\d{2}:\d{2}$", str(t)):
            return None
        hh, mm = t.split(":")
        return int(hh) * 60 + int(mm)

    def _profile_flags(a):
        profile_blob = " ".join([
            a.get("job", ""), a.get("personality", ""),
            a.get("daily_life", ""), a.get("values", ""),
            a.get("work_style", ""),
        ])
        is_student = any(k in profile_blob for k in ["学生", "硕士", "博士", "课题组", "上课", "学习"])
        is_retired = any(k in profile_blob for k in ["退休", "无业", "待业", "失业", "家庭主妇", "家庭主夫", "已退休"])
        late_schedule = any(k in profile_blob for k in ["夜间活跃", "晚睡", "作息偏晚"])
        overtime = "加班" in a.get("work_style", "")
        return is_student, is_retired, late_schedule, overtime

    def _public_pool():
        """Build a pool of public / leisure places using category matching."""
        cats = ["leisure", "commerce"]
        candidates = resolve_best_location(city_map, current, cats,
                                           top_k=12, max_radius_km=15.0)
        pool = [nid for nid, _d in candidates if nid in location_set]
        if not pool:
            # Fallback: keyword scan (legacy)
            keywords = ["Park", "Cinema", "Market", "Library", "Community",
                        "Center", "Riverwalk", "Grove", "Playground",
                        "Fitness", "Picnic", "Pocket", "Night Market"]
            pool = [loc for loc in location_set
                    if any(k in loc for k in keywords)]
        if not pool:
            pool = [loc for loc in location_set if loc not in {home, work}]
        return pool

    def _time_bias():
        minutes = _time_to_minutes(time_str)
        is_student, is_retired, late_schedule, overtime = _profile_flags(agent)
        if minutes is None:
            return {"home": 0.4, "work": 0.3, "public": 0.3, "current": 0.2}
        if late_schedule:
            minutes = (minutes - 60) % (24 * 60)

        if minutes >= 22 * 60 or minutes < 6 * 60:
            base = {"home": 0.75, "work": 0.05, "public": 0.2, "current": 0.25}
        elif minutes < 9 * 60:
            base = {"home": 0.45, "work": 0.2, "public": 0.35, "current": 0.25}
        elif minutes < 17 * 60 + 30:
            if is_retired:
                base = {"home": 0.45, "work": 0.15, "public": 0.4, "current": 0.25}
            elif is_student:
                base = {"home": 0.2, "work": 0.55, "public": 0.25, "current": 0.2}
            else:
                base = {"home": 0.2, "work": 0.6, "public": 0.2, "current": 0.2}
        else:
            base = {"home": 0.55, "work": 0.1, "public": 0.35, "current": 0.25}
            if overtime:
                base["work"] += 0.1
                base["home"] -= 0.05
        s = agent.get("state", {})
        mobility = s.get("mobility_intent", 0.5)
        stress = s.get("stress", 0.5)
        if mobility > 0.65:
            base["public"] += 0.1
            base["home"] -= 0.05
        if mobility < 0.35:
            base["home"] += 0.1
            base["public"] -= 0.05
        if stress > 0.7:
            base["home"] += 0.08
            base["public"] -= 0.05
        return base

    def _weighted_pick(candidate_weights):
        if not candidate_weights:
            return home
        items = list(candidate_weights.items())
        locs, weights = zip(*items)
        return random.choices(locs, weights=weights, k=1)[0]

    def _add_weight(weights, loc, w):
        if not loc or w <= 0:
            return
        if loc not in location_set:
            return
        weights[loc] = weights.get(loc, 0) + w

    # ----- Commute shortcut -----
    if any(k in activity for k in ["通勤"]):
        transit_nodes = resolve_best_location(city_map, current, ["transit"],
                                              top_k=3, max_radius_km=10.0)
        for nid, _d in transit_nodes:
            if nid in location_set:
                return nid
        return _pick_first_available(
            ["Riverside Bus Station", "Market St"], location_set) or home

    # ----- Category-based activity matching -----
    activity_categories = activity_to_categories(activity)
    growth_matches = match_growth_items(agent.get("growth_profile"), activity) if INTERESTS_ENABLED else []
    growth_categories = []
    for item in growth_matches:
        category = str(item.get("category", ""))
        name = str(item.get("name", ""))
        blob = f"{category} {name} {' '.join(item.get('activity_templates', []) or [])}"
        if any(k in blob for k in ["运动", "健康", "跑步", "健身"]):
            growth_categories.extend(["leisure"])
        elif any(k in blob for k in ["阅读", "学习", "研究", "专业"]):
            growth_categories.extend(["education", "leisure"])
        elif any(k in blob for k in ["艺术", "创作", "摄影", "音乐", "内容"]):
            growth_categories.extend(["leisure", "commerce"])
        elif any(k in blob for k in ["技术", "编程", "职业", "沟通", "运营"]):
            growth_categories.extend(["commerce", "education"])
    if growth_categories:
        activity_categories = list(dict.fromkeys(list(activity_categories or []) + growth_categories))
    activity_candidates = []

    if any(k in activity for k in ["工作", "上班", "加班"]):
        activity_candidates.append(work)

    # Use category-based resolution for activity-derived categories
    if activity_categories:
        cat_results = resolve_best_location(city_map, current,
                                            activity_categories,
                                            top_k=5, max_radius_km=15.0)
        for nid, _d in cat_results:
            if nid in location_set and nid not in activity_candidates:
                activity_candidates.append(nid)

    # ----- Build weighted choice -----
    weights = {}
    bias = _time_bias()
    _add_weight(weights, home, bias["home"])
    _add_weight(weights, work, bias["work"])
    _add_weight(weights, current, bias["current"])

    public_pool = _public_pool()
    if public_pool:
        for loc in random.sample(public_pool, k=min(2, len(public_pool))):
            _add_weight(weights, loc, bias["public"])

    for loc in activity_candidates:
        _add_weight(weights, loc, 1.2)

    # Meal-time bonus for commerce/food locations
    if any(k in activity for k in ["午饭", "晚饭", "吃饭"]):
        if time_str and time_str <= "10:30":
            _add_weight(weights, home, 0.6)
        food_places = resolve_best_location(city_map, current,
                                            ["commerce"], top_k=3,
                                            max_radius_km=5.0)
        for nid, _d in food_places:
            _add_weight(weights, nid, 0.8)

    # Home-centric activities
    if any(k in activity for k in ["吃早饭", "睡前", "午休", "休息", "个人时间"]):
        _add_weight(weights, home, 0.8)

    # Habitual bonus: boost locations the agent visits frequently
    freq_places = agent.get("locations", {}).get("frequent_places", {})
    if freq_places:
        max_visits = max(freq_places.values()) or 1
        for loc, count in freq_places.items():
            if loc in weights:
                habit_bonus = 0.15 * (count / max_visits)
                _add_weight(weights, loc, habit_bonus)

    choice = _weighted_pick(weights)
    return choice or home


def _timeline_step_minutes(timeline, index):
    if not timeline:
        return 30
    current = _time_str_to_minutes(timeline[index])
    if current is None:
        return 30
    if index + 1 < len(timeline):
        nxt = _time_str_to_minutes(timeline[index + 1])
        if nxt is not None:
            delta = nxt - current
            if delta <= 0:
                delta += 24 * 60
            return max(1, delta)
    if index > 0:
        prev = _time_str_to_minutes(timeline[index - 1])
        if prev is not None:
            delta = current - prev
            if delta <= 0:
                delta += 24 * 60
            return max(1, delta)
    return max(1, TIME_STEP_MINUTES or 30)


# Transit progress + main movement dispatcher moved to
# gaworld.sim._location during the S3 refactor.
from gaworld.sim._location import _update_transit_progress, move_agent  # noqa: E402

# =========================================================
# Schedule & Action
# =========================================================
# Schedule parsing / heuristic / sleep / timing helpers moved to
# gaworld.sim._schedule during the S3 refactor.
from gaworld.sim._schedule import (  # noqa: E402
    _align_daily_planning_start_time,
    _extract_json_array_block,
    _has_workday_signature,
    _heuristic_schedule,
    _is_strictly_increasing_times,
    _parse_schedule,
    _round_to_anchor,
    _schedule_profile_flags,
    _schedule_times,
    ensure_sleep_in_schedule,
)

def _rewrite_weekend_schedule_from_profile(agent, schedule, day_context=None, day=None):
    if not schedule:
        return []
    if not day_context or day_context.get("day_type") != "weekend":
        return list(schedule)
    if not _has_workday_signature(schedule):
        return list(schedule)

    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    routine_text = json.dumps(
        [{"time": t, "activity": a} for t, a in schedule],
        ensure_ascii=False,
        indent=2,
    )
    memory_hits = retrieve_relevant_memories(agent, "周末 休息 兴趣 爱好 日程", max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    intent_hint = intention_text(agent.get("intentions")) if HUMAN_REALISM_ENABLED else "无"
    weekday_zh = day_context.get("weekday_zh", "周末")
    sim_date_text = day_context.get("sim_date", "")
    day_label = f"Day {day}" if day is not None else "当日"
    weekend_work_possible = any(
        k in " ".join([
            agent.get("job", ""),
            agent.get("daily_life", ""),
            agent.get("work_style", ""),
        ])
        for k in ["轮班", "值班", "夜班", "周末兼职", "周末营业", "周末上班"]
    )
    if weekend_work_possible:
        work_rule = "可保留少量工作/值班活动，但仍需体现周末个人安排。"
    else:
        work_rule = "尽量避免通勤/工作/加班等工作日活动。"

    prompt = f"""
你是城市生活模拟器的“周末个性化日程改写器”。
请根据角色 profile（职业、性格、爱好/习惯）改写周末活动，避免套用通用模板。
日期：{day_label}，{sim_date_text}，{weekday_zh}（周末）
角色资料：
{profile_text}
当前周末草案：
{routine_text}
相关记忆：{memory_hint}
今日行为意图：{intent_hint}

要求：
1) 仅改活动文本，时间点必须与输入完全一致。
2) 至少改写 1 个非睡眠活动，使其体现角色的个体偏好（职业压力、性格、兴趣习惯）。
3) {work_rule}
4) 输出 JSON 数组，每项为 ["HH:MM","活动"] 或 {{"time":"HH:MM","activity":"活动"}}。
5) 仅输出 JSON，不要其他文字。
"""
    response = call_llm(prompt, task="weekend_routine", agent_id=agent["id"])
    candidate = _parse_schedule(response)
    if not candidate or len(candidate) != len(schedule):
        return list(schedule)

    base_times = [t for t, _ in schedule]
    by_time = {t: a for t, a in candidate}
    if all(t in by_time for t in base_times):
        aligned = [(t, by_time[t]) for t in base_times]
    else:
        sorted_candidate = sorted(candidate, key=lambda x: _time_str_to_minutes(x[0]) or 0)
        aligned = [(t, a) for (t, _), (_, a) in zip(schedule, sorted_candidate)]

    changed = any(
        (new_act != old_act) and (not is_sleep_activity(new_act))
        for (_, old_act), (_, new_act) in zip(schedule, aligned)
    )
    return aligned if changed else list(schedule)

# External-RAG hint helpers moved to gaworld.sim._rag during the S3 refactor.
from gaworld.sim._rag import (  # noqa: E402
    EXTERNAL_RAG_TOP_K,
    _agent_has_external_rag,
    _external_rag_hint,
)


# _compact_text moved to gaworld.sim._schedule during the S3 refactor.
from gaworld.sim._schedule import _compact_text  # noqa: E402


def _parse_structured_json(text, allowed_fields):
    json_blob = _extract_json_block(text)
    if not json_blob:
        return {}
    try:
        raw = json.loads(json_blob)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    parsed = {}
    for field in allowed_fields:
        value = raw.get(field, "")
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        parsed[field] = _compact_text(value, max_chars=120)
    return parsed


# Fallback plan/reflection structs, plan/reflection text formatters, and
# the activity-commitment-level classifier moved to gaworld.sim._schedule
# during the S3 refactor.
from gaworld.sim._schedule import (  # noqa: E402
    _activity_commitment_level,
    _fallback_plan_struct,
    _fallback_reflection_struct,
    format_plan_text,
    format_reflection_text,
    replan_affected_interval,
)


# --------------------------------------------------------------------
# Decision-time memory recall + behavioural context — extracted to
# ``gaworld.sim._memory_recall``.  28 helpers: ``evoke_memory``,
# ``maybe_review_memories``, ``_build_decision_reference_bundle``, plus
# the 23 predicates / formatters / helpers they depend on.  Three
# constants (``RECALL_STAGE_HINTS``, ``RECALL_STAGE_ENTRY_TYPES``,
# ``POSITIVE_RECALL_HINTS``, ``NEGATIVE_RECALL_HINTS``) also moved.
#
# Re-exported because the legacy ``RECALL_STAGE_HINTS`` etc. constants
# at L612–L646 of this file are now dead — but ``choose_action``,
# ``planning``, ``reflection``, ``interview_agent``, ``infer_event_effect``,
# and ``_apply_life_event_state_effects`` all call these helpers as
# bare names.  Tests do ``patch.object(sim, "evoke_memory", ...)`` so
# the binding must live in this module's globals.
#
# This is the first cut of the RUN_SIMULATION extraction plan — see
# ``docs/RUN_SIMULATION_EXTRACTION_PLAN.md`` for the prerequisite
# ordering.
# --------------------------------------------------------------------
from gaworld.sim._memory_recall import (  # noqa: E402, F401
    NEGATIVE_RECALL_HINTS,
    POSITIVE_RECALL_HINTS,
    RECALL_STAGE_ENTRY_TYPES,
    RECALL_STAGE_HINTS,
    _activity_matches_keywords,
    _apply_recall_effect,
    _behavioral_action_fallbacks,
    _build_decision_reference_bundle,
    _build_recall_context_labels,
    _clip01,
    _commitment_weight,
    _current_emotion_text,
    _ensure_behavioral_action_balance,
    _format_recollection,
    _heuristic_memory_review,
    _infer_recall_valence,
    _is_location_time_relevant,
    _is_meaningful_text,
    _is_physical_environment_relevant,
    _is_social_context_relevant,
    _is_social_environment_relevant,
    _join_query_parts,
    _memory_recall_top_k,
    _same_activity_habit_entry,
    _social_relationship_snapshot,
    _summarize_environment_refs,
    evoke_memory,
    maybe_review_memories,
)

# --------------------------------------------------------------------
# RAG bootstrap helpers — extracted to ``gaworld.sim._rag``.
# Re-exported because tests do
#   patch.object(sim, "_llm_bootstrap_external_items", ...)
#   patch.object(sim, "_summarize_bootstrap_web_item", ...)
# and the orchestrator ``_bootstrap_agent_external_rag`` (below) calls
# these as bare names — bare-name lookup resolves in sim's globals,
# which is where the re-export binds them, and where patch.object
# replaces them.  Orchestrator stays here.
# --------------------------------------------------------------------
from gaworld.sim._rag import (  # noqa: E402
    _append_external_payload_to_agent,
    _heuristic_bootstrap_external_items,
    _parse_bootstrap_external_items,
    _llm_bootstrap_external_items,
    _summarize_bootstrap_web_item,
)

def _bootstrap_agent_external_rag(agent, news_cache=None, news_sources=None):
    # Read from CONFIG at call time (not the module-load snapshot
    # EXTERNAL_RAG_CONFIG): test fixtures replace CONFIG["external_rag"]
    # wholesale before each run, so the snapshot misses their patches —
    # the simulator used to silently still fire the network-heavy
    # bootstrap during the e2e smoke run. (Phase 3 perf fix.)
    bootstrap_cfg = CONFIG.get("external_rag", {}).get("bootstrap", {})
    if not isinstance(bootstrap_cfg, dict) or not bootstrap_cfg.get("enabled", False):
        return []
    # Prefer the standalone seed generator for unified bootstrap behavior.
    if bootstrap_cfg.get("use_seed_script", False):
        try:
            import generate_agent_rag_seed as rag_seed_script
            inserted, status = rag_seed_script.generate_for_runtime_agent(
                agent=agent,
                profile_items=int(bootstrap_cfg.get("profile_items", 3)),
                web_items=int(bootstrap_cfg.get("web_items", 1)),
                use_web=bool(bootstrap_cfg.get("use_web_search", True)),
                force=not bool(bootstrap_cfg.get("only_when_empty", True)),
            )
            if inserted or status == "skipped_existing":
                return inserted
        except Exception as exc:  # noqa: BLE001 — third-party seed script may raise anything.
            # Fall back to in-module bootstrap to keep simulation resilient.
            _LOG.warning("rag_seed_script bootstrap failed for agent %s: %s", agent.get("id"), exc)
    if bootstrap_cfg.get("only_when_empty", True) and _agent_has_external_rag(agent):
        return []

    max_chars = int(bootstrap_cfg.get("max_chars_per_item", 280))
    inserted = []
    profile_items = _llm_bootstrap_external_items(
        agent,
        max_items=int(bootstrap_cfg.get("profile_items", 3)),
        max_chars=max_chars,
    )
    for item in profile_items:
        payload = _store_external_info_for_agent(
            agent,
            item,
            timestamp=None,
            source="init_seed_profile",
            persist=STATEFUL,
        )
        if payload:
            inserted.append(payload)

    if not bootstrap_cfg.get("use_web_search", True):
        return inserted

    seed_config = dict(INFO_SEEK_CONFIG)
    seed_config.update({
        "prefer_source_visit_ratio": 1.0 if bootstrap_cfg.get("prefer_cached_news", True) else 0.0,
        "max_results": max(2, int(INFO_SEEK_CONFIG.get("max_results", 4))),
    })
    preferred_sites = _build_agent_preferred_sites(
        agent,
        news_sources=news_sources or [],
        news_cache=news_cache or [],
        max_sites=int(INFO_SEEK_CONFIG.get("preferred_sites_per_agent", 6)),
    )
    seen_urls = set()
    used_queries = set()
    for _ in range(max(0, int(bootstrap_cfg.get("web_items", 1)))):
        target = _choose_info_target(
            agent=agent,
            news_cache=news_cache or [],
            news_sources=news_sources or [],
            preferred_sites=preferred_sites,
            seen_urls=seen_urls,
            used_queries=used_queries,
            config=seed_config,
        )
        if not target:
            break
        url = str(target.get("url", "")).strip()
        if not url:
            continue
        seen_urls.add(url)
        query = str(target.get("query", "")).strip()
        if query:
            used_queries.add(query)
        content = _sanitize_extra_text(target.get("content", ""), max_chars=900)
        if not content:
            continue
        text = _summarize_bootstrap_web_item(
            agent,
            target.get("title", ""),
            content,
            url,
            max_chars=max_chars,
        )
        domain = _domain_from_url(url) or "web"
        payload = _store_external_info_for_agent(
            agent,
            text,
            timestamp=target.get("fetched_at", "") or "",
            source=f"init_seed_web:{domain}",
            persist=STATEFUL,
        )
        if payload:
            inserted.append(payload)
    return inserted

# --------------------------------------------------------------------
# Schedule normalisation helpers — extracted to ``gaworld.sim._schedule``.
# Re-exported because nothing outside the sim module references them; this
# keeps the in-file callers (``generate_schedule``, ``generate_daily_routine``,
# etc.) working unchanged. New code should import from
# ``gaworld.sim._schedule`` directly.
# --------------------------------------------------------------------
from gaworld.sim._schedule import (  # noqa: E402
    _jitter_schedule_times,
    normalize_schedule_to_base,
    _dedupe_schedule_items,
    _enforce_schedule_min_gap,
    _has_enough_schedule_anchors,
    normalize_flexible_schedule,
)

# ---------------------------------------------------------------------------
# Daily-routine context aggregators
#
# The daily-routine LLM prompt now folds in four extra signals so that the
# generated schedule feels like a continuation of the agent's life rather
# than a fresh draft each morning:
#   1. current body/mind state (emotion, stress, fatigue, hunger, ...)
#   2. yesterday's salient episodes (continuation cues, unfinished business)
#   3. recently triggered life events that still cast a shadow on today
#   4. social pulse — recent interactions worth following up on
#
# Each aggregator is a pure function: easy to unit-test without an LLM call.
# ---------------------------------------------------------------------------


# --------------------------------------------------------------------
# Prompt-fragment builders — extracted to ``gaworld.sim._prompt``.
# Re-exported here because tests at ``tests/test_daily_routine_context.py``
# call them via direct attribute access on the sim module
# (``sim._state_brief_for_prompt(...)`` etc.). New code should import
# from ``gaworld.sim._prompt`` directly.
# --------------------------------------------------------------------
from gaworld.sim._prompt import (  # noqa: E402
    _band_label,
    _state_brief_for_prompt,
    _yesterday_recap_for_prompt,
    _recent_life_events_for_prompt,
    _social_pulse_for_prompt,
)


def generate_daily_routine(agent, base_schedule, day=None, day_context=None):
    if not base_schedule:
        return base_schedule
    day_context = day_context or _resolve_day_context(
        day,
        start_weekday_idx=SIM_START_WEEKDAY_INDEX,
        weekend_indexes=SIM_WEEKEND_INDEXES,
        start_date=SIM_START_DATE,
    )
    day_label = f"Day {day}" if day is not None else "当日"
    sim_date_text = day_context.get("sim_date", "")
    weekday_zh = day_context.get("weekday_zh", "周一")
    day_type_zh = day_context.get("day_type_zh", "工作日")
    if day_context.get("day_type") == "weekend":
        day_rule = "今天是周末：安排应与工作日节奏有明显区别；对上班族尽量不安排通勤/工作/加班，多安排休闲、社交、家务或外出。"
    else:
        day_rule = "今天是工作日：保持较稳定的工作/学习节奏，可有少量弹性调整。"
    if DAILY_PLAN_FLEX_ENABLED:
        flexibility_rule = (
            f"今天的日程可以有 {DAILY_PLAN_MIN_ITEMS}-{DAILY_PLAN_MAX_ITEMS} 项；"
            f"可增删低承诺活动，允许插入临时任务、休息、社交回应、购物/办事或短暂走神；"
            f"高承诺活动尽量保留在原时间前后 {DAILY_PLAN_MAX_SHIFT_MINUTES} 分钟内。"
        )
    else:
        flexibility_rule = (
            "活动数量必须与基础日程一致，只允许改活动文本和小幅调整时间。"
        )
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    base_text = json.dumps(
        [{"time": t, "activity": a} for t, a in base_schedule],
        ensure_ascii=False,
        indent=2,
    )
    memory_hits = retrieve_relevant_memories(agent, "日程安排 今日计划", max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    external_hint = _external_rag_hint(agent, f"{day_type_zh} 日程 计划")
    intent_hint = intention_text(agent.get("intentions")) if HUMAN_REALISM_ENABLED else "无"
    growth_context = format_growth_context(agent.get("growth_profile"), max_items=INTERESTS_MAX_ITEMS) if INTERESTS_ENABLED else "无"
    # New: four contextual signals so the schedule reflects the agent's
    # ongoing life rather than being regenerated from scratch each day.
    state_brief_text = _state_brief_for_prompt(agent)
    yesterday_recap_text = _yesterday_recap_for_prompt(agent, day)
    recent_events_text = _recent_life_events_for_prompt(agent, day)
    social_pulse_text = _social_pulse_for_prompt(agent, day)
    prompt = f"""
你是城市生活模拟器的“今日日程”制定器。请基于角色资料与基础日程，生成今天的日程。
角色资料：
{profile_text}
日期类型：{day_label}，{sim_date_text}，{weekday_zh}，{day_type_zh}
基础日程（作为框架，不是死板脚本）：
{base_text}
{state_brief_text}
{yesterday_recap_text}
{recent_events_text}
{social_pulse_text}
可参考的近期记忆：{memory_hint}
可参考的额外信息：{external_hint}
今日行为意图：{intent_hint}
兴趣与技能成长画像：
{growth_context}
日程约束：{day_rule}
弹性约束：{flexibility_rule}
要求：
1) 输出 JSON 数组，每项为 ["HH:MM","活动"] 或 {{"time":"HH:MM","activity":"活动"}}。
2) 时间点需保持顺序，活动为中文短语；不要所有人都套同一个模板。
3) 必须包含“睡前/睡觉/睡眠”类活动，并给出具体时间。
4) 若兴趣与技能成长画像不为“无”，按现实约束自然插入 0-2 个兴趣恢复或技能练习活动；日常倾向约 {INTERESTS_DAILY_INSERT_CHANCE:.2f}，周末额外提高 {INTERESTS_WEEKEND_BOOST:.2f}，工作日少量，周末可更多。
5) 高承诺工作/上课/医疗/睡眠不可被兴趣活动硬性覆盖，低承诺个人时间可被具体兴趣或技能活动替换。
6) 活动可以包含临时念头或外界触发，但要符合角色职业、状态、星期和近期意图。
7) 日程应自然反映“当前身心状态”：情绪低/压力高/疲劳重时减少高强度任务、增加恢复性活动；精力充沛/情绪积极时可加入挑战性或社交活动。
8) “昨日关键回顾”里的未完成或被打断事项可被自然延续到今日；昨日已让人疲惫或受挫的事项今日应缩减或推后。
9) “近期突发事件”应优先反映在前一/两个时段（例如就医、处理纠纷、家庭责任、处理影响等），但不要凭空编造未在事件中提及的细节。
10) “近期社交脉动”里有强互动对象时，可在合适时段加入跟进社交（约见、电话、回信等）；如最近无社交，可适度补一次轻量联络。
11) 仅输出 JSON，不要其他文字。
"""
    response = call_llm(prompt, task="daily_routine", agent_id=agent["id"])
    schedule = _parse_schedule(response)
    normalized = normalize_flexible_schedule(base_schedule, schedule)
    if normalized:
        if len(normalized) == len(base_schedule) and _schedule_times(normalized) == _schedule_times(base_schedule):
            normalized = _jitter_schedule_times(
                normalized,
                max_shift=min(60, max(1, DAILY_PLAN_MAX_SHIFT_MINUTES)),
                min_gap=DAILY_PLAN_MIN_GAP_MINUTES,
            )
        normalized = ensure_sleep_in_schedule(agent, normalized)
        normalized = _align_daily_planning_start_time(
            normalized,
            anchor_step=DAILY_PLAN_ANCHOR_MINUTES,
            max_delay=DAILY_PLAN_RANDOM_DELAY_MAX_MINUTES,
        )
        return _rewrite_weekend_schedule_from_profile(
            agent,
            normalized,
            day_context=day_context,
            day=day,
        )
    jittered = _jitter_schedule_times(
        base_schedule,
        max_shift=min(60, max(1, DAILY_PLAN_MAX_SHIFT_MINUTES)),
        min_gap=DAILY_PLAN_MIN_GAP_MINUTES,
    )
    jittered = ensure_sleep_in_schedule(agent, jittered)
    jittered = _align_daily_planning_start_time(
        jittered,
        anchor_step=DAILY_PLAN_ANCHOR_MINUTES,
        max_delay=DAILY_PLAN_RANDOM_DELAY_MAX_MINUTES,
    )
    return _rewrite_weekend_schedule_from_profile(
        agent,
        jittered,
        day_context=day_context,
        day=day,
    )

def generate_schedule(agent):
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    memory_hits = retrieve_relevant_memories(agent, "日程安排", max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    external_hint = _external_rag_hint(agent, "长期日程 生活偏好 职业节奏")
    growth_context = format_growth_context(agent.get("growth_profile"), max_items=INTERESTS_MAX_ITEMS) if INTERESTS_ENABLED else "无"
    prompt = f"""
你是城市生活模拟器的日程生成器。请基于角色资料生成一天日程安排。
角色资料：
{profile_text}
可参考的近期记忆：{memory_hint}
可参考的额外信息：{external_hint}
兴趣与技能成长画像：
{growth_context}
要求：
1) 输出 JSON 数组，每项为 ["HH:MM","活动"] 或 {{"time":"HH:MM","activity":"活动"}}。
2) 6-10 项，时间升序覆盖早中晚，活动为中文短语。
3) 必须包含“睡前/睡觉/睡眠”类活动，并给出具体时间。
4) 若角色为退休/无业/待业/失业/家庭主妇/家庭主夫/已退休，不出现“工作/通勤/上班/加班”等活动。
5) 若角色为学生，优先出现“上课/学习/实验”等活动；若作息偏晚，适度延后。
6) 若兴趣与技能成长画像不为“无”，把个人时间具体化为 0-2 个兴趣爱好或技能发展活动。
7) 仅输出 JSON，不要其他文字。
"""
    response = call_llm(prompt, task="schedule", agent_id=agent["id"])
    schedule = _parse_schedule(response)
    if schedule:
        return ensure_sleep_in_schedule(agent, schedule)
    return ensure_sleep_in_schedule(agent, _heuristic_schedule(agent))

# --------------------------------------------------------------------
# JSON block extractor and schedule-change parser — extracted to
# ``gaworld.sim._schedule`` (siblings of the existing
# ``_extract_json_array_block``).
# --------------------------------------------------------------------
from gaworld.sim._schedule import _extract_json_block, _parse_schedule_change  # noqa: E402

def _routine_change_probability(agent, env_events, policy_desc):
    if not ROUTINE_CHANGE_ENABLED:
        return 0.0
    prob = ROUTINE_CHANGE_BASE_CHANCE
    if env_events:
        prob += ROUTINE_CHANGE_EVENT_BOOST * len(env_events)
    if policy_desc:
        prob += ROUTINE_CHANGE_POLICY_BOOST
    s = agent.get("state", {})
    stress = float(s.get("stress", 0.5))
    emotion = float(s.get("emotion", 0.5))
    hunger = float(s.get("hunger", 0.25))
    fatigue = float(s.get("fatigue_debt", 0.2))
    time_pressure = float(s.get("time_pressure", 0.25))
    if stress > 0.6:
        prob += (stress - 0.6) * 0.3
    if emotion < 0.4:
        prob += (0.4 - emotion) * 0.25
    if hunger > 0.65:
        prob += (hunger - 0.65) * 0.18
    if fatigue > 0.65:
        prob += (fatigue - 0.65) * 0.16
    if time_pressure > 0.65:
        prob += (time_pressure - 0.65) * 0.12
    return float(max(0.0, min(prob, ROUTINE_CHANGE_MAX_CHANCE)))

def _routine_change_trigger_strength(agent, env_events, policy_desc):
    state = agent.get("state", {}) if isinstance(agent, dict) else {}
    stress = float(state.get("stress", 0.5))
    hunger = float(state.get("hunger", 0.25))
    fatigue = float(state.get("fatigue_debt", 0.2))
    time_pressure = float(state.get("time_pressure", 0.25))
    self_control = float(state.get("self_control", 0.6))
    energy = float(state.get("energy", 0.75))
    trigger = 0.0
    trigger += max(0.0, stress - 0.62) * 0.65
    trigger += max(0.0, hunger - 0.68) * 0.55
    trigger += max(0.0, fatigue - 0.62) * 0.55
    trigger += max(0.0, time_pressure - 0.60) * 0.45
    trigger += max(0.0, 0.42 - self_control) * 0.65
    trigger += max(0.0, 0.35 - energy) * 0.35
    trigger += min(0.25, 0.10 * len(env_events or []))
    if policy_desc:
        trigger += 0.10
    return float(np.clip(trigger, 0.0, 1.0))


def _routine_change_resistance(agent, activity):
    state = agent.get("state", {}) if isinstance(agent, dict) else {}
    self_control = float(state.get("self_control", 0.6))
    commitment_level = _activity_commitment_level(activity)
    commitment_weight = _commitment_weight(commitment_level)
    resistance = 0.08 + commitment_weight * 0.55 + max(0.0, self_control - 0.5) * 0.20
    return commitment_level, float(np.clip(resistance, 0.0, 1.0))


def _social_context_has_trigger(social_context, inbox_messages=None):
    text = str(social_context or "")
    if inbox_messages:
        return True
    keywords = [
        "等你回应",
        "责任压力",
        "顾虑",
        "摩擦",
        "消息",
        "回复",
        "配合",
        "分工",
        "安排",
        "支持感",
    ]
    return any(k in text for k in keywords)


def _top_env_event(env_events):
    best = None
    best_score = -1.0
    for ev in env_events or []:
        if not isinstance(ev, dict):
            continue
        try:
            severity = float(ev.get("severity", 0.0))
        except (TypeError, ValueError):
            severity = 0.0
        desc = str(ev.get("description", ev.get("name", ""))).strip()
        score = severity + (0.08 if desc else 0.0)
        if score > best_score:
            best = ev
            best_score = score
    return best


def _suggest_activity_for_event(event, policy_desc, scheduled_activity):
    event_text = ""
    event_type = ""
    impact_tags = []
    if isinstance(event, dict):
        event_text = str(event.get("description", event.get("name", "")))
        event_type = str(event.get("type", "")).lower()
        impact_tags = [str(x).lower() for x in event.get("impact_tags", []) if str(x).strip()]
    if policy_desc:
        event_text = f"{event_text} {policy_desc}".strip()
        if not event_type:
            event_type = "policy"
    activity_text = str(scheduled_activity or "")
    combined = f"{event_text} {activity_text}"
    if any(k in combined for k in ["雨", "雪", "风", "高温", "寒潮", "拥堵", "封路", "施工", "停电", "天气", "路况"]) or "mobility" in impact_tags:
        if any(k in activity_text for k in ["通勤", "前往", "散步", "运动", "买菜", "购物", "会面", "拜访"]):
            return "调整出行"
        return "查看天气"
    if any(k in combined for k in ["工资", "就业", "裁员", "收入", "物价", "市场", "经济"]):
        return "盘算开支"
    if any(k in combined for k in ["政策", "监管", "制度", "社区", "通知"]):
        return "查看通知"
    if any(k in combined for k in ["平台", "技术", "服务", "系统", "应用"]):
        return "查看消息"
    if event_type:
        return "关注事件"
    return ""


def _spontaneity_probability(agent, env_events, policy_desc, social_context, inbox_messages=None):
    if not SPONTANEITY_ENABLED:
        return 0.0
    state = agent.get("state", {}) if isinstance(agent, dict) else {}
    prob = SPONTANEITY_BASE_THOUGHT_CHANCE
    if env_events:
        prob += min(0.30, SPONTANEITY_EVENT_BOOST * len(env_events))
        top_event = _top_env_event(env_events)
        if isinstance(top_event, dict):
            try:
                severity = float(top_event.get("severity", 0.0) or 0.0)
            except (TypeError, ValueError):
                severity = 0.0
            prob += 0.08 * severity
    if policy_desc:
        prob += SPONTANEITY_POLICY_BOOST
    if _social_context_has_trigger(social_context, inbox_messages=inbox_messages):
        prob += SPONTANEITY_SOCIAL_BOOST
    stress = float(state.get("stress", 0.5))
    hunger = float(state.get("hunger", 0.25))
    fatigue = float(state.get("fatigue_debt", 0.2))
    self_control = float(state.get("self_control", 0.6))
    if self_control < 0.5:
        prob += (0.5 - self_control) * SPONTANEITY_LOW_SELF_CONTROL_BOOST
    if stress > 0.55:
        prob += (stress - 0.55) * SPONTANEITY_STRESS_BOOST
    if fatigue > 0.5:
        prob += (fatigue - 0.5) * SPONTANEITY_FATIGUE_BOOST
    if hunger > 0.55:
        prob += (hunger - 0.55) * SPONTANEITY_HUNGER_BOOST
    return float(np.clip(prob, 0.0, SPONTANEITY_MAX_THOUGHT_CHANCE))


def _weighted_thought_pick(candidates):
    if not candidates:
        return {}
    weights = [max(0.01, float(item.get("intensity", 0.1))) for item in candidates]
    return random.choices(candidates, weights=weights, k=1)[0]


def maybe_generate_transient_thought(
    agent,
    time_str,
    scheduled_activity,
    perception_text,
    env_events=None,
    policy_desc=None,
    social_context="",
    inbox_messages=None,
):
    prob = _spontaneity_probability(
        agent,
        env_events or [],
        policy_desc,
        social_context,
        inbox_messages=inbox_messages,
    )
    if prob <= 0 or random.random() > prob:
        return {}

    state = agent.get("state", {}) if isinstance(agent, dict) else {}
    candidates = []
    top_event = _top_env_event(env_events or [])
    if top_event or policy_desc:
        try:
            severity = float(top_event.get("severity", 0.35) if isinstance(top_event, dict) else 0.45)
        except (TypeError, ValueError):
            severity = 0.35
        suggestion = _suggest_activity_for_event(top_event, policy_desc, scheduled_activity)
        event_desc = ""
        if isinstance(top_event, dict):
            event_desc = str(top_event.get("description", top_event.get("name", ""))).strip()
        if policy_desc:
            event_desc = f"{event_desc} {policy_desc}".strip()
        candidates.append({
            "source": "external_event" if top_event else "policy",
            "kind": "event_trigger",
            "thought": f"外面的变化可能会影响原安排，想先处理一下：{_compact_text(event_desc, max_chars=54)}",
            "activity_suggestion": suggestion or "关注事件",
            "reason": _compact_text(event_desc, max_chars=80) or "外部环境变化",
            "intensity": float(np.clip(0.35 + 0.55 * severity, 0.0, 1.0)),
        })

    if _social_context_has_trigger(social_context, inbox_messages=inbox_messages):
        candidates.append({
            "source": "social",
            "kind": "social_trigger",
            "thought": "突然想到有人可能在等回应，想先处理一下关系或消息。",
            "activity_suggestion": "回复消息",
            "reason": _compact_text(social_context, max_chars=80) or "社交消息触发",
            "intensity": float(np.clip(0.45 + 0.25 * float(state.get("social_need", 0.4)), 0.0, 1.0)),
        })

    hunger = float(state.get("hunger", 0.25))
    energy = float(state.get("energy", 0.75))
    fatigue = float(state.get("fatigue_debt", 0.2))
    stress = float(state.get("stress", 0.5))
    emotion = float(state.get("emotion", 0.5))
    self_control = float(state.get("self_control", 0.6))
    time_pressure = float(state.get("time_pressure", 0.25))
    if hunger > 0.62:
        candidates.append({
            "source": "need",
            "kind": "hunger",
            "thought": "肚子有点占据注意力，想先找点吃的。",
            "activity_suggestion": "找点吃的",
            "reason": f"hunger={hunger:.2f}",
            "intensity": float(np.clip((hunger - 0.45) * 1.25, 0.0, 1.0)),
        })
    if energy < 0.42 or fatigue > 0.62:
        candidates.append({
            "source": "need",
            "kind": "recovery",
            "thought": "身体有点撑不住，想临时缓一缓。",
            "activity_suggestion": "休息片刻",
            "reason": f"energy={energy:.2f}, fatigue={fatigue:.2f}",
            "intensity": float(np.clip(max(0.42 - energy, fatigue - 0.55) * 1.4, 0.0, 1.0)),
        })
    if time_pressure > 0.66:
        candidates.append({
            "source": "task",
            "kind": "time_pressure",
            "thought": "时间压力突然冒出来，想先把最急的事处理掉。",
            "activity_suggestion": "处理待办",
            "reason": f"time_pressure={time_pressure:.2f}",
            "intensity": float(np.clip((time_pressure - 0.55) * 1.35, 0.0, 1.0)),
        })

    impulse_chance = SPONTANEITY_IMPULSE_ACTIVITY_CHANCE
    impulse_chance += max(0.0, 0.48 - self_control) * 0.35
    impulse_chance += max(0.0, stress - 0.62) * 0.22
    impulse_chance += max(0.0, 0.42 - emotion) * 0.18
    if random.random() < min(0.55, impulse_chance):
        impulse_pool = [
            ("刷手机", "想逃开当前节奏，手已经想去刷手机。"),
            ("临时散步", "突然想出去走几分钟，换一下脑子。"),
            ("买杯咖啡", "突然想买点喝的，让自己重新提神。"),
            ("发消息聊天", "突然想找人说两句，缓一下心情。"),
            ("查看新闻", "突然想看看外面又发生了什么。"),
            ("顺手购物", "突然想顺手买点东西，满足一下即时念头。"),
            ("整理待办", "突然觉得脑子乱，想先整理一下接下来要做什么。"),
        ]
        suggestion, thought_text = random.choice(impulse_pool)
        candidates.append({
            "source": "impulse",
            "kind": "random_impulse",
            "thought": thought_text,
            "activity_suggestion": suggestion,
            "reason": f"self_control={self_control:.2f}, stress={stress:.2f}",
            "intensity": float(np.clip(0.35 + max(0.0, 0.55 - self_control) + max(0.0, stress - 0.60), 0.0, 1.0)),
        })

    picked = _weighted_thought_pick(candidates)
    if not picked:
        return {}
    picked["time"] = str(time_str)
    picked["scheduled_activity"] = str(scheduled_activity)
    picked["probability"] = round(prob, 3)
    picked["perception_excerpt"] = _compact_text(perception_text, max_chars=70)
    picked["intensity"] = round(float(np.clip(picked.get("intensity", 0.0), 0.0, 1.0)), 3)
    return picked


def format_transient_thought(thought):
    if not isinstance(thought, dict) or not thought:
        return ""
    source = str(thought.get("source", "thought"))
    kind = str(thought.get("kind", ""))
    intensity = float(thought.get("intensity", 0.0) or 0.0)
    suggestion = str(thought.get("activity_suggestion", "")).strip()
    body = str(thought.get("thought", "")).strip()
    reason = str(thought.get("reason", "")).strip()
    parts = [f"{source}/{kind}({intensity:.2f})"]
    if body:
        parts.append(body)
    if suggestion:
        parts.append(f"倾向：{suggestion}")
    if reason:
        parts.append(f"原因：{reason}")
    return "；".join(parts)


def maybe_adjust_activity(agent, time_str, scheduled_activity, perception_text, plan_text,
                          env_context, env_events, policy_desc, transient_thought=None, social_context=""):
    prob = _routine_change_probability(agent, env_events, policy_desc)
    if prob <= 0:
        return scheduled_activity, "", False
    commitment_level, resistance = _routine_change_resistance(agent, scheduled_activity)
    trigger = _routine_change_trigger_strength(agent, env_events, policy_desc)
    thought = transient_thought if isinstance(transient_thought, dict) else {}
    thought_intensity = float(thought.get("intensity", 0.0) or 0.0)
    if thought:
        prob = min(ROUTINE_CHANGE_MAX_CHANCE, prob + min(SPONTANEITY_MAX_OVERRIDE_BONUS, thought_intensity * 0.40))
        trigger = float(np.clip(trigger + thought_intensity * 0.55, 0.0, 1.0))
        source = str(thought.get("source", ""))
        if source in {"external_event", "policy", "social", "task"}:
            resistance = max(0.0, resistance - 0.08)
        elif source == "impulse":
            self_control = float(agent.get("state", {}).get("self_control", 0.6))
            if self_control < 0.45:
                resistance = max(0.0, resistance - 0.10)
    if trigger <= resistance:
        return scheduled_activity, "", False
    activation = min(0.95, prob + max(0.0, trigger - resistance) * 0.9)
    if random.random() > activation:
        return scheduled_activity, "", False

    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    state = agent.get("state", {})
    state_text = (
        f"emotion={state.get('emotion', 0.5):.2f}, "
        f"stress={state.get('stress', 0.5):.2f}, "
        f"econ_security={state.get('econ_security', 0.5):.2f}, "
        f"risk_preference={state.get('risk_preference', 0.5):.2f}, "
        f"fatigue_debt={state.get('fatigue_debt', 0.2):.2f}, "
        f"self_control={state.get('self_control', 0.6):.2f}, "
        f"time_pressure={state.get('time_pressure', 0.25):.2f}"
    )
    prompt = f"""
你是城市生活模拟器的“临时改程”决策器。
当前时间：{time_str}
原计划活动：{scheduled_activity}
该活动承诺等级：{commitment_level}
角色资料：
{profile_text}
当前状态数值：{state_text}
当前感知：{perception_text}
当前计划：{plan_text}
环境事件：{env_context if env_context else "无"}
政策事件：{policy_desc if policy_desc else "无"}
社交/任务触发：{social_context if social_context else "无"}
临时念头：{format_transient_thought(thought) if thought else "无"}
改程触发强度：{trigger:.2f}
原计划承诺阻力：{resistance:.2f}

请判断是否需要因个人意愿或环境/事件影响而临时更改该时段活动。
要求：
1) 仅输出 JSON：{{"change": true/false, "activity": "活动", "reason": "原因"}}。
2) 若不改变，change=false，activity 可留空。
3) 若改变，activity 为中文短语（2-8字），能合理反映动机与情境。
4) 高承诺活动除非触发很强，否则尽量不改；低承诺活动可以更灵活。
5) 不要输出其他文字。
"""
    response = call_llm(prompt, task="routine_change", agent_id=agent["id"])
    parsed = _parse_schedule_change(response)
    if not parsed:
        suggestion = str(thought.get("activity_suggestion", "")).strip()
        if suggestion and suggestion != scheduled_activity:
            reason = str(thought.get("reason", "")).strip() or "临时念头触发"
            return suggestion, reason, True
        return scheduled_activity, "", False
    if not parsed.get("change"):
        return scheduled_activity, parsed.get("reason", ""), False
    activity = parsed.get("activity", "").strip()
    if not activity or activity == scheduled_activity:
        return scheduled_activity, parsed.get("reason", ""), False
    return activity, parsed.get("reason", ""), True

# --------------------------------------------------------------------
# Action choice + action-space generation — extracted to
# ``gaworld.sim._action`` in run-split-2.  12 names total: 3 pure JSON
# parsers, 5 LLM-call helpers (``_llm_generate_actions``,
# ``_llm_generate_location_bias``, ``get_location_action_bias``,
# ``generate_actions``, ``build_action_space_for_agent``), the
# 340-line ``choose_action`` weighted picker, plus
# ``fallback_action``, ``ensure_action_space_for_activity``, and
# ``DEFAULT_ACTIONS``.
#
# Re-exported because tests do ``sim.choose_action(...)`` and other
# in-file callers (``planning``, ``reflection``, ``run_simulation``,
# ``maybe_adjust_activity``) reference these as bare names.  All
# CONFIG knobs are now read at call time inside ``_action.py``.
# --------------------------------------------------------------------
from gaworld.sim._action import (  # noqa: E402, F401
    DEFAULT_ACTIONS,
    _llm_generate_actions,
    _llm_generate_location_bias,
    _parse_action_space,
    _parse_location_bias,
    _parse_policy_effect,
    build_action_space_for_agent,
    choose_action,
    ensure_action_space_for_activity,
    fallback_action,
    generate_actions,
    get_location_action_bias,
)
# is_sleep_activity kept for in-file callers at L1238 and L3355 (now-shifted).
from gaworld.sim._schedule import is_sleep_activity  # noqa: E402, F401

# =========================================================
# Policy effect inference
# =========================================================
def infer_event_effect(agent, event_desc, event_type="event"):
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    prompt = f"""
你是城市生活模拟器的影响评估器。请基于事件描述与角色资料，推断该事件对角色状态的短期影响。
角色资料：
{profile_text}
事件类型：{event_type}
事件描述：{event_desc}
要求：
1) 仅输出 JSON 对象，键为 emotion、stress、econ_security、city_identity、policy_sensitivity、
   platform_dependence、risk_preference、voice_propensity、mobility_intent 的子集。
2) 值为 -0.2 到 0.2 的小幅浮点数，正值为提升，负值为下降。
3) 不要输出其他文字。
"""
    response = call_llm(prompt, task="event_effect", agent_id=agent["id"])
    effect = _parse_policy_effect(response)
    if not effect:
        return {}
    for k in effect:
        effect[k] = float(np.clip(effect[k], -0.2, 0.2))
    return effect

# =========================================================
# A. 认知模块（使用社交网络）
# =========================================================
# get_social_context + perception moved to gaworld.sim._cognition during
# the S3 refactor (unblocked once human_realism + llm_providers migrated).
from gaworld.sim._cognition import get_social_context, perception  # noqa: E402

def planning(agent, perception_text, recall_context=None, decision_refs=None):
    if bool((CONFIG.get("fos_fast_mode", {}) or {}).get("deterministic_cognition", False)):
        return _fallback_plan_struct(perception_text)
    if not isinstance(recall_context, dict):
        recall_context = evoke_memory(agent, "planning", perception_text)
    memory_hint = recall_context.get("hint", "暂无重要经验")
    recollection = recall_context.get("recollection", "").strip() or "无明显回忆"
    refs = decision_refs or {
        "emotion_text": _current_emotion_text(agent),
        "memory_hint": memory_hint,
        "recollection": recollection,
        "physical_env_relevant": False,
        "social_env_relevant": False,
        "location_time_relevant": False,
        "social_network_relevant": False,
        "physical_env_text": "",
        "social_env_text": "",
        "location_time_text": "",
        "social_network_text": "",
    }
    external_hint = _external_rag_hint(agent, perception_text)
    history_hint = "暂无历史"
    if STATEFUL:
        history_blocks = load_recent_log_blocks(agent["id"], max_blocks=2, max_chars=380)
        if history_blocks:
            history_hint = "\n---\n".join(history_blocks)
    intent_hint = intention_text(agent.get("intentions")) if HUMAN_REALISM_ENABLED else "无"
    optional_sections = []
    if refs.get("physical_env_relevant") and refs.get("physical_env_text"):
        optional_sections.append(f"相关物理环境：{refs['physical_env_text']}")
    if refs.get("social_env_relevant") and refs.get("social_env_text"):
        optional_sections.append(f"相关社会事件与社会环境：{refs['social_env_text']}")
    if refs.get("location_time_relevant") and refs.get("location_time_text"):
        optional_sections.append(refs["location_time_text"])
    if refs.get("social_network_relevant") and refs.get("social_network_text"):
        optional_sections.append(f"相关社交网络情况：{refs['social_network_text']}")
    if refs.get("transient_thought"):
        optional_sections.append(f"临时念头：{format_transient_thought(refs.get('transient_thought'))}")
    optional_text = "\n".join(optional_sections) if optional_sections else "无其他与当前规划强相关的补充参考。"
    prompt = f"""
你是{agent['name']}。
你的感知是：{perception_text}
{refs.get('emotion_text', _current_emotion_text(agent))}
你的近期经验：{refs.get('memory_hint', memory_hint)}
你此刻被唤起的回忆：{refs.get('recollection', recollection)}
可用额外信息：{external_hint}
你今天的行为意图：{intent_hint}
其他可选参考（仅保留与当前规划强相关的部分）：
{optional_text}
你的近期历史片段：
{history_hint}

请输出 JSON：
{{
  "goal": "...",
  "constraint": "...",
  "urge": "...",
  "plan": "...",
  "expected_outcome": "..."
}}
要求：
1) 每个字段 8-30 字，中文。
2) constraint 必须是现实约束，urge 必须是内心冲动或偷懒/回避/社交/恢复倾向之一。
3) plan 要体现妥协，而不是完美理性答案。
4) 仅输出 JSON，不要其他文字。
"""
    response = call_llm(prompt, task="planning", agent_id=agent["id"])
    parsed = _parse_structured_json(
        response,
        ["goal", "constraint", "urge", "plan", "expected_outcome"],
    )
    return parsed or _fallback_plan_struct(response)

def reflection(agent, outcome, recall_context=None):
    if bool((CONFIG.get("fos_fast_mode", {}) or {}).get("deterministic_cognition", False)):
        return _fallback_reflection_struct(outcome)
    if not isinstance(recall_context, dict):
        recall_context = evoke_memory(agent, "reflection", outcome)
    memory_hint = recall_context.get("hint", "暂无重要经验")
    recollection = recall_context.get("recollection", "").strip() or "无明显回忆"
    prompt = f"""
你是{agent['name']}。
刚刚发生的事情是：{outcome}
你的相关记忆：{memory_hint}
你此刻想起了：{recollection}

请输出 JSON：
{{
  "result": "...",
  "feeling": "...",
  "lesson": "...",
  "next_bias": "..."
}}
要求：
1) 每个字段 8-30 字，中文。
2) feeling 要体现真实情绪，不要只写“平静”。
3) lesson 要体现模式或代价，不要重复流水账。
4) next_bias 要体现接下来会更偏向什么做法。
5) 仅输出 JSON，不要其他文字。
"""
    response = call_llm(prompt, task="reflection", agent_id=agent["id"])
    parsed = _parse_structured_json(
        response,
        ["result", "feeling", "lesson", "next_bias"],
    )
    return parsed or _fallback_reflection_struct(response)

# _parse_interview moved to gaworld.sim._schedule (joins _parse_schedule
# as another LLM-JSON list parser) during the S3 refactor.
from gaworld.sim._schedule import _parse_interview  # noqa: E402

def interview_agent(agent, questions, context=None, max_questions=6):
    if not questions:
        return []
    if isinstance(questions, str):
        questions = [q.strip() for q in questions.splitlines() if q.strip()]
    else:
        questions = [str(q).strip() for q in questions if str(q).strip()]
    if not questions:
        return []
    questions = questions[:max_questions]

    context_text = context if context else "无"
    question_text = "\n".join(f"- {q}" for q in questions)
    recall_context = evoke_memory(agent, "interview", context_text, questions)
    memory_hint = recall_context.get("hint", "暂无重要经验")
    recollection = recall_context.get("recollection", "").strip() or "无明显回忆"
    prompt = f"""
你是{agent['name']}。
这是一次访谈，回答要真实且基于角色经历。
背景：{context_text}
你的近期经验：{memory_hint}
这些问题勾起的回忆：{recollection}

请逐题回答以下问题，每题1-3句。
要求：
1) 输出 JSON 数组，每项为 {{"question":"...","answer":"..."}} 或 ["question","answer"]。
2) 仅输出 JSON，不要其他文字。
3) 回答前先在心里调动与你问题最相关的经历，而不是泛泛而谈。
问题列表：
{question_text}
"""
    response = call_llm(prompt, task="interview", agent_id=agent["id"])
    parsed = _parse_interview(response, questions)
    if parsed:
        return parsed
    fallback = response.strip()
    if not fallback:
        return []
    return [{"question": q, "answer": fallback} for q in questions]

# =========================================================
# 社会影响（情绪扩散）
# =========================================================
# social_influence moved to gaworld.sim._cognition during the S3 refactor.
from gaworld.sim._cognition import social_influence  # noqa: E402

# =========================================================
# 状态更新
# =========================================================
def _bounded_state_target(base, *terms, lo=0.08, hi=0.92):
    return float(np.clip(base + sum(float(term) for term in terms), lo, hi))


def _apply_state_tendency(state, key, target, rate, noise_lo, noise_hi):
    current = float(state.get(key, target))
    state[key] = current + rate * (target - current) + random.uniform(noise_lo, noise_hi)


def update_state(agent):
    s = agent["state"]
    s.setdefault("policy_sensitivity", 0.5)
    s.setdefault("platform_dependence", 0.5)
    s.setdefault("risk_preference", 0.5)
    s.setdefault("voice_propensity", 0.5)
    s.setdefault("mobility_intent", 0.5)
    if HUMAN_REALISM_ENABLED:
        s.setdefault("energy", 0.75)
        s.setdefault("hunger", 0.25)
        s.setdefault("social_need", 0.40)
        s.setdefault("fatigue_debt", 0.20)
        s.setdefault("self_control", 0.60)
        s.setdefault("time_pressure", 0.25)

    energy = float(s.get("energy", 0.75))
    hunger = float(s.get("hunger", 0.25))
    social_need = float(s.get("social_need", 0.40))
    fatigue = float(s.get("fatigue_debt", 0.20))
    self_control = float(s.get("self_control", 0.60))
    time_pressure = float(s.get("time_pressure", 0.25))
    need_strain = float(np.clip(0.42 * hunger + 0.38 * (1 - energy) + 0.20 * social_need, 0.0, 1.0))

    emotion_target = _bounded_state_target(
        0.56,
        0.22 * (s["econ_security"] - 0.5),
        -0.30 * (s["stress"] - 0.5),
        0.16 * (s["city_identity"] - 0.5),
        -0.15 * (need_strain - 0.5),
        -0.16 * (fatigue - 0.5),
        0.12 * (self_control - 0.5),
        -0.12 * (time_pressure - 0.5),
        -0.08 * (s["mobility_intent"] - 0.5),
    )
    stress_target = _bounded_state_target(
        0.46,
        0.30 * (0.5 - s["econ_security"]),
        0.20 * (s["platform_dependence"] - 0.5),
        0.22 * (need_strain - 0.5),
        0.16 * (fatigue - 0.5),
        -0.18 * (self_control - 0.5),
        0.18 * (time_pressure - 0.5),
        -0.18 * (s["emotion"] - 0.5),
        -0.10 * (s["city_identity"] - 0.5),
    )
    econ_target = _bounded_state_target(
        0.53,
        -0.22 * (s["stress"] - 0.5),
        -0.18 * (s["platform_dependence"] - 0.5),
        0.10 * (s["risk_preference"] - 0.5),
        -0.10 * (need_strain - 0.5),
        -0.08 * (time_pressure - 0.5),
    )
    city_target = _bounded_state_target(
        0.58,
        0.24 * (s["emotion"] - 0.5),
        -0.18 * (s["mobility_intent"] - 0.5),
        -0.08 * (time_pressure - 0.5),
        -0.10 * (s["stress"] - 0.5),
    )
    policy_target = _bounded_state_target(
        0.52,
        0.16 * (s["stress"] - 0.5),
        0.10 * (s["voice_propensity"] - 0.5),
        -0.06 * (s["emotion"] - 0.5),
    )
    platform_target = _bounded_state_target(
        0.52,
        0.20 * (0.5 - s["econ_security"]),
        0.12 * (s["stress"] - 0.5),
        -0.10 * (s["city_identity"] - 0.5),
    )
    risk_target = _bounded_state_target(
        0.48,
        0.18 * (s["emotion"] - 0.5),
        -0.20 * (s["stress"] - 0.5),
        0.10 * (s["econ_security"] - 0.5),
    )
    voice_target = _bounded_state_target(
        0.50,
        0.20 * (s["city_identity"] - 0.5),
        0.10 * (s["emotion"] - 0.5),
        0.10 * (s["policy_sensitivity"] - 0.5),
        -0.12 * (s["stress"] - 0.5),
    )
    mobility_target = _bounded_state_target(
        0.42,
        0.22 * (s["stress"] - 0.5),
        -0.24 * (s["city_identity"] - 0.5),
        0.14 * (0.5 - s["econ_security"]),
        0.12 * (time_pressure - 0.5),
        0.08 * (fatigue - 0.5),
        -0.08 * (s["emotion"] - 0.5),
    )

    _apply_state_tendency(s, "emotion", emotion_target, 0.18, -0.012, 0.012)
    _apply_state_tendency(s, "stress", stress_target, 0.16, -0.012, 0.012)
    _apply_state_tendency(s, "econ_security", econ_target, 0.14, -0.010, 0.010)
    _apply_state_tendency(s, "city_identity", city_target, 0.12, -0.008, 0.008)
    _apply_state_tendency(s, "policy_sensitivity", policy_target, 0.12, -0.008, 0.008)
    _apply_state_tendency(s, "platform_dependence", platform_target, 0.13, -0.008, 0.008)
    _apply_state_tendency(s, "risk_preference", risk_target, 0.12, -0.008, 0.008)
    _apply_state_tendency(s, "voice_propensity", voice_target, 0.12, -0.008, 0.008)
    _apply_state_tendency(s, "mobility_intent", mobility_target, 0.14, -0.008, 0.008)
    if HUMAN_REALISM_ENABLED:
        _apply_state_tendency(s, "energy", 0.72, 0.08, -0.004, 0.004)
        _apply_state_tendency(s, "hunger", 0.35, 0.10, -0.003, 0.003)
        _apply_state_tendency(s, "social_need", 0.45, 0.08, -0.004, 0.004)
        _apply_state_tendency(s, "fatigue_debt", 0.24, 0.08, -0.004, 0.004)
        _apply_state_tendency(s, "self_control", 0.60, 0.10, -0.004, 0.004)
        _apply_state_tendency(s, "time_pressure", 0.28, 0.08, -0.004, 0.004)

    for k in s:
        s[k] = float(np.clip(s[k], 0, 1))

# =========================================================
# B. 长期记忆
# =========================================================
# Daily summary + daily diary chain (the entire ``# B. 长期记忆`` banner)
# moved to gaworld.sim._diary during the S3 refactor.
from gaworld.sim._diary import (  # noqa: E402
    _append_memory_record,
    _daily_diary_path,
    _fallback_daily_diary,
    _top_day_episode_lines,
    daily_summary,
    generate_daily_diary,
    save_daily_diary,
)
from gaworld.sim._summary import (  # noqa: E402
    summarize_simulation,
    take_initial_snapshot,
)

# =========================================================
# C. 主循环
# =========================================================
def validate_action_space(schedules, action_space):
    missing = set()
    if not schedules:
        return

    def iter_action_spaces():
        sample_key = next(iter(action_space.keys()))
        if isinstance(sample_key, int):
            return action_space.items()
        return ((agent_id, action_space) for agent_id in schedules.keys())

    for agent_id, space in iter_action_spaces():
        sch = schedules.get(agent_id, [])
        for _, activity in sch:
            if activity not in space:
                missing.add(activity)
    if missing:
        print("⚠️ 警告：以下活动没有定义动作空间：")
        for m in missing:
            print("  -", m)

def build_schedule_map(schedules):
    sorted_map = {}
    for agent_id, sch in schedules.items():
        sorted_map[agent_id] = sorted(sch, key=lambda x: x[0])
    return sorted_map

def get_activity_for_time(schedule, time_str):
    if not schedule:
        return "个人时间"
    current_minutes = _time_str_to_minutes(time_str)
    if current_minutes is None:
        return schedule[-1][1]
    last_activity = None
    for t, activity in schedule:
        t_minutes = _time_str_to_minutes(t)
        if t_minutes is None:
            continue
        if t_minutes <= current_minutes:
            last_activity = activity
        else:
            break
    return last_activity or "个人时间"

def apply_schedule_override(schedule, time_str, activity):
    if not schedule:
        return [(time_str, activity)]
    updated = [(t, a) for t, a in schedule if t != time_str]
    updated.append((time_str, activity))
    updated.sort(key=lambda x: _time_str_to_minutes(x[0]) or 0)
    return updated

def build_master_timeline(schedules, step_minutes=None):
    if step_minutes:
        times = set(_build_time_grid(step_minutes))
        for sch in schedules.values():
            times.update(t for t, _ in sch)
        return sorted(times)
    times = set()
    for sch in schedules.values():
        times.update(t for t, _ in sch)
    return sorted(times)

def _enforce_memory_model_compat(sim_state):
    if not REQUIRE_CLEAN_RESET_ON_MEMORY_MODEL_CHANGE:
        return
    current_version = sim_state.get("memory_model_version")
    if current_version is None:
        return  # Fresh start, no prior state
    if current_version != MEMORY_MODEL_VERSION:
        raise RuntimeError(
            "Memory model version changed. "
            "Please run `python generative_city_sim.py reset` once, "
            "then rerun simulation."
        )

def run_simulation():
    # ====================================================================
    # PHASE BANNERS — added in S3/round 4 as navigation aids for a future
    # extraction of this orchestrator.  Each banner marks the start of a
    # cohesive chunk; once the helpers each phase depends on have been
    # migrated out of this file, lifting each phase into
    # ``gaworld/sim/runner_<phase>.py`` becomes mechanical.  See
    # ``docs/REFACTOR_PLAN.md`` for the deferred-extraction rationale.
    # ====================================================================
    # ----- PHASE 1: Initialise (seed, load data, build agents, restore state, growth bootstrap) -----
    if RANDOM_SEED is not None:
        try:
            seed = int(RANDOM_SEED)
            random.seed(seed)
            np.random.seed(seed)
        except (TypeError, ValueError) as exc:
            # Seed config is invalid — keep going unseeded, but tell the user
            # so they don't expect reproducibility.
            _LOG.warning(
                "RANDOM_SEED=%r is not a valid int (%s); running unseeded.",
                RANDOM_SEED,
                exc,
            )
    df = pd.read_csv(CSV_PATH)
    city_map = load_city_map(MAP_PATH)
    city_map_text = load_city_map_text(MAP_PATH)
    hook_bus = HookBus(CONFIG.get("extensions", {}))
    extension_state = {}
    agents = [build_agent(i, df, city_map=city_map) for i in AGENT_IDS]
    for agent in agents:
        initialize_agent_intervention_state(agent, INTERVENTION_CONFIG)
    if PRINT_AGENT_PROFILE:
        print_agent_profiles([a["id"] for a in agents])
    start_day = 1
    if STATEFUL:
        sim_state = load_sim_state()
        _enforce_memory_model_compat(sim_state)
        # Resume day count for persistent simulations.
        last_day = sim_state.get("last_day", 0)
        if isinstance(last_day, int) and last_day >= 0:
            start_day = last_day + 1
    if STATEFUL:
        for agent in agents:
            agent["memory"] = load_agent_memory(agent["id"])
            seed_vector_db_from_memory(agent)
            # P4: learned location-aversion persists across runs (independent
            # of human-realism, so loaded outside that block).
            if SPATIAL_PREF_ENABLED:
                agent["env_preferences"] = load_agent_env_preferences(agent["id"])
            if HUMAN_REALISM_ENABLED:
                agent["episodes"] = load_agent_episodes(agent["id"])
                agent["habits"] = load_agent_habits(agent["id"])
                agent["intentions"] = load_agent_intentions(agent["id"])
                agent["relationships"] = load_agent_relationships(agent["id"])
                state = agent.setdefault("state", {})
                state.setdefault("energy", 0.75)
                state.setdefault("hunger", 0.25)
                state.setdefault("social_need", 0.40)
                state.setdefault("fatigue_debt", 0.20)
                state.setdefault("self_control", 0.60)
                state.setdefault("time_pressure", 0.25)
                agent.setdefault("last_activity", "")
                agent.setdefault("last_action", "")
    else:
        for agent in agents:
            agent["memory"] = []
            reset_agent_memory(agent["id"])
            if HUMAN_REALISM_ENABLED:
                agent["episodes"] = []
                agent["habits"] = {}
                agent["intentions"] = {}
                agent["relationships"] = {}
                state = agent.setdefault("state", {})
                state.setdefault("energy", 0.75)
                state.setdefault("hunger", 0.25)
                state.setdefault("social_need", 0.40)
                state.setdefault("fatigue_debt", 0.20)
                state.setdefault("self_control", 0.60)
                state.setdefault("time_pressure", 0.25)
                agent.setdefault("last_activity", "")
                agent.setdefault("last_action", "")
    agents_by_id = {a["id"]: a for a in agents}
    agent_names = {a["id"]: a.get("name", str(a["id"])) for a in agents}
    if INTERESTS_ENABLED:
        bootstrap_growth_profiles(
            agents,
            cache_path=INTERESTS_CACHE_PATH,
            memory_dir=CONFIG.get("memory_dir", "output/memory"),
            llm=lambda prompt: call_llm(prompt, task="growth_profile", agent_id=None),
            max_items=INTERESTS_MAX_ITEMS,
            stateful=STATEFUL,
        )
        for agent in agents:
            context = format_growth_context(agent.get("growth_profile"), max_items=INTERESTS_MAX_ITEMS)
            growth_log = f"[GrowthProfile] {agent.get('name', agent['id'])}\n{context}\n"
            print(growth_log.strip())
            append_agent_log(agent, growth_log)
    else:
        for agent in agents:
            agent["growth_profile"] = {}
    distributed_client = DistributedRelayClient(DISTRIBUTED_CONFIG)
    if distributed_client.enabled:
        registered = distributed_client.register_agents(agents)
        directory = distributed_client.refresh_directory()
        remote_ids = sorted(aid for aid in directory.keys() if aid not in AGENT_IDS)
        status = "ok" if registered else f"degraded ({distributed_client.last_error or 'register failed'})"
        print(
            f"🌐 分布式通信已启用: cluster={distributed_client.cluster}, "
            f"node={distributed_client.node_id}, status={status}, "
            f"local_agents={AGENT_IDS}, known_remote_agents={remote_ids[:12]}"
        )
    state_metrics = list(agents[0]["state"].keys()) if agents else []
    state_history = {
        a["id"]: {
            metric: [] for metric in state_metrics
        }
        for a in agents
    }
    env_service_cfg = CONFIG.get("external_environment_service", {})
    if isinstance(env_service_cfg, dict) and env_service_cfg.get("enabled", False):
        env_system = RemoteEnvironmentClient(env_service_cfg)
    else:
        env_system = EnvironmentSystem(CONFIG, llm_fn=call_llm)
    os.makedirs(ENV_OUTPUT_DIR, exist_ok=True)
    env_timeline_path = os.path.join(ENV_OUTPUT_DIR, "timeline.jsonl")
    if os.path.exists(env_timeline_path):
        try:
            os.remove(env_timeline_path)
        except OSError:
            pass
    background_text = str(BACKGROUND).strip()
    news_sources = load_news_sources(NEWS_SOURCES_PATH) if NEWS_ENABLED else []
    news_cache = []
    if NEWS_ENABLED:
        if news_sources:
            news_cache = update_news_cache(NEWS_CACHE_PATH, news_sources, NEWS_CONFIG)
        else:
            news_cache = load_news_cache(NEWS_CACHE_PATH)
    if NEWS_ENABLED and not news_sources:
        print(f"ℹ️ 未找到新闻源列表或列表为空：{NEWS_SOURCES_PATH}，将主要使用 Web 搜索。")
    if NEWS_ENABLED and not news_cache and NEWS_USE_CACHE_FIRST:
        print(f"ℹ️ 新闻缓存为空或未找到：{NEWS_CACHE_PATH}，将实时抓取网页。")
    for agent in agents:
        seeded = _bootstrap_agent_external_rag(
            agent,
            news_cache=news_cache,
            news_sources=news_sources,
        )
        if seeded:
            print(f"🧱 {agent['name']} 初始化 RAG 条目：{len(seeded)}")

    # ----- PHASE 2: Build social network + initialise per-agent edges and weights -----
    social_net = build_social_network(agents)
    for a in agents:
        a["social_neighbors"] = social_net[a["id"]]
        if HUMAN_REALISM_ENABLED:
            rel = a.setdefault("relationships", {})
            for n in a["social_neighbors"]:
                key = str(n)
                rel.setdefault(
                    key,
                    {
                        "closeness": 0.5,
                        "trust": 0.5,
                        "obligation": 0.5,
                        "friction": 0.5,
                        "last_interaction_day": 0,
                    },
                )
                rel[key].setdefault("closeness", 0.5)
                rel[key].setdefault("trust", 0.5)
                rel[key].setdefault("obligation", 0.5)
                rel[key].setdefault("friction", 0.5)
                rel[key].setdefault("last_interaction_day", 0)
            # Migrate existing records into the extended schema, then
            # seed an off-screen roster (family, old friends, etc.) so
            # the agent has relationships beyond the in-sim neighbours.
            migrate_relationships(a, current_day=start_day)
            try:
                bootstrap_social_roster(
                    a,
                    lambda prompt, task=None, agent_id=None: call_llm(
                        prompt, task=task, agent_id=agent_id
                    ),
                    current_day=start_day,
                )
            except Exception as exc:  # noqa: BLE001 - never block sim init
                _LOG.warning(
                    "off-screen social roster bootstrap failed for %s: %s",
                    a.get("name", a.get("id")),
                    exc,
                )

    for a in agents:
        if not a.get("locations"):
            init_agent_locations(a, city_map)
        a["location_action_bias"] = load_agent_location_action_bias(a["id"])
        locs = a.get("locations", {})
        init_loc_line = (
            f"[InitLocation] {a.get('name', a['id'])}: "
            f"home={locs.get('home', 'Home')} "
            f"work={locs.get('workplace', locs.get('home', 'Home'))} "
            f"current={locs.get('current', locs.get('home', 'Home'))}\n"
        )
        print(init_loc_line.strip())
        append_agent_log(a, init_loc_line)

    visualizer = None
    if VISUALIZATION_ENABLED:
        visualizer = SimulationVisualizer(
            VISUALIZATION_OUTPUT_DIR,
            city_map,
            agents,
            sim_meta={
                "sim_days": SIM_DAYS,
                "seconds_per_day": SECONDS_PER_DAY,
                "simulate_realtime": SIMULATE_REALTIME,
                "time_step_minutes": TIME_STEP_MINUTES,
                "map_path": MAP_PATH,
                "agent_ids": [a["id"] for a in agents],
            },
            flush_every_frames=VISUALIZATION_FLUSH_EVERY_FRAMES,
        )

    schedules = {}
    actions = {}
    for a in agents:
        agent_id = a["id"]
        cached_schedule = load_agent_schedule(agent_id)
        if cached_schedule:
            ensured = ensure_sleep_in_schedule(a, cached_schedule)
            schedules[agent_id] = ensured
            if ensured != cached_schedule and STATEFUL:
                save_agent_schedule(agent_id, ensured)
        else:
            # Generate schedule once per agent unless cache exists.
            schedules[agent_id] = generate_schedule(a)
            save_agent_schedule(agent_id, schedules[agent_id])

        cached_actions = load_agent_actions(agent_id)
        if cached_actions:
            actions[agent_id] = {
                activity: _ensure_behavioral_action_balance(activity, acts)
                for activity, acts in cached_actions.items()
            }
        else:
            # Action space is expensive; cache for reuse across runs.
            base_actions = generate_actions(a, schedules[agent_id])
            actions[agent_id] = build_action_space_for_agent(a, base_actions)
        save_agent_actions(agent_id, actions[agent_id])

    # Print each agent's base routine at the beginning of the simulation.
    for agent in agents:
        sch = schedules.get(agent["id"], [])
        lines = [f"{t} {act}" for t, act in sch] if sch else ["(no schedule)"]
        routine_text = "\n".join(lines)
        header = f"\n[BasicRoutine] {agent.get('name', agent['id'])}\n"
        print(header + routine_text)
        append_agent_log(agent, header + routine_text + "\n")

    base_schedule_map = build_schedule_map(schedules)
    validate_action_space(schedules, actions)

    # Snapshot per-agent state at sim start so the end-of-run summary can
    # diff state / growth / schedule / relationships against the agent's
    # initial profile. Kept lightweight (deep-copies only the fields the
    # summary needs). See ``gaworld/sim/_summary.py``.
    initial_snapshots = {
        a["id"]: take_initial_snapshot(a, schedule=schedules.get(a["id"]))
        for a in agents
    }
    # Real-work runtime: bootstrap capabilities + queue + market + workers.
    # Returns None when CONFIG.real_work.enabled is False, in which case
    # all real-work code paths are no-ops.
    real_work_runtime = RealWorkRuntime.create(CONFIG, agents, llm_fn=call_llm)
    if real_work_runtime is not None:
        real_work_runtime.start()
    hook_bus.emit(
        "on_simulation_start",
        config=CONFIG,
        agents=agents,
        agents_by_id=agents_by_id,
        city_map=city_map,
        city_map_text=city_map_text,
        schedules=schedules,
        actions=actions,
        extension_state=extension_state,
    )

    # ----- PHASE 3: DAY LOOP — runs once per simulated day -----
    for day in range(start_day, start_day + SIM_DAYS):
        # ----- PHASE 3a: Per-day setup (real-work tick, day context, schedule/routine generation, action space) -----
        if real_work_runtime is not None:
            real_work_runtime.tick_day(day)
        day_context = _resolve_day_context(
            day,
            start_weekday_idx=SIM_START_WEEKDAY_INDEX,
            weekend_indexes=SIM_WEEKEND_INDEXES,
            start_date=SIM_START_DATE,
        )
        day_desc = (
            f"{day_context.get('sim_date', '')} "
            f"{day_context.get('weekday_zh', '周一')} "
            f"{day_context.get('day_type_zh', '工作日')}"
        ).strip()
        print(f"\n================= Day {day} ({day_desc}) =================")
        if distributed_client.enabled:
            distributed_client.refresh_directory()
        if HUMAN_REALISM_ENABLED:
            for _a in agents:
                _maybe_inject_ghost_event(_a, day, "08:30")
        daily_logs = defaultdict(str)
        day_env_events = env_system.start_day(day, day_context=day_context, agents=agents)
        day_env_context = env_system.get_day_context_text()
        append_jsonl(
            env_timeline_path,
            {
                "scope": "day",
                "day": int(day),
                "date": day_context.get("sim_date", ""),
                "summary": day_env_context,
                "events": day_env_events,
            },
        )
        if day_env_events:
            env_lines = "\n".join(f"- {_format_external_env_event(ev)}" for ev in day_env_events)
            env_header = f"\n[ExternalEnvironment Day {day} {day_desc}]\n{env_lines}\n"
            print(env_header.strip())
            for agent in agents:
                daily_logs[agent["id"]] += env_header
                append_agent_log(agent, env_header)
                vector_db_add_entry(
                    agent["id"],
                    "external_env",
                    env_header.strip(),
                    sim_day=day,
                    sim_time="day_start",
                )
        llm_budget_by_agent = {}
        daily_schedules = {}
        daily_routine_texts = {}
        daily_wake_times = {}
        daily_routine_logged = {}
        if HUMAN_REALISM_ENABLED:
            max_extra = int(
                HUMAN_REALISM_CONFIG.get("llm", {}).get("max_extra_calls_per_agent_day", 2)
            )
            for agent in agents:
                agent["current_day"] = day
                budget = {"remaining": max(0, max_extra)}
                llm_budget_by_agent[agent["id"]] = budget
                episodes = sorted(
                    agent.get("episodes", []),
                    key=lambda x: float(x.get("decayed_salience", x.get("salience", 0.0))),
                    reverse=True,
                )
                intentions = build_daily_intentions(
                    agent,
                    episodes,
                    HUMAN_REALISM_CONFIG,
                    budget,
                )
                intentions["day"] = day
                agent["intentions"] = intentions
                if STATEFUL:
                    save_agent_intentions(agent["id"], intentions)
        # Daily routine generation is one LLM call per agent and the
        # only cross-agent state it touches is `actions[agent_id]`,
        # which is keyed by id (no aliasing across agents). It is the
        # safest concurrency point in the main loop, so we route it
        # through gaworld.core.runner.parallel_map. Default is serial:
        # set CONFIG["concurrency"]["day_routine_workers"] > 1 to opt in.
        # Per-agent IO (save_agent_actions, log writes) is left in the
        # serial merge phase below to keep the SQLite + log file
        # writers single-writer for now.
        def _compute_daily_routine(agent):
            agent_id = agent["id"]
            daily_schedule = generate_daily_routine(
                agent,
                base_schedule_map[agent_id],
                day=day,
                day_context=day_context,
            )
            updated = False
            new_actions = actions[agent_id]
            for _, activity in daily_schedule:
                updated = ensure_action_space_for_activity(agent, new_actions, activity) or updated
            return agent_id, daily_schedule, updated

        _routine_workers = resolve_max_workers(
            CONFIG, key="day_routine_workers", default=1
        )
        _routine_results = parallel_map(
            _compute_daily_routine,
            agents,
            max_workers=_routine_workers,
            label="day_routine",
        )

        # Serial merge phase: ordering matters for log files / save calls.
        for agent_id, daily_schedule, action_space_updated in _routine_results:
            daily_schedules[agent_id] = daily_schedule
            if action_space_updated and STATEFUL:
                save_agent_actions(agent_id, actions[agent_id])
            lines = [f"{t} {act}" for t, act in daily_schedule] if daily_schedule else ["(no schedule)"]
            routine_text = "\n".join(lines)
            daily_routine_texts[agent_id] = routine_text
            wake_time = None
            for t, act in daily_schedule:
                if not is_sleep_activity(act):
                    wake_time = t
                    break
            daily_wake_times[agent_id] = wake_time or (daily_schedule[0][0] if daily_schedule else None)
            daily_routine_logged[agent_id] = False

        schedule_map = build_schedule_map(daily_schedules)
        timeline = build_master_timeline(daily_schedules, TIME_STEP_MINUTES)
        sleep_step = SECONDS_PER_DAY / (SIM_DAYS * max(len(timeline), 1))
        info_schedule = {}
        curiosity_budget = {}
        daily_info_seen = defaultdict(set)
        daily_query_seen = defaultdict(set)
        preferred_sites_map = {}
        if NEWS_ENABLED and timeline:
            for agent in agents:
                agent_id = agent["id"]
                preferred_sites = _build_agent_preferred_sites(
                    agent,
                    news_sources=news_sources,
                    news_cache=news_cache,
                    max_sites=int(INFO_SEEK_CONFIG.get("preferred_sites_per_agent", 6)),
                )
                preferred_sites_map[agent_id] = preferred_sites
                agent["preferred_info_sites"] = preferred_sites
                curiosity = _estimate_curiosity(agent)
                ev_cfg = INFO_SEEK_CONFIG.get("event_driven", {})
                curiosity_budget[agent["id"]] = int(ev_cfg.get("max_extra_seeks_per_day", 2))
                if not INFO_SEEK_ENABLED:
                    continue
                daily_chance = min(0.98, INFO_SEEK_BASE_CHANCE * curiosity + 0.05)
                if random.random() > daily_chance:
                    continue
                max_seeks = max(1, int(round(INFO_SEEK_MAX_PER_DAY * curiosity)))
                seeks = min(max_seeks, len(timeline))
                info_schedule[agent_id] = set(random.sample(timeline, k=seeks))

        day_header = f"\n================= Day {day} ({day_desc}) =================\n"
        for agent in agents:
            daily_logs[agent["id"]] += day_header
            append_agent_log(agent, day_header)
            # Reset daily travel cost counter
            if "locations" in agent:
                agent["locations"]["daily_travel_cost"] = 0.0
            # P4: decay learned location-aversion by recency at each day start.
            if SPATIAL_PREF_ENABLED:
                decay_env_preferences(agent, day, half_life_days=SPATIAL_PREF_HALF_LIFE)
                if STATEFUL:
                    save_agent_env_preferences(agent["id"], agent.get("env_preferences", {}))
        hook_bus.emit(
            "on_day_start",
            day=day,
            config=CONFIG,
            agents=agents,
            agents_by_id=agents_by_id,
            city_map=city_map,
            city_map_text=city_map_text,
            schedule_map=schedule_map,
            actions=actions,
            timeline=timeline,
            daily_logs=daily_logs,
            env_events=day_env_events,
            env_context=day_env_context,
            extension_state=extension_state,
        )

        # ----- PHASE 3b: STEP LOOP — the megaloop, runs once per timeline tick (default 10-30 min steps) -----
        for time_index, time_str in enumerate(timeline):
            step_minutes = _timeline_step_minutes(timeline, time_index)
            policy = next((p for p in POLICY_EVENTS if p["day"] == day and p["time"] == time_str), None)
            due_life_events = drain_due_life_events(day, time_str, CONFIG)
            env_system.tick(day, time_str, agents)
            env_events = env_system.get_events()
            env_context = env_system.get_context_text()
            # P0: refresh the city map's physical state so agents can perceive
            # their actual surroundings (crowding / opening hours) this tick.
            if LOCAL_PHYSICAL_ENABLED and city_map:
                set_sim_time(city_map, time_str)
                update_occupancy_from_agents(city_map, agents)
            frame_steps = []
            if due_life_events:
                append_jsonl(
                    env_timeline_path,
                    {
                        "scope": "life_event",
                        "day": int(day),
                        "date": day_context.get("sim_date", ""),
                        "time": str(time_str),
                        "events": due_life_events,
                    },
                )
            if env_events:
                append_jsonl(
                    env_timeline_path,
                    {
                        "scope": "tick",
                        "day": int(day),
                        "date": day_context.get("sim_date", ""),
                        "time": str(time_str),
                        "events": env_events,
                    },
                )
            if background_text:
                env_context = f"背景：{background_text} 当前环境事件：{env_context}"
            hook_bus.emit(
                "on_time_tick",
                day=day,
                time_str=time_str,
                config=CONFIG,
                agents=agents,
                agents_by_id=agents_by_id,
                city_map=city_map,
                city_map_text=city_map_text,
                schedule_map=schedule_map,
                actions=actions,
                daily_logs=daily_logs,
                env_events=env_events,
                env_context=env_context,
                policy=policy,
                extension_state=extension_state,
            )

            distributed_inbox = {}
            if distributed_client.enabled:
                distributed_inbox = distributed_client.poll_messages(
                    local_agent_ids=[a["id"] for a in agents],
                    day=day,
                    time_str=time_str,
                )

            for agent in agents:
                agent_id = agent["id"]
                if (
                    not daily_routine_logged.get(agent_id)
                    and daily_wake_times.get(agent_id) == time_str
                ):
                    header = (
                        f"\n[TodayRoutine Day {day} {day_desc}] "
                        f"{agent.get('name', agent_id)} @ {time_str}\n"
                    )
                    routine_text = daily_routine_texts.get(agent_id, "")
                    print(header + routine_text)
                    daily_logs[agent_id] += header + routine_text + "\n"
                    append_agent_log(agent, header + routine_text + "\n")
                    daily_routine_logged[agent_id] = True
                if time_str in info_schedule.get(agent_id, set()):
                    scheduled_keywords = None
                    if INFO_SEEK_CONFIG.get("contextual_keywords", True):
                        _ctx = assemble_curiosity_context(
                            agent,
                            scheduled_activity=get_activity_for_time(schedule_map[agent_id], time_str),
                            recent_events=[
                                _format_external_env_event(ev) for ev in (env_events or [])
                            ],
                            day=day,
                            time_str=time_str,
                        )
                        scheduled_keywords = propose_contextual_keywords(
                            agent, _ctx, config=INFO_SEEK_CONFIG
                        ) or None
                    _, info_log, result_url, query = info_seek_and_store(
                        agent,
                        day=day,
                        time_str=time_str,
                        news_cache=news_cache,
                        news_sources=news_sources,
                        preferred_sites=preferred_sites_map.get(agent_id, []),
                        seen_urls=daily_info_seen[agent_id],
                        used_queries=daily_query_seen[agent_id],
                        keywords=scheduled_keywords,
                        config=INFO_SEEK_CONFIG,
                    )
                    if query:
                        daily_query_seen[agent_id].add(query)
                    if result_url:
                        daily_info_seen[agent_id].add(result_url)
                    if info_log:
                        print(info_log)
                        daily_logs[agent_id] += info_log
                        append_agent_log(agent, info_log)
                _maybe_curiosity_seek(
                    agent,
                    day=day,
                    time_str=time_str,
                    scheduled_activity=get_activity_for_time(schedule_map[agent_id], time_str),
                    recent_events=[
                        _format_external_env_event(ev) for ev in (env_events or [])
                    ],
                    news_cache=news_cache,
                    news_sources=news_sources,
                    preferred_sites=preferred_sites_map.get(agent_id, []),
                    seen_urls=daily_info_seen[agent_id],
                    used_queries=daily_query_seen[agent_id],
                    curiosity_budget=curiosity_budget,
                    config=INFO_SEEK_CONFIG,
                    daily_logs=daily_logs,
                )
                if env_events:
                    for ev in env_events:
                        vector_db_add_entry(
                            agent_id,
                            "external_env",
                            f"[ExternalEnvironment Day {day} {time_str}] {_format_external_env_event(ev)}",
                            sim_day=day,
                            sim_time=time_str,
                        )
                agent_life_events = life_events_for_agent(due_life_events, agent_id)
                if agent_life_events:
                    _record_life_events_for_agent(
                        agent,
                        agent_life_events,
                        day,
                        time_str,
                        daily_logs,
                    )
                agent_env_events = list(env_events or []) + [
                    _life_event_as_env_event(event) for event in agent_life_events
                ]
                #act = random.choice(actions.get(activity, ["继续当前活动"]))
                scheduled_activity = get_activity_for_time(schedule_map[agent_id], time_str)
                inbox_messages = distributed_inbox.get(agent_id, [])
                social_context = get_social_context(agent, agents_by_id)
                inbox_context = format_inbox_context(
                    inbox_messages,
                    max_items=int(DISTRIBUTED_CONFIG.get("max_inbound_per_step", 3)),
                )
                if inbox_context:
                    social_context = f"{social_context} {inbox_context}".strip()
                    inbox_log = f"[DistributedInbox {agent['name']} @ {time_str}] {inbox_context}\n"
                    daily_logs[agent_id] += inbox_log
                    append_agent_log(agent, inbox_log)
                    vector_db_add_entry(
                        agent_id,
                        "distributed_in",
                        inbox_context,
                        sim_day=day,
                        sim_time=time_str,
                    )

                policy_desc = None
                if policy:
                    policy_desc = policy.get("description") or policy.get("name")
                state_before = dict(agent.get("state", {}))
                step_ctx = {
                    "scheduled_activity": scheduled_activity,
                    "activity": scheduled_activity,
                    "social_context": social_context,
                    "policy_desc": policy_desc,
                    "life_events": agent_life_events,
                }
                hook_bus.emit(
                    "on_agent_pre_step",
                    day=day,
                    time_str=time_str,
                    config=CONFIG,
                    agent=agent,
                    agents=agents,
                    agents_by_id=agents_by_id,
                    city_map=city_map,
                    city_map_text=city_map_text,
                    schedule_map=schedule_map,
                    actions=actions,
                    env_events=agent_env_events,
                    env_context=env_context,
                    policy=policy,
                    step=step_ctx,
                    extension_state=extension_state,
                )
                scheduled_activity = step_ctx.get("scheduled_activity", scheduled_activity)
                social_context = step_ctx.get("social_context", social_context)
                policy_desc = step_ctx.get("policy_desc", policy_desc)
                intervention_feed = {}
                step_env_context = env_context
                life_event_context = _format_life_event_context(agent_life_events)
                if life_event_context:
                    step_env_context = (
                        f"{step_env_context}\n{life_event_context}"
                        if step_env_context
                        else life_event_context
                    )
                if INTERVENTION_ENABLED:
                    intervention_feed = build_intervention_feed(
                        agent,
                        agents_by_id=agents_by_id,
                        day=day,
                        time_str=time_str,
                        env_events=agent_env_events,
                        policy_event=policy or policy_desc,
                        news_items=news_cache[:5],
                        config=INTERVENTION_CONFIG,
                    )
                    feed_context = intervention_feed.get("context_text", "")
                    if feed_context:
                        step_env_context = (
                            f"{env_context}\n平台干预推荐：{feed_context}"
                            if env_context
                            else f"平台干预推荐：{feed_context}"
                        )
                        step_ctx["intervention_feed"] = intervention_feed
                # P0: localized physical snapshot of the agent's *current*
                # surroundings (crowding / open-closed / local weather).
                # Stored on the agent so later behaviour stages can read it.
                if LOCAL_PHYSICAL_ENABLED:
                    local_physical = local_physical_state(
                        city_map,
                        agent,
                        time_str=time_str,
                        weather_state=_env_weather_state(env_system),
                        busy_ratio=LOCAL_PHYSICAL_BUSY_RATIO,
                        packed_ratio=LOCAL_PHYSICAL_PACKED_RATIO,
                        anomaly_ratio=LOCAL_PHYSICAL_ANOMALY_RATIO,
                        anomaly_jump=LOCAL_PHYSICAL_ANOMALY_JUMP,
                    )
                    agent["_local_physical"] = local_physical
                    if LOCAL_PHYSICAL_INJECT:
                        _lp_text = physical_state_text(local_physical)
                        if _lp_text:
                            step_env_context = (
                                f"{step_env_context}\n身边的物理环境：{_lp_text}"
                                if step_env_context
                                else f"身边的物理环境：{_lp_text}"
                            )
                else:
                    agent["_local_physical"] = {}
                # Core cognition loop: perceive -> plan -> (maybe) change routine -> act -> reflect.
                perc = perception(agent, time_str, social_context, step_env_context, policy_desc if policy else None)
                # --- Dynamic behaviour system (replaces old transient thought) ---
                _use_dynamic = CONFIG.get("dynamic_behavior", {}).get("enabled", True)
                if _use_dynamic:
                    transient_thought = dynamic_transient_thought(
                        agent,
                        time_str,
                        scheduled_activity,
                        perception_text=perc,
                        env_events=agent_env_events,
                        policy_desc=policy_desc,
                        social_context=social_context,
                        inbox_messages=inbox_messages,
                        all_agents=agents,
                        agents_by_id=agents_by_id,
                        config=CONFIG,
                    )
                else:
                    transient_thought = maybe_generate_transient_thought(
                        agent,
                        time_str,
                        scheduled_activity,
                        perc,
                        env_events=agent_env_events,
                        policy_desc=policy_desc,
                        social_context=social_context,
                        inbox_messages=inbox_messages,
                    )
                step_recollections = []
                plan_commitment = _activity_commitment_level(scheduled_activity)
                plan_prefetch_refs = _build_decision_reference_bundle(
                    agent,
                    scheduled_activity,
                    time_str=time_str,
                    location=agent.get("locations", {}).get("current", ""),
                    env_context=step_env_context,
                    env_events=agent_env_events,
                    policy_desc=policy_desc,
                    social_context=social_context,
                )
                plan_recall = evoke_memory(
                    agent,
                    "planning",
                    scheduled_activity,
                    perc,
                    social_context if plan_prefetch_refs.get("social_network_relevant") else "",
                    plan_prefetch_refs.get("physical_env_text", "") if plan_prefetch_refs.get("physical_env_relevant") else "",
                    plan_prefetch_refs.get("social_env_text", "") if plan_prefetch_refs.get("social_env_relevant") else "",
                    context_labels=_build_recall_context_labels(
                        agent,
                        activity=scheduled_activity,
                        time_str=time_str if plan_prefetch_refs.get("location_time_relevant") else "",
                        location=agent.get("locations", {}).get("current", "") if plan_prefetch_refs.get("location_time_relevant") else "",
                        commitment_level=plan_commitment,
                    ),
                )
                if plan_recall.get("recollection"):
                    step_recollections.append(plan_recall["recollection"])
                plan_refs = dict(plan_prefetch_refs)
                plan_refs["memory_hint"] = plan_recall.get("hint", "")
                plan_refs["recollection"] = plan_recall.get("recollection", "")
                plan_refs["transient_thought"] = transient_thought
                plan = planning(agent, perc, recall_context=plan_recall, decision_refs=plan_refs)
                plan_text = format_plan_text(plan)
                activity, change_reason, changed = maybe_adjust_activity(
                    agent,
                    time_str,
                    scheduled_activity,
                    perc,
                    plan_text,
                    step_env_context,
                    agent_env_events,
                    policy_desc,
                    transient_thought=transient_thought,
                    social_context=social_context,
                )
                # --- Dynamic behaviour system: apply if LLM didn't change ---
                _dyn_result = transient_thought.get("dynamic_result") if isinstance(transient_thought, dict) else None
                if _dyn_result and not changed and _dyn_result.get("changed"):
                    activity = _dyn_result["activity"]
                    change_reason = _dyn_result.get("reason", "动态行为系统触发")
                    changed = True
                # Apply mood delta from dynamic system
                if _dyn_result and _dyn_result.get("mood_delta"):
                    _mood_d = float(_dyn_result["mood_delta"])
                    state = agent.get("state", {})
                    state["emotion"] = max(0.0, min(1.0, float(state.get("emotion", 0.5)) + _mood_d))
                # Apply schedule insertion from dynamic system
                if _dyn_result and _dyn_result.get("schedule_insert") and changed:
                    _si = _dyn_result["schedule_insert"]
                    _sched_tuples = [(s.get("time", ""), s.get("activity", "")) if isinstance(s, dict) else s
                                     for s in schedule_map.get(agent_id, [])]
                    _new_sched = dynamic_insert_activity(
                        _sched_tuples,
                        _si["insert_time"],
                        _si["activity"],
                        duration_minutes=_si.get("duration_minutes", 30),
                        resumable=True,
                        original_activity=_si.get("original_activity", scheduled_activity),
                    )
                    # Convert back to schedule format used by the simulator
                    schedule_map[agent_id] = [{"time": t, "activity": a} for t, a in _new_sched]
                # Log social encounters from dynamic system
                if _dyn_result and _dyn_result.get("social_encounters"):
                    for _enc in _dyn_result["social_encounters"]:
                        _LOG.debug("agent_%s social_encounter: %s", agent_id, _enc.get("activity", ""))

                activity = step_ctx.get("activity", activity)
                if activity != scheduled_activity and not changed:
                    changed = True
                    hook_reason = str(step_ctx.get("change_reason", "")).strip()
                    if hook_reason:
                        change_reason = hook_reason
                if changed:
                    schedule_map[agent_id] = apply_schedule_override(
                        schedule_map[agent_id],
                        time_str,
                        activity,
                    )
                    updated = ensure_action_space_for_activity(agent, actions[agent_id], activity)
                    if updated and STATEFUL:
                        save_agent_actions(agent_id, actions[agent_id])

                # P3: a *persistent* anomaly (non-resumable physical / emergency
                # reaction) makes the disrupted activity unworkable for a while —
                # defer its upcoming slots rather than only patching this step.
                if REPLAN_ENABLED and changed and isinstance(_dyn_result, dict):
                    _itr = _dyn_result.get("interrupt") or {}
                    _extra = _itr.get("extra", {}) if isinstance(_itr, dict) else {}
                    _persistent_anomaly = (
                        isinstance(_itr, dict)
                        and not _itr.get("resumable", True)
                        and (bool(_extra.get("anomaly"))
                             or _extra.get("event_type") in ("emergency", "local_physical"))
                    )
                    # P4: learn to avoid a *place* only for location-bound
                    # anomalies (crowd surge / closed venue) — never for
                    # city-wide macro anomalies, which aren't a place's fault.
                    if (SPATIAL_PREF_ENABLED and _persistent_anomaly
                            and _extra.get("event_type") == "local_physical"
                            and _extra.get("location")):
                        record_anomaly_experience(
                            agent,
                            location=str(_extra.get("location")),
                            day=day,
                            weight=SPATIAL_PREF_WEIGHT,
                            reason=str(_itr.get("kind", "")),
                            time_str=time_str,
                        )
                        if STATEFUL:
                            save_agent_env_preferences(agent_id, agent.get("env_preferences", {}))
                    _cur_min = _time_str_to_minutes(time_str)
                    if _persistent_anomaly and scheduled_activity and _cur_min is not None:
                        _sched_tuples = [
                            (s.get("time", ""), s.get("activity", "")) if isinstance(s, dict) else tuple(s)
                            for s in schedule_map.get(agent_id, [])
                        ]
                        _new_sched, _replan_changes = replan_affected_interval(
                            _sched_tuples,
                            time_str,
                            _minutes_to_time_str(min(24 * 60 - 1, _cur_min + REPLAN_WINDOW_MINUTES)),
                            is_affected=lambda t, a, _d=scheduled_activity: a == _d,
                            defer=True,
                            defer_gap_minutes=REPLAN_DEFER_GAP,
                        )
                        if _replan_changes:
                            schedule_map[agent_id] = _new_sched
                            _replan_log = (
                                f"[Replan {time_str}] 因突发异常重排日程，"
                                f"顺延 {len(_replan_changes)} 项（{scheduled_activity}）\n"
                            )
                            daily_logs[agent_id] += _replan_log
                            append_agent_log(agent, _replan_log)

                desired_location = resolve_location(agent, activity, time_str, city_map)
                # P4: bias away from places the agent has learned to avoid.
                if SPATIAL_PREF_ENABLED and desired_location:
                    desired_location, _redirected = redirect_for_aversion(
                        agent, city_map, desired_location, time_str,
                        threshold=SPATIAL_PREF_THRESHOLD,
                    )
                movement = move_agent(
                    agent,
                    desired_location=desired_location,
                    activity=activity,
                    time_str=time_str,
                    step_minutes=step_minutes,
                    city_map=city_map,
                )
                if STATEFUL:
                    persist_agent_locations_if_changed(agent)
                location = movement["display_location"]
                resolved_location = movement["resolved_location"]
                travel = movement["travel"]
                effective_activity = activity
                if travel.get("status") in {"departed", "in_transit"}:
                    act = f"乘坐{travel.get('mode', '交通工具')}移动"
                    action_meta = {
                        "decision_driver": "时空约束",
                        "commitment_level": _activity_commitment_level(activity),
                        "scores": {act: {"weight": 1.0, "components": {}, "styles": ["quick"]}},
                    }
                    outcome = (
                        f"从【{resolved_location}】前往【{movement['target_location']}】，"
                        f"使用【{travel.get('mode', '未知方式')}】，路程约 {travel.get('distance_km', 0.0):.1f} km，"
                        f"预计 {travel.get('minutes', 0)} 分钟"
                    )
                    location_bias = {}
                    effective_activity = f"前往{movement['target_location']}"
                else:
                    location_bias = get_location_action_bias(
                        agent,
                        resolved_location,
                        city_map_text,
                        actions[agent_id],
                    )
                    location_time_relevant = _is_location_time_relevant(activity, time_str=time_str, location=resolved_location)
                    action_prefetch_refs = _build_decision_reference_bundle(
                        agent,
                        activity,
                        time_str=time_str,
                        location=resolved_location,
                        env_context=step_env_context,
                        env_events=agent_env_events,
                        policy_desc=policy_desc,
                        social_context=social_context,
                    )
                    action_recall = evoke_memory(
                        agent,
                        "action",
                        activity,
                        perc,
                        plan_text,
                        social_context if action_prefetch_refs.get("social_network_relevant") else "",
                        action_prefetch_refs.get("physical_env_text", "") if action_prefetch_refs.get("physical_env_relevant") else "",
                        action_prefetch_refs.get("social_env_text", "") if action_prefetch_refs.get("social_env_relevant") else "",
                        resolved_location if location_time_relevant else "",
                        time_str if location_time_relevant else "",
                        context_labels=_build_recall_context_labels(
                            agent,
                            activity=activity,
                            time_str=time_str if location_time_relevant else "",
                            location=resolved_location if location_time_relevant else "",
                            commitment_level=_activity_commitment_level(activity),
                        ),
                    )
                    if action_recall.get("recollection"):
                        step_recollections.append(action_recall["recollection"])
                    action_refs = dict(action_prefetch_refs)
                    action_refs["memory_hint"] = action_recall.get("hint", "")
                    action_refs["recollection"] = action_recall.get("recollection", "")
                    action_refs["transient_thought"] = transient_thought
                    act, action_meta = choose_action(
                        agent,
                        activity,
                        actions[agent_id],
                        context=f"{activity} {perc} {plan_text}",
                        location_bias=location_bias,
                        location=resolved_location,
                        time_str=time_str,
                        recall_context=action_recall,
                        decision_refs=action_refs,
                        return_debug=True,
                    )
                    outcome = f"在【{activity}】中执行了【{act}】"
                    if real_work_runtime is not None:
                        rw_outcome = real_work_runtime.router.maybe_dispatch(
                            agent, activity=activity, chosen_action=act,
                            sim_day=day, sim_time=time_str,
                        )
                        if rw_outcome:
                            outcome = rw_outcome
                        rw_done = real_work_runtime.absorb_for(
                            agent, sim_day=day, sim_time=time_str,
                        )
                        if rw_done:
                            outcome = f"{outcome}｜回收：{_rw_summarise(rw_done)}"
                reflection_recall = evoke_memory(
                    agent,
                    "reflection",
                    effective_activity,
                    act,
                    outcome,
                    time_str if _is_location_time_relevant(effective_activity, time_str=time_str, location=resolved_location) else "",
                    context_labels=_build_recall_context_labels(
                        agent,
                        activity=effective_activity,
                        time_str=time_str if _is_location_time_relevant(effective_activity, time_str=time_str, location=resolved_location) else "",
                        location=resolved_location if _is_location_time_relevant(effective_activity, time_str=time_str, location=resolved_location) else "",
                        commitment_level=action_meta.get("commitment_level", _activity_commitment_level(effective_activity)),
                    ),
                )
                if reflection_recall.get("recollection"):
                    step_recollections.append(reflection_recall["recollection"])
                refl = reflection(agent, outcome, recall_context=reflection_recall)
                refl_text = format_reflection_text(refl)
                if HUMAN_REALISM_ENABLED:
                    update_needs(
                        agent,
                        time_str,
                        effective_activity,
                        cfg=HUMAN_REALISM_CONFIG,
                        changed=changed,
                        travel=travel,
                    )

                if agent_env_events:
                    for ev in agent_env_events:
                        inferred = infer_event_effect(agent, ev.get("description", ev.get("name", "")), ev.get("type", "event"))
                        for k, v in inferred.items():
                            agent["state"][k] += v
                if agent_life_events:
                    _apply_life_event_state_effects(agent, agent_life_events)

                if policy:
                    inferred = infer_event_effect(agent, policy_desc, "policy")
                    for k, v in inferred.items():
                        agent["state"][k] += v

                social_influence(agent, agents_by_id)
                update_state(agent)
                intervention_metrics = {}
                if INTERVENTION_ENABLED:
                    intervention_metrics = update_agent_intervention_metrics(
                        agent,
                        feed=intervention_feed,
                        action=act,
                        outcome=outcome,
                        reflection=refl_text,
                        agents_by_id=agents_by_id,
                        config=INTERVENTION_CONFIG,
                    )
                    source_counts = intervention_feed.get("source_counts", {}) if isinstance(intervention_feed, dict) else {}
                    append_intervention_metrics(
                        INTERVENTION_OUTPUT_DIR,
                        {
                            "day": day,
                            "time": time_str,
                            "agent_id": agent_id,
                            "feed_items": len(intervention_feed.get("items", [])) if isinstance(intervention_feed, dict) else 0,
                            "relational_items": source_counts.get("relational", 0),
                            "personalized_items": source_counts.get("personalized", 0),
                            "headline_items": source_counts.get("headline", 0),
                            **intervention_metrics,
                        },
                    )
                sent_remote_messages = []
                if distributed_client.enabled:
                    sent_remote_messages = distributed_client.send_agent_messages(
                        agent,
                        day=day,
                        time_str=time_str,
                        activity=effective_activity,
                        reflection=refl_text,
                        outcome=outcome,
                    )
                    if sent_remote_messages:
                        sent_summary = "; ".join(
                            f"to#{int(msg.get('to_agent', 0))}:{str(msg.get('text', ''))[:40]}"
                            for msg in sent_remote_messages
                            if isinstance(msg, dict)
                        )
                        if sent_summary:
                            sent_log = (
                                f"[DistributedOutbox {agent['name']} @ {time_str}] "
                                f"{sent_summary}\n"
                            )
                            daily_logs[agent_id] += sent_log
                            append_agent_log(agent, sent_log)
                            vector_db_add_entry(
                                agent_id,
                                "distributed_out",
                                sent_summary,
                                sim_day=day,
                                sim_time=time_str,
                            )
                if HUMAN_REALISM_ENABLED:
                    partners = list(agent.get("_recent_social_partners", []))
                    for sender_id in extract_sender_agent_ids(inbox_messages):
                        if sender_id not in partners:
                            partners.append(sender_id)
                    signal = infer_interaction_signal(refl_text)
                    for pid in partners:
                        relationship_update(agent, pid, signal, HUMAN_REALISM_CONFIG)
                    state_after = dict(agent.get("state", {}))
                    delta = {}
                    for key, before_v in state_before.items():
                        after_v = state_after.get(key)
                        if isinstance(before_v, (int, float)) and isinstance(after_v, (int, float)):
                            delta[key] = float(after_v) - float(before_v)
                    thought_intensity = (
                        float(transient_thought.get("intensity", 0.0))
                        if isinstance(transient_thought, dict)
                        else 0.0
                    )
                    event_intensity = min(
                        1.0,
                        0.2 * len(agent_env_events) + (0.2 if policy else 0.0) + 0.18 * thought_intensity,
                    )
                    recent_actions = [
                        e.get("action", "")
                        for e in agent.get("episodes", [])[-20:]
                        if isinstance(e, dict)
                    ]
                    novelty = 1.0 if act not in recent_actions else 0.2
                    priorities = agent.get("intentions", {}).get("priorities", [])
                    goal_relevance = 0.2
                    for p in priorities:
                        if p and (p in effective_activity or p in plan_text or p in refl_text):
                            goal_relevance = 0.8
                            break
                    salience = compute_episode_salience(
                        delta.get("stress", 0.0),
                        event_intensity,
                        novelty,
                        goal_relevance,
                    )
                    tags = infer_episode_tags(
                        effective_activity,
                        act,
                        refl_text,
                        env_events=[ev.get("description", ev.get("name", "")) for ev in agent_env_events],
                        policy_event=policy_desc if policy else "",
                    )
                    need_snapshot = {
                        "energy": round(float(state_after.get("energy", 0.75)), 3),
                        "hunger": round(float(state_after.get("hunger", 0.25)), 3),
                        "social_need": round(float(state_after.get("social_need", 0.40)), 3),
                        "fatigue_debt": round(float(state_after.get("fatigue_debt", 0.20)), 3),
                        "self_control": round(float(state_after.get("self_control", 0.60)), 3),
                        "time_pressure": round(float(state_after.get("time_pressure", 0.25)), 3),
                    }
                    episode = {
                        "episode_id": str(uuid.uuid4()),
                        "day": day,
                        "time": time_str,
                        "scheduled_activity": scheduled_activity,
                        "final_activity": effective_activity,
                        "action": act,
                        "location": location,
                        "target_location": movement["target_location"],
                        "travel": travel,
                        "env_events": [ev.get("description", ev.get("name", "")) for ev in agent_env_events],
                        "life_events": [dict(event) for event in agent_life_events],
                        "policy_event": policy_desc if policy else "",
                        "social_partners": partners,
                        "perception": perc,
                        "plan": plan_text,
                        "plan_struct": plan,
                        "outcome": outcome,
                        "reflection": refl_text,
                        "reflection_struct": refl,
                        "transient_thought": transient_thought or {},
                        "state_before": state_before,
                        "state_after": state_after,
                        "need_snapshot": need_snapshot,
                        "delta": delta,
                        "tags": tags,
                        "recollections": list(step_recollections),
                        "salience": salience,
                        "valence": float(np.clip(delta.get("emotion", 0.0), -1.0, 1.0)),
                        "decision_driver": action_meta.get("decision_driver", "惯性延续"),
                        "change_reason": change_reason or "",
                        "commitment_level": action_meta.get("commitment_level", _activity_commitment_level(effective_activity)),
                        "expected_outcome": str(plan.get("expected_outcome", "")).strip(),
                        "created_at_day": day,
                    }
                    if INTERESTS_ENABLED:
                        progress_minutes = step_minutes
                        if INTERESTS_PROGRESS_MINUTES is not None:
                            parsed_minutes = _parse_step_minutes(INTERESTS_PROGRESS_MINUTES)
                            if parsed_minutes is not None:
                                progress_minutes = parsed_minutes
                        updated_growth, growth_progress = update_growth_from_episode(
                            agent.get("growth_profile"),
                            episode,
                            step_minutes=progress_minutes,
                        )
                        agent["growth_profile"] = updated_growth
                        episode["growth_matches"] = list(growth_progress.get("matches", []))
                        episode["growth_progress"] = growth_progress
                        if STATEFUL:
                            save_agent_growth_profile(
                                agent_id,
                                agent.get("growth_profile", {}),
                                CONFIG.get("memory_dir", "output/memory"),
                            )
                    else:
                        episode["growth_matches"] = []
                        episode["growth_progress"] = {"matches": [], "minutes": 0, "level_changes": {}}
                    agent.setdefault("episodes", []).append(episode)
                    update_habits_from_episode(agent, episode, HUMAN_REALISM_CONFIG)
                    append_agent_episode(agent_id, episode)
                    episode_text = (
                        f"Day {day} {time_str} {effective_activity}/{act} @ {location} "
                        f"driver={episode['decision_driver']} commitment={episode['commitment_level']} "
                        f"thought={format_transient_thought(transient_thought) if transient_thought else 'none'} "
                        f"needs={json.dumps(need_snapshot, ensure_ascii=False)} "
                        f"tags={','.join(tags)} salience={salience:.2f} reflection={refl_text}"
                    )
                    vector_db_add_entry(agent_id, "episode", episode_text, sim_day=day, sim_time=time_str)
                    agent["last_activity"] = effective_activity
                    agent["last_action"] = act
                    memory_review = maybe_review_memories(
                        agent,
                        day,
                        time_str,
                        recent_episode=episode,
                        llm_budget_ctx=llm_budget_by_agent.get(agent_id),
                    )
                else:
                    memory_review = ""
                    agent["last_activity"] = effective_activity
                    agent["last_action"] = act
                agent["last_reflection"] = refl_text
                for metric in state_history[agent["id"]]:
                    state_history[agent["id"]][metric].append(agent["state"][metric])

                # --- activity header (fold RoutineChange into one line) ---
                if changed:
                    reason_text = change_reason or "临时改变"
                    _activity_header = f"{scheduled_activity} → {effective_activity} ({reason_text})"
                    routine_line = f"RoutineChange: {scheduled_activity} -> {effective_activity} ({reason_text})\n"
                else:
                    _activity_header = scheduled_activity
                    routine_line = ""

                # --- optional lines (only rendered when non-empty) ---
                recall_line = ""
                unique_recollections = []
                for item in step_recollections:
                    text = str(item).strip()
                    if text and text not in unique_recollections:
                        unique_recollections.append(text)
                if unique_recollections:
                    recall_line = f"Recall: {' | '.join(unique_recollections)}\n"
                transient_thought_line = ""
                if transient_thought:
                    transient_thought_line = f"Thought: {format_transient_thought(transient_thought)}\n"
                memory_review_line = f"Review: {memory_review}\n" if memory_review else ""
                decision_line = ""
                if action_meta.get("decision_driver"):
                    decision_line = (
                        f"Driver: {action_meta.get('decision_driver')} "
                        f"(commit={action_meta.get('commitment_level', '')})\n"
                    )
                needs_line = ""
                if HUMAN_REALISM_ENABLED:
                    needs_line = (
                        "Needs: "
                        f"nrg={agent['state'].get('energy', 0.75):.2f} "
                        f"hun={agent['state'].get('hunger', 0.25):.2f} "
                        f"soc={agent['state'].get('social_need', 0.40):.2f} "
                        f"fat={agent['state'].get('fatigue_debt', 0.20):.2f} "
                        f"ctrl={agent['state'].get('self_control', 0.60):.2f} "
                        f"tprs={agent['state'].get('time_pressure', 0.25):.2f}\n"
                    )

                # --- compact location + travel (collapsed to 1 line) ---
                _travel_status = travel.get("status", "stationary")
                if _travel_status != "stationary":
                    _travel_info = (
                        f"  [{travel.get('mode', '?')} "
                        f"{travel.get('distance_km', 0.0):.1f}km "
                        f"{travel.get('minutes', 0)}min]"
                    )
                    _loc_line = f"Loc: {location} → {resolved_location}{_travel_info}\n"
                else:
                    _travel_info = ""
                    _loc_line = f"Loc: {resolved_location}\n"

                # --- env context (omitted when empty) ---
                _env_line = f"Env: {step_env_context}\n" if step_env_context else ""

                # -------------------------------------------------------
                # Simple mode: one clean block per tick, Chinese-only,
                # stripping LLM reasoning leakage and repeated boilerplate.
                # Verbose mode: full details for debugging.
                # -------------------------------------------------------
                if _LOG_SIMPLE:
                    _env_simple = _clean_env_context(step_env_context)
                    _refl_simple = _clean_reflection(refl_text)
                    log = (
                        f"\n── [{agent['name']} @ {time_str}] {_activity_header} ──\n"
                        f"Loc: {resolved_location}{_travel_info}\n"
                        + (f"Env: {_env_simple}\n" if _env_simple else "")
                        + f"Act: {act}\n"
                        f"Refl: {_refl_simple}\n"
                    )
                else:
                    log = (
                        f"\n── [{agent['name']} @ {time_str}] {_activity_header} ──\n"
                        f"{_loc_line}"
                        f"{_env_line}"
                        f"Perc: {perc}\n"
                        f"Plan: {plan_text}\n"
                        f"{transient_thought_line}"
                        f"{recall_line}"
                        f"Act: {act}  |  Out: {outcome}\n"
                        f"{decision_line}"
                        f"{needs_line}"
                        f"Refl: {refl_text}\n"
                        f"{memory_review_line}"
                    )
                print(log)
                daily_logs[agent["id"]] += log
                append_agent_log(agent, log)
                vector_db_add_entry(agent["id"], "log", log, sim_day=day, sim_time=time_str)
                vector_db_add_entry(agent["id"], "plan", plan_text, sim_day=day, sim_time=time_str)
                vector_db_add_entry(agent["id"], "reflection", refl_text, sim_day=day, sim_time=time_str)
                vector_db_add_entry(agent["id"], "action", outcome, sim_day=day, sim_time=time_str)
                step_ctx.update({
                    "perception": perc,
                    "plan": plan_text,
                    "plan_struct": plan,
                    "transient_thought": transient_thought or {},
                    "activity": effective_activity,
                    "action": act,
                    "outcome": outcome,
                    "reflection": refl_text,
                    "reflection_struct": refl,
                    "log": log,
                    "env_context": step_env_context,
                    "intervention_metrics": intervention_metrics,
                    "changed": changed,
                    "change_reason": change_reason,
                    "location": location,
                    "resolved_location": resolved_location,
                    "target_location": movement["target_location"],
                    "travel": travel,
                })
                if visualizer is not None:
                    frame_steps.append(
                        build_agent_step_payload(
                            agent,
                            time_str=time_str,
                            location=location,
                            resolved_location=resolved_location,
                            target_location=movement["target_location"],
                            scheduled_activity=scheduled_activity,
                            activity=effective_activity,
                            action=act,
                            outcome=outcome,
                            perception=perc,
                            plan=plan_text,
                            reflection=refl_text,
                            changed=changed,
                            change_reason=change_reason,
                            travel=travel,
                        )
                    )
                hook_bus.emit(
                    "on_agent_post_step",
                    day=day,
                    time_str=time_str,
                    config=CONFIG,
                    agent=agent,
                    agents=agents,
                    agents_by_id=agents_by_id,
                    city_map=city_map,
                    city_map_text=city_map_text,
                    schedule_map=schedule_map,
                    actions=actions,
                    daily_logs=daily_logs,
                    env_events=agent_env_events,
                    env_context=step_env_context,
                    policy=policy,
                    step=step_ctx,
                    extension_state=extension_state,
                )

            if visualizer is not None:
                visualizer.record_frame(
                    day=day,
                    time_str=time_str,
                    day_context=day_context,
                    env_context=env_context,
                    env_events=list(env_events or []) + [
                        _life_event_as_env_event(event) for event in due_life_events
                    ],
                    agent_steps=frame_steps,
                    policy=policy or {},
                )

            if SIMULATE_REALTIME and sleep_step > 0:
                time.sleep(sleep_step)

        # ----- PHASE 3c: Day-end consolidation (memory review, daily summary, diary, episode persist) -----
        for agent in agents:
            day_consolidation_text = ""
            if HUMAN_REALISM_ENABLED:
                agent_id = agent["id"]
                budget = llm_budget_by_agent.get(agent_id, {"remaining": 0})
                day_eps = [
                    ep for ep in agent.get("episodes", [])
                    if int(ep.get("day", 0) or 0) == day
                ]
                consolidated = consolidate_day(
                    agent,
                    day,
                    day_eps,
                    HUMAN_REALISM_CONFIG,
                    budget,
                )
                agent["intentions"] = consolidated.get("intentions", agent.get("intentions", {}))
                # Day-end: decay role-aware relationships, prune Dunbar
                # overflow. Both operate in place on agent["relationships"].
                decay_relationships(agent, current_day=day, cfg=HUMAN_REALISM_CONFIG)
                enforce_dunbar(agent)
                if STATEFUL:
                    save_agent_intentions(agent_id, agent.get("intentions", {}))
                    save_agent_habits(agent_id, agent.get("habits", {}))
                    save_agent_relationships(agent_id, agent.get("relationships", {}))
                    mem_cfg = dict(HUMAN_REALISM_CONFIG.get("memory", {}))
                    mem_cfg["current_day"] = day
                    prune_and_decay_episodes(agent_id, mem_cfg)
                    agent["episodes"] = load_agent_episodes(agent_id)
                memory_text = consolidated.get("memory_text", "").strip()
                if memory_text:
                    day_consolidation_text = memory_text
                    _append_memory_record(
                        agent,
                        memory_text,
                        entry_type="memory",
                        day=day,
                        time_str="consolidation",
                    )
                    print(f"🧩 {agent['name']} 的经验整合：{memory_text}")
            mem = daily_summary(agent, daily_logs[agent["id"]], day=day)
            print(f"🧠 {agent['name']} 的今日长期记忆：{mem}")
            diary_text = generate_daily_diary(
                agent,
                day,
                daily_logs[agent["id"]],
                day_context=day_context,
                day_memory=mem,
                consolidation_text=day_consolidation_text,
                intentions=agent.get("intentions", {}),
            )
            diary_path = save_daily_diary(agent, day, diary_text)
            vector_db_add_entry(
                agent["id"],
                "diary",
                diary_text,
                sim_day=day,
                sim_time="end_of_day_diary",
            )
            diary_log = f"[DailyDiary Day {day}] {diary_path}\n"
            daily_logs[agent["id"]] += diary_log
            append_agent_log(agent, diary_log)
            print(f"📓 {agent['name']} 的日记已写入：{diary_path}")
        # RAG enhancement day-tick: consolidation / decay / runtime
        # absorption. Each step is independently flag-gated, so with
        # default config this loop just checks three flags per agent
        # and returns. ``web_fetch_fn=None`` means runtime absorption
        # is skipped — the user can wire a search adapter later.
        for agent in agents:
            try:
                run_daily_memory_lifecycle(
                    agent,
                    day=day,
                    time_str="end_of_day",
                    llm=call_llm,
                    web_fetch_fn=None,
                )
            except Exception as _lifecycle_exc:  # noqa: BLE001
                print(f"⚠️ memory lifecycle hook failed for {agent.get('name')}: {_lifecycle_exc}")
        hook_bus.emit(
            "on_day_end",
            day=day,
            config=CONFIG,
            agents=agents,
            agents_by_id=agents_by_id,
            city_map=city_map,
            city_map_text=city_map_text,
            schedule_map=schedule_map,
            actions=actions,
            daily_logs=daily_logs,
            state_history=state_history,
            extension_state=extension_state,
        )
        if STATEFUL:
            save_sim_state({
                "last_day": day,
                "memory_model_version": MEMORY_MODEL_VERSION,
            })

    print("\n✅ 模拟完成")
    if visualizer is not None:
        visualizer.finalize()
    hook_bus.emit(
        "on_simulation_end",
        config=CONFIG,
        agents=agents,
        agents_by_id=agents_by_id,
        city_map=city_map,
        city_map_text=city_map_text,
        schedules=schedules,
        actions=actions,
        state_history=state_history,
        extension_state=extension_state,
    )
    visualize_social_network(agents, output_dir=NETWORK_OUTPUT_DIR)
    save_state_history(state_history, output_dir=STATE_OUTPUT_DIR)
    visualize_agent_state_changes(
        state_history,
        agent_names,
        output_dir=STATE_OUTPUT_DIR,
        metrics=state_metrics,
    )

    # End-of-simulation recap: per-agent structured block plus an LLM
    # narrative covering days run, key events, top activities, state /
    # emotion changes, growth deltas, memory + schedule + relationship
    # shifts, and a read on how human-like the run felt. Wrapped so a
    # failure here never reverses successful simulation work.
    try:
        last_day = day if "day" in locals() else start_day - 1
        life_event_log = list_life_events(CONFIG)
        summarize_simulation(
            agents,
            initial_snapshots,
            state_history,
            start_day,
            last_day,
            life_events=life_event_log,
            env_timeline_path=env_timeline_path,
            llm_fn=call_llm,
        )
    except Exception as exc:  # noqa: BLE001 - summary is best-effort
        print(f"⚠️ 仿真总结生成失败：{exc}")


# =========================================================
# 入口
# =========================================================
def _parse_question_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).splitlines() if v.strip()]

def _sanitize_timestamp_text(timestamp):
    if timestamp is None:
        return ""
    cleaned = re.sub(r"\s+", " ", str(timestamp)).strip()
    return cleaned[:64]

def _compose_external_info_text(text, timestamp=None, source=None):
    body = _sanitize_extra_text(text)
    if not body:
        return ""
    ts = _sanitize_timestamp_text(timestamp)
    src = _sanitize_extra_text(source, max_chars=80) if source else ""
    tags = ["额外信息"]
    if ts:
        tags.append(f"时间:{ts}")
    if src:
        tags.append(f"来源:{src}")
    keyword_tokens = []
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{3,}", body):
        token = chunk.strip().lower()
        if not token:
            continue
        if re.match(r"^[\u4e00-\u9fff]{5,}$", token):
            for i in range(len(token) - 1):
                keyword_tokens.append(token[i:i + 2])
        else:
            keyword_tokens.append(token)
    deduped = []
    seen = set()
    for token in keyword_tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
        if len(deduped) >= 24:
            break
    keyword_hint = f" 关键词: {' '.join(deduped)}" if deduped else ""
    return f"[{' | '.join(tags)}] {body}{keyword_hint}"

def _store_external_info_for_agent(agent, text, timestamp=None, source=None, persist=True):
    if not isinstance(agent, dict) or "id" not in agent:
        return ""
    payload = _compose_external_info_text(text, timestamp=timestamp, source=source)
    if not payload:
        return ""
    sim_time = _sanitize_timestamp_text(timestamp) or "external"
    vector_db_add_entry(agent["id"], "external_info", payload, sim_day=None, sim_time=sim_time)
    _append_external_payload_to_agent(agent, payload)
    if persist:
        save_agent_memory(agent)
    return payload

def _upsert_external_info(agent_id, text, timestamp=None, source=None):
    payload = _compose_external_info_text(text, timestamp=timestamp, source=source)
    if not payload:
        return ""
    sim_time = _sanitize_timestamp_text(timestamp) or "external"
    vector_db_add_entry(agent_id, "external_info", payload, sim_day=None, sim_time=sim_time)
    existing = load_agent_memory(agent_id)
    existing.append(payload)
    save_agent_memory({"id": agent_id, "memory": existing})
    return payload

def _parse_timestamped_line(text):
    line = str(text or "").strip()
    if not line:
        return "", ""
    patterns = [
        r"^\[(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?)\]\s*(.+)$",
        r"^(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?)\s*[|｜,，]\s*(.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, line)
        if match:
            return match.group(2).strip(), match.group(1).strip()
    return line, ""

def _normalize_external_item(item):
    if isinstance(item, str):
        text, ts = _parse_timestamped_line(item)
        return {"text": text, "timestamp": ts}
    if isinstance(item, dict):
        text = ""
        for key in ("text", "content", "info", "knowledge", "message"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip()
                break
        if not text:
            text = _sanitize_extra_text(item)
        ts = ""
        for key in ("timestamp", "time", "date", "ts"):
            value = item.get(key)
            if value is not None and str(value).strip():
                ts = _sanitize_timestamp_text(value)
                break
        return {"text": text, "timestamp": ts}
    text, ts = _parse_timestamped_line(str(item))
    return {"text": text, "timestamp": ts}

def _parse_external_text_blob(blob):
    raw = str(blob or "")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw) if b.strip()]
    if len(blocks) > 1:
        return [_normalize_external_item(block) for block in blocks]
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    return [_normalize_external_item(line) for line in lines]

def _infer_diary_timestamp_from_path(file_path):
    base_name = os.path.basename(str(file_path or "")).strip()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})\.(md|txt)$", base_name, re.I)
    if not match:
        return ""
    return match.group(1)

def _summarize_diary_import(raw_text, timestamp, file_path):
    cleaned = _sanitize_extra_text(raw_text, max_chars=12000)
    if not cleaned:
        return ""
    prompt = f"""
请将下面这份个人日记原文浓缩整理成一篇第一人称日记。

要求：
1. 保留当天最重要的事件、情绪、想法、人际互动和计划。
2. 写成连贯自然的一篇日记，不要分点。
3. 不要虚构原文没有的信息。
4. 长度控制在200到500字。

日期：{timestamp or "未知"}
文件：{os.path.basename(file_path)}

原文：
{cleaned}
"""
    try:
        summary = call_llm(prompt, task="diary_import_summary", agent_id=None).strip()
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        _LOG.warning("diary_import_summary LLM call failed: %s", exc)
        summary = ""
    summary = _sanitize_extra_text(summary, max_chars=1200)
    if summary:
        return summary
    return cleaned[:800]

def _load_external_items_from_file(file_path):
    if not os.path.exists(file_path):
        return []
    ext = os.path.splitext(file_path)[1].lower()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return []
    if not raw.strip():
        return []
    diary_timestamp = _infer_diary_timestamp_from_path(file_path)
    if diary_timestamp:
        diary_text = _summarize_diary_import(raw, diary_timestamp, file_path)
        if diary_text:
            return [{
                "text": diary_text,
                "timestamp": diary_timestamp,
            }]

    if ext == ".json":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return _parse_external_text_blob(raw)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            data = data.get("items")
        if isinstance(data, list):
            return [_normalize_external_item(item) for item in data]
        return [_normalize_external_item(data)]

    if ext in (".jsonl", ".ndjson"):
        items = []
        for line in raw.splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError:
                item = text
            items.append(_normalize_external_item(item))
        return items

    return _parse_external_text_blob(raw)

def _iter_external_import_files(path):
    if not path or not os.path.exists(path):
        return []
    if os.path.isfile(path):
        return [path]
    supported_exts = {".txt", ".md", ".json", ".jsonl", ".ndjson"}
    collected = []
    for root, _, files in os.walk(path):
        for name in sorted(files):
            ext = os.path.splitext(name)[1].lower()
            if ext not in supported_exts:
                continue
            collected.append(os.path.join(root, name))
    return collected

def _cli_rag_add(agent_id, text, timestamp=None, source="cli"):
    payload = _upsert_external_info(agent_id, text, timestamp=timestamp, source=source)
    if not payload:
        raise ValueError("额外信息为空，未写入。")
    print("✅ 已写入额外 RAG 信息")
    print(json.dumps({
        "agent_id": int(agent_id),
        "entry_type": "external_info",
        "timestamp": _sanitize_timestamp_text(timestamp) or None,
        "source": source,
        "text": payload,
    }, ensure_ascii=False, indent=2))

def _cli_rag_import(agent_id, file_path, source=None, default_timestamp=None):
    import_files = _iter_external_import_files(file_path)
    if not import_files:
        raise ValueError(f"未找到可导入文件：{file_path}")
    base_dir = file_path if os.path.isdir(file_path) else os.path.dirname(file_path)
    inserted = 0
    preview = []
    imported_files = 0
    for current_file in import_files:
        items = _load_external_items_from_file(current_file)
        if not items:
            continue
        imported_files += 1
        if source:
            src = source
        elif os.path.isdir(file_path):
            src = os.path.relpath(current_file, base_dir)
        else:
            src = os.path.basename(current_file)
        for item in items:
            text = _sanitize_extra_text(item.get("text", ""))
            if not text:
                continue
            timestamp = item.get("timestamp") or default_timestamp
            payload = _upsert_external_info(agent_id, text, timestamp=timestamp, source=src)
            if not payload:
                continue
            inserted += 1
            if len(preview) < 5:
                preview.append({
                    "source": src,
                    "timestamp": _sanitize_timestamp_text(timestamp) or None,
                    "text": payload,
                })
    if inserted <= 0:
        raise ValueError(f"存在输入内容但无有效条目写入：{file_path}")
    print("✅ 已批量导入额外 RAG 信息")
    print(json.dumps({
        "agent_id": int(agent_id),
        "path": file_path,
        "source": source,
        "files_found": len(import_files),
        "files_imported": imported_files,
        "inserted": inserted,
        "preview": preview,
    }, ensure_ascii=False, indent=2))

def _cli_interview_agent(agent_id, questions, context=None):
    df = pd.read_csv(CSV_PATH)
    city_map = load_city_map(MAP_PATH)
    agent = build_agent(agent_id, df, city_map=city_map)
    news_sources = load_news_sources(NEWS_SOURCES_PATH) if NEWS_ENABLED else []
    news_cache = load_news_cache(NEWS_CACHE_PATH) if NEWS_ENABLED else []
    if STATEFUL:
        agent["memory"] = load_agent_memory(agent["id"])
        seed_vector_db_from_memory(agent)
    else:
        agent["memory"] = []
    _bootstrap_agent_external_rag(
        agent,
        news_cache=news_cache,
        news_sources=news_sources,
    )
    answers = interview_agent(agent, questions, context=context)
    print(json.dumps(answers, ensure_ascii=False, indent=2))


def _sanitize_slug(text):
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", str(text or "").strip())
    cleaned = cleaned.strip("_")
    return cleaned[:40] if cleaned else "event"


def _extract_run_failure_hint(log_path, max_lines=80):
    if not log_path or not os.path.exists(log_path):
        return "日志不存在"
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f]
    except OSError:
        return "日志读取失败"
    if not lines:
        return "日志为空"
    tail = lines[-max_lines:]
    joined = "\n".join(tail)
    hint_lines = []
    traceback_start = None
    for idx, line in enumerate(tail):
        if line.startswith("Traceback (most recent call last):"):
            traceback_start = idx
            break
    if traceback_start is not None:
        hint_lines.extend(tail[traceback_start:])
    else:
        error_markers = ["RuntimeError", "ConnectionError", "ValueError", "KeyError", "Exception"]
        for line in reversed(tail):
            if any(marker in line for marker in error_markers):
                hint_lines = [line]
                break
    if not hint_lines:
        hint_lines = tail[-8:]
    snippet = "\n".join(hint_lines[-20:])
    if "localhost" in joined and "11434" in joined and "Connection refused" in joined:
        snippet += (
            "\n建议：当前配置正在请求本地 Ollama（localhost:11434），"
            "请先启动 Ollama，或在 compare-event 命令中显式指定可用 provider（--llm-provider）。"
        )
    return snippet


def _build_compare_overrides(scenario_dir, include_event, event_payload, args):
    policy_events = [dict(item) for item in CONFIG.get("policy_events", []) if isinstance(item, dict)]
    if include_event:
        policy_events.append(dict(event_payload))
    overrides = {
        "memory_dir": os.path.join(scenario_dir, "memory"),
        "log_dir": os.path.join(scenario_dir, "logs"),
        "vector_db_path": os.path.join(scenario_dir, "memory", "vector_db.sqlite"),
        "state_output_dir": os.path.join(scenario_dir, "state"),
        "network_output_dir": os.path.join(scenario_dir, "network"),
        "environment_output_dir": os.path.join(scenario_dir, "environment"),
        "intervention": {
            "output_dir": os.path.join(scenario_dir, "intervention"),
        },
        "visualization": {
            "enabled": True,
            "output_dir": os.path.join(scenario_dir, "visualization"),
            "site_path": CONFIG.get("visualization", {}).get("site_path", "site/simviz/index.html"),
        },
        "policy_events": policy_events,
        "stateful": True,
        "random_seed": int(args.seed),
        "distributed": {
            "enabled": False,
        },
    }
    if args.sim_days is not None:
        overrides["sim_days"] = int(args.sim_days)
    if args.agent_ids:
        overrides["agent_ids"] = list(args.agent_ids)
    if getattr(args, "llm_provider", None):
        routing = CONFIG.get("llm", {}).get("routing", {})
        task_map = routing.get("tasks", {})
        forced_tasks = {}
        if isinstance(task_map, dict):
            forced_tasks = {str(k): str(args.llm_provider) for k in task_map.keys()}
        overrides["llm"] = {
            "routing": {
                "default": str(args.llm_provider),
                "tasks": forced_tasks,
            }
        }
    return overrides


def _run_cli_subprocess(command, env, log_path):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        proc = subprocess.run(
            command,
            env=env,
            stdout=f,
            stderr=subprocess.STDOUT,
            text=True,
        )
    return proc.returncode


def _launch_cli_subprocess(command, env, log_path):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    f = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        command,
        env=env,
        stdout=f,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, f


def _final_metric_snapshot(state_csv_path):
    if not state_csv_path or not os.path.exists(state_csv_path):
        return {}
    try:
        df = pd.read_csv(state_csv_path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        _LOG.warning("Failed to read state CSV %s: %s", state_csv_path, exc)
        return {}
    required = {"agent_id", "step", "metric", "value"}
    if df.empty or not required.issubset(set(df.columns)):
        return {}
    final_idx = df.groupby(["agent_id", "metric"])["step"].idxmax()
    final_df = df.loc[final_idx]
    grouped = final_df.groupby("metric")["value"].mean()
    return {str(k): float(v) for k, v in grouped.items()}


def _mean_metric_snapshot(state_csv_path):
    if not state_csv_path or not os.path.exists(state_csv_path):
        return {}
    try:
        df = pd.read_csv(state_csv_path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        _LOG.warning("Failed to read state CSV %s: %s", state_csv_path, exc)
        return {}
    required = {"metric", "value"}
    if df.empty or not required.issubset(set(df.columns)):
        return {}
    grouped = df.groupby("metric")["value"].mean()
    return {str(k): float(v) for k, v in grouped.items()}


def _compose_comparison_rows(base_state_csv, event_state_csv):
    baseline_final = _final_metric_snapshot(base_state_csv)
    event_final = _final_metric_snapshot(event_state_csv)
    baseline_mean = _mean_metric_snapshot(base_state_csv)
    event_mean = _mean_metric_snapshot(event_state_csv)
    metrics = sorted(set(baseline_final) | set(event_final) | set(baseline_mean) | set(event_mean))
    rows = []
    for metric in metrics:
        b_final = float(baseline_final.get(metric, 0.0))
        e_final = float(event_final.get(metric, 0.0))
        b_mean = float(baseline_mean.get(metric, 0.0))
        e_mean = float(event_mean.get(metric, 0.0))
        rows.append({
            "metric": metric,
            "baseline_final": b_final,
            "event_final": e_final,
            "delta_final": e_final - b_final,
            "baseline_mean": b_mean,
            "event_mean": e_mean,
            "delta_mean": e_mean - b_mean,
        })
    rows.sort(key=lambda x: abs(x["delta_final"]), reverse=True)
    return rows


def _impact_hint(metric, delta):
    if abs(delta) < 1e-9:
        return "几乎无变化"
    sign = "上升" if delta > 0 else "下降"
    amount = abs(delta)
    if metric == "stress":
        direction = "压力" + sign
    elif metric == "emotion":
        direction = "情绪" + sign
    elif metric == "econ_security":
        direction = "经济安全感" + sign
    elif metric == "city_identity":
        direction = "城市认同" + sign
    elif metric == "mobility_intent":
        direction = "流动意愿" + sign
    elif metric == "stance_score":
        direction = "平均立场分数" + sign
    elif metric == "toxicity_score":
        direction = "毒性风险" + sign
    elif metric == "misinformation_risk":
        direction = "误信息风险" + sign
    elif metric == "cross_viewpoint_exposure":
        direction = "跨观点曝光" + sign
    elif metric == "intervention_reward":
        direction = "干预奖励" + sign
    else:
        direction = f"{metric}" + sign
    return f"{direction}（Δ={amount:.4f}）"


def _write_comparison_report(output_root, event_payload, rows):
    os.makedirs(output_root, exist_ok=True)
    metrics_csv = os.path.join(output_root, "comparison_metrics.csv")
    report_md = os.path.join(output_root, "comparison_summary.md")
    if rows:
        pd.DataFrame(rows).to_csv(metrics_csv, index=False)
    else:
        pd.DataFrame(columns=[
            "metric",
            "baseline_final",
            "event_final",
            "delta_final",
            "baseline_mean",
            "event_mean",
            "delta_mean",
        ]).to_csv(metrics_csv, index=False)

    lines = []
    lines.append("# 事件影响对比报告")
    lines.append("")
    lines.append(f"- 事件名称：{event_payload.get('name', '')}")
    lines.append(f"- 事件时间：Day {event_payload.get('day', '')} {event_payload.get('time', '')}")
    lines.append(f"- 事件描述：{event_payload.get('description', '')}")
    lines.append("")
    if rows:
        top = rows[:5]
        intervention_rows = [
            row for row in rows
            if row.get("metric") in set(INTERVENTION_METRICS)
        ]
        intervention_rows.sort(key=lambda x: abs(x["delta_final"]), reverse=True)
        if intervention_rows:
            lines.append("## PolicySim 干预指标")
            lines.append("")
            for item in intervention_rows:
                hint = _impact_hint(item["metric"], item["delta_final"])
                lines.append(
                    f"- `{item['metric']}`: baseline={item['baseline_final']:.4f}, "
                    f"event={item['event_final']:.4f}, Δ={item['delta_final']:.4f}，{hint}"
                )
            lines.append("")
        lines.append("## 关键差异（按终值绝对差排序）")
        lines.append("")
        for item in top:
            hint = _impact_hint(item["metric"], item["delta_final"])
            lines.append(
                f"- `{item['metric']}`: baseline={item['baseline_final']:.4f}, "
                f"event={item['event_final']:.4f}, Δ={item['delta_final']:.4f}，{hint}"
            )
        lines.append("")
        lines.append("## 估计结论")
        lines.append("")
        top_hint = "；".join(_impact_hint(r["metric"], r["delta_final"]) for r in top[:3])
        lines.append(f"事件对系统的主要影响表现为：{top_hint}。")
    else:
        lines.append("未生成有效状态对比数据，请检查两组 simulation 输出。")
    lines.append("")
    lines.append(f"- 指标明细：`{metrics_csv}`")
    with open(report_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return report_md, metrics_csv


def _cli_compare_event(args):
    event_payload = {
        "day": int(args.event_day),
        "time": str(args.event_time),
        "name": str(args.event_name),
        "description": str(args.event_description),
    }
    ts = time.strftime("%Y%m%d_%H%M%S")
    slug = _sanitize_slug(args.event_name)
    root = os.path.join(args.output_root, f"{ts}_{slug}")
    baseline_dir = os.path.join(root, "without_event")
    event_dir = os.path.join(root, "with_event")
    os.makedirs(baseline_dir, exist_ok=True)
    os.makedirs(event_dir, exist_ok=True)

    baseline_overrides = _build_compare_overrides(
        baseline_dir,
        include_event=False,
        event_payload=event_payload,
        args=args,
    )
    event_overrides = _build_compare_overrides(
        event_dir,
        include_event=True,
        event_payload=event_payload,
        args=args,
    )

    script_path = os.path.abspath(__file__)
    python_bin = sys.executable
    base_env = os.environ.copy()
    env_without = dict(base_env)
    env_with = dict(base_env)
    env_without["GAWORLD_CONFIG_OVERRIDES"] = json.dumps(baseline_overrides, ensure_ascii=False)
    env_with["GAWORLD_CONFIG_OVERRIDES"] = json.dumps(event_overrides, ensure_ascii=False)

    # Clean reset both scenarios before run.
    reset_without_log = os.path.join(baseline_dir, "reset.log")
    reset_with_log = os.path.join(event_dir, "reset.log")
    rc = _run_cli_subprocess([python_bin, script_path, "reset"], env_without, reset_without_log)
    if rc != 0:
        raise RuntimeError(f"无事件场景 reset 失败，日志：{reset_without_log}")
    rc = _run_cli_subprocess([python_bin, script_path, "reset"], env_with, reset_with_log)
    if rc != 0:
        raise RuntimeError(f"有事件场景 reset 失败，日志：{reset_with_log}")

    # Run in parallel.
    run_without_log = os.path.join(baseline_dir, "run.log")
    run_with_log = os.path.join(event_dir, "run.log")
    proc_without, file_without = _launch_cli_subprocess(
        [python_bin, script_path, "run"],
        env_without,
        run_without_log,
    )
    proc_with, file_with = _launch_cli_subprocess(
        [python_bin, script_path, "run"],
        env_with,
        run_with_log,
    )
    code_without = proc_without.wait()
    code_with = proc_with.wait()
    file_without.close()
    file_with.close()
    if code_without != 0 or code_with != 0:
        without_hint = _extract_run_failure_hint(run_without_log)
        with_hint = _extract_run_failure_hint(run_with_log)
        raise RuntimeError(
            "并行 simulation 运行失败。"
            f"\n无事件日志：{run_without_log}\n{without_hint}\n"
            f"\n有事件日志：{run_with_log}\n{with_hint}"
        )

    baseline_state_csv = os.path.join(baseline_overrides["state_output_dir"], "agent_state_history.csv")
    event_state_csv = os.path.join(event_overrides["state_output_dir"], "agent_state_history.csv")
    rows = _compose_comparison_rows(baseline_state_csv, event_state_csv)
    report_md, metrics_csv = _write_comparison_report(root, event_payload, rows)

    print("\n✅ 对比 simulation 完成")
    print(f"输出目录: {root}")
    print(f"报告文件: {report_md}")
    print(f"指标文件: {metrics_csv}")
    if rows:
        print("\nTop differences:")
        for item in rows[:5]:
            print(
                f"- {item['metric']}: baseline={item['baseline_final']:.4f}, "
                f"event={item['event_final']:.4f}, delta={item['delta_final']:.4f}"
            )

def _build_arg_parser():
    import argparse
    parser = argparse.ArgumentParser(description="GAWorld simulator")
    subparsers = parser.add_subparsers(dest="command")

    run_cmd = subparsers.add_parser("run", help="Run the full simulation")
    run_cmd.add_argument("--sim-days", type=int, default=None, help="Override simulation days")
    subparsers.add_parser("reset", help="Reset simulation memory/logs/cache")

    interview = subparsers.add_parser("interview", help="Interview a specific agent by ID")
    interview.add_argument("--agent-id", type=int, required=True, help="Agent ID to interview")
    interview.add_argument(
        "--question",
        action="append",
        dest="questions",
        help="Interview question (can be used multiple times)",
    )
    interview.add_argument(
        "--questions-file",
        help="Path to a UTF-8 text file with one question per line",
    )
    interview.add_argument(
        "--context",
        default=None,
        help="Optional background context for the interview",
    )

    create_from_social = subparsers.add_parser(
        "create-agent-from-social",
        help="Create a new agent from a social media page or extracted text",
    )
    create_source_group = create_from_social.add_mutually_exclusive_group(required=True)
    create_source_group.add_argument("--url", help="Social media page URL (e.g. X/Weibo page)")
    create_source_group.add_argument("--file", help="Local text/html/markdown file containing page content")
    create_source_group.add_argument("--text", help="Direct pasted page text")
    create_from_social.add_argument(
        "--name",
        default=None,
        help="Optional override name for the generated agent",
    )

    rag_add = subparsers.add_parser(
        "rag-add",
        help="Add one external RAG info item for an agent",
    )
    rag_add.add_argument("--agent-id", type=int, required=True, help="Agent ID")
    rag_add.add_argument("--text", required=True, help="External info text")
    rag_add.add_argument(
        "--timestamp",
        default=None,
        help="Optional timestamp for this info (e.g. 2026-02-18 09:30)",
    )
    rag_add.add_argument(
        "--source",
        default="cli",
        help="Source tag for this info",
    )

    rag_import = subparsers.add_parser(
        "rag-import",
        help="Import external RAG info from a file or directory for an agent",
    )
    rag_import.add_argument("--agent-id", type=int, required=True, help="Agent ID")
    rag_import.add_argument("--file", required=True, help="Input file or directory path (.txt/.md/.json/.jsonl)")
    rag_import.add_argument(
        "--source",
        default=None,
        help="Optional source tag (defaults to file name or relative path when importing a directory)",
    )
    rag_import.add_argument(
        "--default-timestamp",
        default=None,
        help="Fallback timestamp for items without timestamp",
    )

    compare_event = subparsers.add_parser(
        "compare-event",
        help="Run two simulations in parallel (with/without a specified event) and compare impact",
    )
    compare_event.add_argument("--event-name", required=True, help="Event name")
    compare_event.add_argument("--event-description", required=True, help="Event description")
    compare_event.add_argument("--event-day", type=int, required=True, help="Event day index")
    compare_event.add_argument("--event-time", default="10:00", help="Event time HH:MM")
    compare_event.add_argument("--sim-days", type=int, default=None, help="Override simulation days")
    compare_event.add_argument(
        "--agent-id",
        type=int,
        action="append",
        dest="agent_ids",
        help="Agent ID to include (can be repeated)",
    )
    compare_event.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed shared by both scenarios",
    )
    compare_event.add_argument(
        "--llm-provider",
        default=None,
        help="Force both scenarios to use the same provider name (e.g., openai_gpt, ollama_local)",
    )
    compare_event.add_argument(
        "--output-root",
        default="output/comparisons",
        help="Output root for comparison artifacts",
    )

    serve_viz = subparsers.add_parser(
        "serve-viz",
        help="Serve the visualization page and output artifacts over HTTP",
    )
    serve_viz.add_argument("--host", default="127.0.0.1", help="Bind host")
    serve_viz.add_argument("--port", type=int, default=8000, help="Bind port")

    dashboard = subparsers.add_parser(
        "dashboard",
        help="Serve the local simulation dashboard with configuration and run controls",
    )
    dashboard.add_argument("--host", default="127.0.0.1", help="Bind host")
    dashboard.add_argument("--port", type=int, default=8766, help="Bind port")

    distributed_cfg = CONFIG.get("distributed", {})
    distributed_server_cfg = (
        distributed_cfg.get("server", {})
        if isinstance(distributed_cfg.get("server"), dict)
        else {}
    )
    serve_distributed = subparsers.add_parser(
        "serve-distributed",
        help="Run distributed communication relay server for multi-machine agents",
    )
    serve_distributed.add_argument(
        "--host",
        default=distributed_server_cfg.get("host", "0.0.0.0"),
        help="Bind host",
    )
    serve_distributed.add_argument(
        "--port",
        type=int,
        default=int(distributed_server_cfg.get("port", 8877)),
        help="Bind port",
    )
    serve_distributed.add_argument(
        "--state-path",
        default=distributed_server_cfg.get("state_path", "output/distributed/relay_state.json"),
        help="State persistence path",
    )
    serve_distributed.add_argument(
        "--max-messages",
        type=int,
        default=int(distributed_server_cfg.get("max_messages", 20000)),
        help="Max retained messages in relay",
    )
    return parser

def _load_questions_from_file(path):
    if not path:
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except OSError:
        return []


def _cli_serve_viz(host="127.0.0.1", port=8000):
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    repo_root = os.path.dirname(os.path.abspath(__file__))
    handler = partial(SimpleHTTPRequestHandler, directory=repo_root)
    page_url = f"http://{host}:{int(port)}/{VISUALIZATION_SITE_PATH}"
    print(f"可视化页面: {page_url}")
    print("按 Ctrl+C 停止服务。")
    server = ThreadingHTTPServer((host, int(port)), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _cli_serve_distributed(host=None, port=None, state_path=None, max_messages=None):
    from gaworld.apps.distributed_comm_server import run_server

    distributed_cfg = CONFIG.get("distributed", {})
    server_cfg = distributed_cfg.get("server", {}) if isinstance(distributed_cfg.get("server"), dict) else {}
    use_host = host or server_cfg.get("host", "0.0.0.0")
    use_port = int(port if port is not None else server_cfg.get("port", 8877))
    use_state_path = state_path or server_cfg.get("state_path", "output/distributed/relay_state.json")
    use_max_messages = int(max_messages if max_messages is not None else server_cfg.get("max_messages", 20000))
    run_server(
        host=use_host,
        port=use_port,
        state_path=use_state_path,
        max_messages=use_max_messages,
    )

def _main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.command == "reset":
        reset_simulation()
        print("✅ 已重置模拟：清空记忆、日志与缓存。")
        return

    if args.command == "interview":
        questions = []
        questions.extend(_parse_question_list(args.questions))
        questions.extend(_load_questions_from_file(args.questions_file))
        if not questions:
            parser.error("Provide at least one --question or a --questions-file.")
        _cli_interview_agent(args.agent_id, questions, context=args.context)
        return

    if args.command == "create-agent-from-social":
        _cli_create_agent_from_social(
            url=args.url,
            file_path=args.file,
            text=args.text,
            name=args.name,
        )
        return

    if args.command == "rag-add":
        _cli_rag_add(
            args.agent_id,
            args.text,
            timestamp=args.timestamp,
            source=args.source,
        )
        return

    if args.command == "rag-import":
        _cli_rag_import(
            args.agent_id,
            args.file,
            source=args.source,
            default_timestamp=args.default_timestamp,
        )
        return

    if args.command == "compare-event":
        _cli_compare_event(args)
        return

    if args.command == "serve-viz":
        _cli_serve_viz(host=args.host, port=args.port)
        return

    if args.command == "dashboard":
        from gaworld.apps.dashboard_server import run_server

        run_server(host=args.host, port=args.port)
        return

    if args.command == "serve-distributed":
        _cli_serve_distributed(
            host=args.host,
            port=args.port,
            state_path=args.state_path,
            max_messages=args.max_messages,
        )
        return

    if getattr(args, "sim_days", None) is not None:
        CONFIG["sim_days"] = int(args.sim_days)
        global SIM_DAYS
        SIM_DAYS = int(args.sim_days)

    run_simulation()

if __name__ == "__main__":
    _main()
