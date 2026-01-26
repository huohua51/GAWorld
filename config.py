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
    "agent_ids": [45],
    "sim_days": 1,
    "seconds_per_day": 10,
    "print_agent_profile": False,
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
