import json
import os

CONFIG = {
    # LLM (legacy defaults for compatibility)
    "ollama_url": "http://localhost:11434/api/generate",
    #"model_name": "gemma3n:e4b",
    "model_name": "qwen3.5:9b",
    "llm_timeout": 600,
    # LLM routing (multi-backend)
    "llm": {
        "providers": {
            "ollama_local": {
                "type": "ollama",
                "url": "http://localhost:11434/api/generate",
                "model": "gemma3n:e4b",
                "timeout": 120,
            },
            "ollama_gemma4": {
                "type": "ollama",
                "url": "http://localhost:11434/api/generate",
                "model": "gemma4:e4b",
                "timeout": 120,
            },
            "ollama_qwen": {
                "type": "ollama",
                "url": "http://localhost:11434/api/generate",
                "model": "qwen3.5:9b",
                "timeout": 600,
            },
            "omlx_qwen": {
                "type": "openai",
                "base_url": "http://127.0.0.1:8000/v1",
                "model": "Qwen3.5-9B-MLX-4bit",
                # omlx exposes an OpenAI-compatible API locally.
                # If your local server does not require auth, this placeholder is sufficient.
                "api_key": os.environ.get("OMLX_API_KEY", "omlx-local"),
                # Stream responses so the client receives incremental chunks
                # during long local prefill/generation phases.
                "stream": True,
                # Keep local generations bounded; the simulator makes many calls.
                "max_tokens": 256,
                "temperature": 0.2,
                "timeout": 600,
            },
            "openai_gpt": {
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-5.4",
                "api_key_env": "OPENAI_API_KEY",
                "timeout": 120,
            },
            "minimax": {
                "type": "anthropic",
                "base_url": os.environ.get("ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic"),
                "model": os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7"),
                "api_key_env": "MINIMAX_API_KEY",
                "api_key_envs": ["MINIMAX_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"],
                # China-region Minimax expects the raw secret key in Authorization.
                # Set MINIMAX_AUTHORIZATION_SCHEME=bearer for endpoints that require Bearer tokens.
                "authorization_scheme": os.environ.get("MINIMAX_AUTHORIZATION_SCHEME", "raw"),
                "authorization_retry_schemes": ["bearer"],
                "include_x_api_key": False,
                "timeout": 120,
                "max_tokens": 512,
            },
        },
        "routing": {
            "default": "minimax",
            "tasks": {
                "schedule": "minimax",
            },
        },
    },
    # Simulation
    "agent_ids": [52],
    "sim_days": 7,
    "seconds_per_day": 10,
    # When False, simulation runs as fast as the CPU/LLM backend allows.
    "simulate_realtime": False,
    "print_agent_profile": False,
    # Time step for simulation timeline (minutes). None/0 uses schedule times only.
    #"time_step_minutes": "2 hours",
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
    "csv_path": "hangzhou_agents_state_init.csv",
    "md_path": "hangzhou_profiles_with_names.md",
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
    "environment_config_path": "environment_config.json",
    "external_environment_service": {
        "enabled": False,
        "base_url": "http://127.0.0.1:8765",
        "timeout": 6,
        "fallback_to_empty": True,
    },
    # Distributed multi-machine simulation.
    # Run a relay server and let each node process its own local agent subset.
    "distributed": {
        "enabled": True,
        "cluster": "default",
        # Leave empty to auto-generate using hostname + pid.
        "node_id": "",
        # Optional local subset override for this machine.
        # If enabled and non-empty, this list overrides CONFIG["agent_ids"].
        "local_agent_ids": [],
        # Optional explicit cross-machine peers.
        # If empty, peers are discovered from relay directory.
        "peer_agent_ids": [],
        "send_probability": 0.18,
        "max_outbound_per_step": 1,
        "max_inbound_per_step": 3,
        "message_max_chars": 160,
        "fail_fast": False,
        "relay": {
            "base_url": "http://127.0.0.1:8877",
            "timeout": 3,
        },
        "server": {
            "host": "0.0.0.0",
            "port": 8877,
            "state_path": "output/distributed/relay_state.json",
            "max_messages": 20000,
        },
    },
    # OpenClaw external agent integration.
    # Allows users to connect their personal OpenClaw agents to the simulation.
    "openclaw": {
        "enabled": False,
        # ID range for auto-assigned OpenClaw agents (avoid collision with native IDs).
        "id_range_start": 1001,
        # Auth tokens that OpenClaw bridges must present to register.
        # Empty list = open (no auth required).  Set via POST /auth/token or here.
        "auth_tokens": [],
        # Whether the sim engine should push tick state to the relay server
        # so that bridges can synchronise with the simulation clock.
        "push_tick_to_relay": True,
        # Default bridge settings (informational; the bridge reads its own CLI args).
        "bridge_defaults": {
            "poll_interval_seconds": 5.0,
            "openclaw_gateway_url": "http://127.0.0.1:18789",
            "openclaw_timeout": 30,
            "max_inbound_per_cycle": 5,
            "message_max_chars": 300,
        },
    },
    # Personal twin runtime.
    # Private memory and raw context stay local; only public social summaries
    # are shared with the relay-backed social layer.
    "personal_twin": {
        "enabled": True,
        "local_first": True,
        "private_memory_policy": "local_only",
        "share_social_summaries": True,
        "daily_self_update": True,
        "what_if_enabled": True,
    },
    "environment_server": {
        "host": "0.0.0.0",
        "port": 8765,
        "state_path": "output/environment/server_state.json",
        "use_llm": True,
    },
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
            "description": "Increase social security coverage and wage transparency, strengthen platform labor oversight."
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
    # News / social media reading
    "news": {
        "enabled": True,
        "sources_path": "news_source.md",
        "cache_path": "news_cache.json",
        "use_cache_first": True,
        "daily_chance": 0.9,
        "max_reads_per_day": 5,
        "timeout": 8,
        "max_chars": 2000,
        "memory_excerpt_chars": 600,
        "user_agent": "GAWorld/1.0",
        "info_seek": {
            "enabled": True,
            "base_daily_chance": 0.55,
            "max_seeks_per_day": 3,
            "preferred_sites_per_agent": 6,
            "prefer_source_visit_ratio": 0.55,
            "engines": ["baidu", "google", "bing"],
            "max_results": 4,
            "timeout": 8,
            "content_timeout": 8,
            "content_max_chars": 2000,
            "memory_excerpt_chars": 700,
            "user_agent": "GAWorld/1.0",
        },
    },
    # PolicySim-inspired lightweight intervention evaluation.
    # This is deterministic and does not call external moderation or training APIs.
    "intervention": {
        "enabled": True,
        "output_dir": "output/intervention",
        "recommendation": {
            "max_items": 5,
            "source_weights": {
                "relational": 1.0,
                "personalized": 0.85,
                "headline": 0.75,
            },
        },
        "exposure_control": {
            "enabled": True,
            "toxicity_threshold": 0.45,
            "misinformation_threshold": 0.35,
            "suppression_factor": 0.25,
        },
        "stance": {
            "alpha": 0.8,
            "positive_keywords": ["支持", "赞成", "改善", "安心", "信任", "机会", "合作", "透明", "保护"],
            "negative_keywords": ["反对", "担心", "不满", "风险", "冲突", "失望", "质疑", "压力", "限制"],
        },
        "toxicity_keywords": ["辱骂", "攻击", "仇恨", "歧视", "极端", "滚", "骗子", "垃圾"],
        "misinformation_keywords": ["谣言", "假消息", "未经证实", "阴谋", "伪造", "骗局", "造假", "不实"],
        "objectives": {
            "cross_viewpoint_weight": 0.55,
            "engagement_weight": 0.20,
            "toxicity_penalty_weight": 0.15,
            "misinformation_penalty_weight": 0.10,
        },
    },
    # Human realism (experience accumulation + habit/need dynamics)
    "human_realism": {
        "enabled": True,
        "llm": {
            "max_extra_calls_per_agent_day": 2,
        },
        "memory": {
            "max_episodes_per_agent": 2000,
            "daily_consolidation_top_k": 12,
            "salience_threshold": 0.35,
            "decay_half_life_days": 14,
            "recall": {
                "base_top_k": 2,
                "max_top_k": 5,
                "planning_top_k": 3,
                "action_top_k": 3,
                "reflection_top_k": 4,
                "interview_top_k": 4,
                "hint_chars": 240,
                "surface_min_score": 0.08,
                "effect_scale": 0.015,
            },
            "review": {
                "interval_minutes": 240,
                "max_per_day": 3,
                "trigger_salience": 0.72,
                "top_k": 4,
            },
        },
        "behavior": {
            "habit_learning_rate": 0.08,
            "inertia_weight": 0.25,
            "decision_noise": 0.18,
            "fatigue_work_gain": 0.035,
            "fatigue_sleep_recovery": 0.18,
            "self_control_recovery": 0.08,
            "time_pressure_decay": 0.06,
            "commitment_weights": {
                "high": 1.2,
                "medium": 0.6,
                "low": 0.2,
            },
            "avoidance_bonus_scale": 1.1,
            "need_weights": {
                "energy": 0.45,
                "hunger": 0.30,
                "social_need": 0.25,
            },
        },
    },
    # Dynamic behaviour system — makes agent daily schedules feel human
    # by injecting spontaneous urges, social encounters, need-based
    # interrupts, and environment-triggered activity changes.
    "dynamic_behavior": {
        "enabled": True,
    },
    # Economy module – realistic personal finance with tax, social insurance,
    # Engel-coefficient spending, investment, and macro-economic cycles.
    "economy": {
        "enabled": True,
        "currency": "CNY",
        "output_dir": "output/economy",
        "hours_per_step": 1.0,
        "work_days_per_month": 22,
        "work_hours_per_day": 8,
        # --- Initial assets ---
        "initial_savings_months_min": 1.0,
        "initial_savings_months_max": 6.0,
        "inheritance_enabled": True,
        "inheritance_base_probability": 0.28,
        "inheritance_age_peak_low": 30,
        "inheritance_age_peak_high": 55,
        "inheritance_ratio_min": 0.25,
        "inheritance_ratio_max": 2.0,
        "inheritance_hukou_bonus": {
            "urban": 0.04, "city": 0.04, "town": 0.02,
            "rural": -0.03, "village": -0.03,
        },
        # --- Tax (China 2024 progressive individual income tax) ---
        "tax": {
            "enabled": True,
            "monthly_exemption": 5000.0,
            "default_special_deduction": 1500.0,
            "brackets": [
                (3000,   0.03,    0),
                (12000,  0.10,  210),
                (25000,  0.20, 1410),
                (35000,  0.25, 2660),
                (55000,  0.30, 4410),
                (80000,  0.35, 7160),
                (float("inf"), 0.45, 15160),
            ],
        },
        # --- Social insurance (individual contribution rates) ---
        "social_insurance": {
            "enabled": True,
            "pension_rate": 0.08,
            "medical_rate": 0.02,
            "unemployment_rate": 0.005,
            "work_injury_rate": 0.0,
            "maternity_rate": 0.0,
            "housing_fund_rate": 0.08,
            "housing_fund_employer_rate": 0.08,
            "base_cap": 36000.0,
            "base_floor": 4462.0,
        },
        # --- Spending (Engel coefficient curve) ---
        "spending": {
            "engel_curve": [
                (4000,   0.48, 0.05),
                (7000,   0.38, 0.15),
                (12000,  0.30, 0.25),
                (20000,  0.22, 0.32),
                (float("inf"), 0.15, 0.40),
            ],
            "budget_template": {
                "food": 0.30, "housing": 0.25, "transport": 0.10,
                "clothing": 0.06, "leisure": 0.10, "education": 0.08,
                "healthcare": 0.06, "misc": 0.05,
            },
            "income_elasticity": {
                "food": 0.5, "housing": 0.8, "transport": 0.7,
                "clothing": 1.2, "leisure": 1.5, "education": 1.1,
                "healthcare": 0.6, "misc": 1.0,
            },
            "daily_variance": 0.25,
        },
        # --- Investment & savings ---
        "investment": {
            "enabled": True,
            "asset_returns": {
                "deposits": (0.025, 0.005),
                "funds":    (0.06,  0.08),
                "stocks":   (0.08,  0.22),
            },
            "portfolio_profiles": {
                "conservative": {"deposits": 0.70, "funds": 0.25, "stocks": 0.05},
                "moderate":     {"deposits": 0.40, "funds": 0.40, "stocks": 0.20},
                "aggressive":   {"deposits": 0.15, "funds": 0.35, "stocks": 0.50},
            },
            "auto_save_enabled": True,
            "checking_buffer_months": 2.0,
        },
        # --- Macro-economic cycle ---
        "macro": {
            "enabled": True,
            "initial_inflation_rate": 0.025,
            "initial_unemployment_rate": 0.052,
            "cycle_phase_duration_days": (60, 180),
            "phases": ["expansion", "peak", "contraction", "trough"],
            "phase_effects": {
                "expansion":   {"income_mult": 1.05, "expense_mult": 1.02, "layoff_risk": 0.002, "raise_chance": 0.03},
                "peak":        {"income_mult": 1.08, "expense_mult": 1.06, "layoff_risk": 0.005, "raise_chance": 0.02},
                "contraction": {"income_mult": 0.95, "expense_mult": 1.04, "layoff_risk": 0.015, "raise_chance": 0.005},
                "trough":      {"income_mult": 0.90, "expense_mult": 0.98, "layoff_risk": 0.025, "raise_chance": 0.002},
            },
            "industry_conditions": {
                "tech": 1.0, "finance": 1.0, "medical": 1.0,
                "education": 1.0, "service": 1.0, "trade": 1.0, "default": 1.0,
            },
        },
        # --- Shock events ---
        "shocks": {
            "enabled": True,
            "layoff_base_prob": 0.001,
            "raise_base_prob": 0.008,
            "medical_emergency_prob": 0.0005,
            "medical_cost_range": (2000.0, 50000.0),
            "year_end_bonus_enabled": True,
            "year_end_bonus_months": 1.0,
        },
        # --- Backward-compat behavior triggers ---
        "rent_income_ratio": 0.22,
        "daily_utilities_cost": 12.0,
        "base_living_cost_per_hour": 6.0,
        "min_hourly_income": 8.0,
        "income_volatility": 0.25,
        "target_work_hours_per_day": 7.0,
        "asset_safety_days": 18.0,
        "income_seek_threshold": 0.56,
        "income_seek_probability_scale": 0.9,
        "wealth_drive_seek_threshold": 0.65,
        "income_growth_when_deficit": 0.08,
        "income_seek_activities": ["工作", "兼职", "接单", "技能提升"],
        "expense_ranges": {
            "food": [8.0, 26.0], "clothing": [18.0, 120.0],
            "transport": [3.0, 28.0], "housing": [0.0, 0.0],
            "leisure": [8.0, 70.0], "education": [10.0, 60.0],
            "healthcare": [12.0, 90.0], "misc": [4.0, 22.0],
        },
    },
    # ----------------------------------------------------------------
    # Concurrency (S3): each *_workers knob caps the parallelism for
    # one specific stage of the main loop. Default is 1 (serial) so
    # the legacy behaviour is preserved bit-for-bit. When concurrency
    # is enabled the global `random` state may be consumed in a
    # non-deterministic order; reproducible experiments should keep
    # workers at 1.
    "concurrency": {
        "enabled": False,
        "day_routine_workers": 1,
    },
    # Optional extension hooks for custom functions.
    # Each item uses "module:function" import path.
    "extensions": {
        "strict": False,
        "hooks": {
            "on_simulation_start": ["economy_module:on_simulation_start"],
            "on_day_start": ["economy_module:on_day_start"],
            "on_time_tick": [],
            "on_agent_pre_step": ["economy_module:on_agent_pre_step"],
            "on_agent_post_step": ["economy_module:on_agent_post_step"],
            "on_day_end": ["economy_module:on_day_end"],
            "on_simulation_end": ["economy_module:on_simulation_end"],
        },
    },
    # Real Work Execution (gaworld/work/*).
    # When enabled, "工作"-class activities can be dispatched to local
    # adapters that produce real artifacts (HTML / .py / .md / lesson
    # plans) under artifacts_dir, and agents can browse a mock job
    # market. Disabled by default — flipping on must not change any
    # other simulation behaviour.
    "real_work": {
        "enabled": True,
        "queue_path": "output/work/queue.jsonl",
        "artifacts_dir": "output/work",
        "capabilities_cache": "output/work/capabilities.json",
        "max_concurrent_tasks": 2,
        "task_timeout_seconds": 600,
        "tick_ingest_limit": 5,
        "adapters": {
            "web_design": {"enabled": True},
            "code": {"enabled": True, "write_pytest": True},
            "content": {"enabled": True},
            "teaching": {"enabled": True},
        },
        "market": {
            "enabled": True,
            "seed_path": "gaworld/work/market_seed.json",
            "store_path": "output/work/market.jsonl",
            "browse_top_k": 5,
            "max_taken_per_agent_per_day": 2,
            "browse_probability_base": 0.15,
            "expire_after_sim_days": 5,
            "auto_replenish": True,
            "replenish_threshold": 5,
        },
        "external_hooks": {
            "webhook_url": "",
            "mcp_server": "",
        },
    },
    # Planning Fork A/B Experiment.
    # When enabled, each LLM planning call is forked into two variants:
    #   Variant A: baseline (no Life History Context)
    #   Variant B: LH Context + constrained personality injection
    # Results are compared with statistical metrics to detect LH effect.
    "ab_experiment": {
        "enabled": False,
        "sample_rate": 1.0,  # 0.0-1.0, proportion of planning calls that fork
        "metrics_threshold": 0.05,  # p-value threshold for significance
        "output_dir": "output/planning_fork",
        "parallel_calls": True,  # run A/B LLM calls concurrently
        "variant_b": {
            "use_fewshot": True,
            "fewshot_examples": 3,
            "use_json_schema": True,
            "use_chain_of_personality": True,
            "personality_strength": "strong",  # strong | moderate | mild
        },
    },
}


