"""Core simulation primitives: Agent dataclass, concurrency runner."""

from gaworld.core.agent import Agent, ensure_agent_dict, view_as_agent
from gaworld.core.runner import parallel_map, resolve_max_workers

__all__ = [
    "Agent",
    "ensure_agent_dict",
    "parallel_map",
    "resolve_max_workers",
    "view_as_agent",
]
