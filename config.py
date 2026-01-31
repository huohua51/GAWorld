CONFIG = {
    # LLM (legacy defaults for compatibility)
    "ollama_url": "http://localhost:11434/api/generate",
    "model_name": "gemma3n:e4b",
    "llm_timeout": 120,
    # LLM routing (multi-backend)
    "llm": {
        "providers": {
            "ollama_local": {
                "type": "ollama",
                "url": "http://localhost:11434/api/generate",
                "model": "gemma3n:e4b",
                "timeout": 120,
            },
            "ollama_gemma12": {
                "type": "ollama",
                "url": "http://localhost:11434/api/generate",
                "model": "gemma3:12b",
                "timeout": 120,
            },
            "openai_gpt": {
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4.1",
                "api_key_env": "OPENAI_API_KEY",
                "timeout": 120,
            },
            "claude": {
                "type": "claude",
                "base_url": "https://www.packyapi.com",
                "model": "gpt-4.1",
                "ANTHROPIC_AUTH_TOKEN": "sk-b0n7ujizk2dHMXnuiWUzHJ6tnGzbRRdPP2YK7hdxV0Xk5Pt7",
                "timeout": 120,
            },
        },
        "routing": {
            "default": "ollama_local",
            "tasks": {
                "schedule": "ollama_local",
            },
        },
    },
    # Simulation
    "agent_ids": [51],
    "sim_days": 1,
    "seconds_per_day": 10,
    "print_agent_profile": False,
    # Time step for simulation timeline (minutes). None/0 uses schedule times only.
    "time_step_minutes": "2 hours",
    #"time_step_minutes": None,
    # Simulation background (time/city/societal status prompt)
    "background": "2025年冬季，中国·杭州。经济发展中等偏稳，青年就业压力上升，生活成本偏高；社会秩序稳定但政策与舆论压力较高。",
    # Data sources
    "csv_path": "hangzhou_agents_state_init.csv",
    "md_path": "hangzhou_profiles_with_names.md",
    # Memory / logs
    "stateful": True,
    "memory_dir": "output/memory",
    "log_dir": "output/logs",
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
    # Environment system
    "environment": {
        "enabled": True,
        "event_chance": 0.6,
        "max_events_per_tick": 2,
        "natural_events": [
            "Light rain in the afternoon",
            "Cold front arrives, temperature drops",
            "Dense fog in the morning",
            "Heat wave alert",
            "Poor air quality warning"
        ],
        "social_events": [
            "Traffic congestion on main roads",
            "Public transit delay",
            "City marathon causing road closures",
            "Neighborhood market fair",
            "Minor protest near city center"
        ]
    },
    # Routine change (chance to deviate from schedule during the day)
    "routine_change": {
        "enabled": True,
        "base_chance": 0.08,
        "event_boost": 0.08,
        "policy_boost": 0.05,
        "max_chance": 0.45,
    },
}