def _deep_update(base, patch):
    if not isinstance(base, dict) or not isinstance(patch, dict):
        return base
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _load_env_override():
    raw = os.environ.get("GAWORLD_CONFIG_OVERRIDES", "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}

def _load_json_override(path):
    if not path:
        return {}
    target = str(path).strip()
    if not target:
        return {}
    if not os.path.isabs(target):
        target = os.path.join(os.path.dirname(__file__), target)
    if not os.path.exists(target):
        return {}
    try:
        with open(target, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}

def _load_environment_config(path):
    if not path:
        return {}
    target = str(path).strip()
    if not target:
        return {}
    if not os.path.isabs(target):
        target = os.path.join(os.path.dirname(__file__), target)
    if not os.path.exists(target):
        return {}
    try:
        with open(target, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    allowed = {}
    if isinstance(payload.get("environment"), dict):
        allowed["environment"] = payload["environment"]
    if isinstance(payload.get("external_environment"), dict):
        allowed["external_environment"] = payload["external_environment"]
    if isinstance(payload.get("external_environment_service"), dict):
        allowed["external_environment_service"] = payload["external_environment_service"]
    if isinstance(payload.get("environment_server"), dict):
        allowed["environment_server"] = payload["environment_server"]
    return allowed

_OVERRIDES = _load_env_override()
_deep_update(CONFIG, _load_json_override("dashboard_config.json"))
_deep_update(CONFIG, _OVERRIDES)
_deep_update(CONFIG, _load_environment_config(CONFIG.get("environment_config_path")))
_deep_update(CONFIG, _OVERRIDES)
