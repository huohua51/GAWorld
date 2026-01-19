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
                "api_key_env": "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",
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
    "agent_ids": [31, 1, 5],
    "sim_days": 1,
    "seconds_per_day": 30,
    # Data sources
    "csv_path": "hangzhou_agents_state_init.csv",
    "md_path": "hangzhou_profiles_with_names.md",
    # Memory / logs
    "stateful": True,
    "memory_dir": "output/memory",
    "log_dir": "output/logs",
    # Policy events (description only; effect inferred by LLM)
    "policy_events": [
        {
            "day": 1,
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
}
