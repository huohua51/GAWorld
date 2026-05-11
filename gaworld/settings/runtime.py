"""Core simulation, memory, behavior, and policy defaults."""

from __future__ import annotations

from typing import Any


def simulation_settings() -> dict[str, Any]:
    return {
        # Simulation
        "agent_ids": [2],
        "sim_days": 2,
        "seconds_per_day": 10,
        # When False, simulation runs as fast as the CPU/LLM backend allows.
        "simulate_realtime": False,
        "print_agent_profile": False,
        # Time step for simulation timeline (minutes). None/0 uses schedule times only.
        # "time_step_minutes": "2 hours",
        "time_step_minutes": None,
        # Calendar settings for weekday/weekend simulation.
        "calendar": {
            "start_date": "today",
            "start_weekday": "monday",
            "weekend_days": ["saturday", "sunday"],
        },
        # External RAG information (added via CLI/file import).
        "external_rag": {
            "top_k": 2,
            "bootstrap": {
                "enabled": True,
                "use_seed_script": True,
                "only_when_empty": True,
                "profile_items": 3,
                "web_items": 1,
                "use_web_search": True,
                "prefer_cached_news": True,
                "max_chars_per_item": 280,
            },
        },
        # Simulation background (time/city/societal status prompt)
        "background": "2025年冬季，中国·杭州。经济发展中等偏稳，青年就业压力上升，生活成本偏高；社会秩序稳定但政策与舆论压力较高。",
        # Data sources
        "csv_path": "data/hangzhou_agents_state_init.csv",
        "md_path": "data/hangzhou_profiles_with_names.md",
        "map_path": "data/citymap.md",
        # Memory / logs
        "stateful": True,
        "memory_dir": "output/memory",
        "log_dir": "output/logs",
        "diary_output_dir": "output/diaries",
        "environment_output_dir": "output/environment",
        "visualization": {
            "enabled": True,
            "output_dir": "output/visualization",
            "site_path": "site/simviz/index.html",
            # Avoid rewriting the full trace file on every tick.
            "flush_every_frames": 24,
        },
        "environment_config_path": "data/environment_config.json",
        # Memory model compatibility gate.
        # When version changes and stateful mode is enabled, run `reset` once.
        "memory_model_version": 3,
        "require_clean_reset_on_memory_model_change": True,
        # Vector DB (memory + logs)
        "vector_db_path": "output/memory/vector_db.sqlite",
        "vector_db_dim": 256,
        "vector_db_top_k": 3,
        "vector_db_max_chars": 2000,
        # Policy events (description only; effect inferred by LLM)
        "policy_events": [
            {
                "day": 2,
                "time": "10:00",
                "name": "Platform worker protection policy",
                "description": (
                    "Increase social security coverage and wage transparency, "
                    "strengthen platform labor oversight."
                ),
            }
        ],
        # Manual "life events" queue. The dashboard can add targeted events while
        # a simulation is running; the simulator consumes due events on each tick.
        "life_events": {
            "enabled": True,
            "event_dir": "output/life_events",
            "events_file": "events.json",
        },
        # Routine change (chance to deviate from schedule during the day)
        "routine_change": {
            "enabled": True,
            "base_chance": 0.08,
            "event_boost": 0.08,
            "policy_boost": 0.05,
            "max_chance": 0.45,
        },
        "daily_planning": {
            "anchor_minutes": 30,
            "random_delay_max_minutes": 10,
            "flexible": {
                "enabled": True,
                "min_items": 6,
                "max_items": 12,
                "max_time_shift_minutes": 120,
                "min_gap_minutes": 15,
                "allow_insertions": True,
            },
        },
        "spontaneity": {
            "enabled": True,
            "base_thought_chance": 0.18,
            "max_thought_chance": 0.68,
            "event_boost": 0.10,
            "policy_boost": 0.08,
            "social_boost": 0.08,
            "low_self_control_boost": 0.22,
            "stress_boost": 0.18,
            "fatigue_boost": 0.14,
            "hunger_boost": 0.12,
            "impulse_activity_chance": 0.10,
            "random_action_chance": 0.05,
            "max_override_bonus": 0.35,
        },
        # Concurrency (S3): each *_workers knob caps the parallelism for one
        # stage of the main loop. Default is serial for legacy compatibility.
        "concurrency": {
            "enabled": False,
            "day_routine_workers": 1,
        },
    }
