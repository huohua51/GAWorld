"""Environment, distributed simulation, and external-agent defaults."""

from __future__ import annotations

from typing import Any


def environment_settings() -> dict[str, Any]:
    return {
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
            # Empty list = open (no auth required). Set via POST /auth/token or here.
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
        "environment_server": {
            "host": "0.0.0.0",
            "port": 8765,
            "state_path": "output/environment/server_state.json",
            "use_llm": True,
        },
    }
