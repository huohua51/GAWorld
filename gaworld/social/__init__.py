"""Hook-based social interaction subsystem for GAWorld."""

from gaworld.social.network import build_social_graph, load_seed_agents
from gaworld.social.schemas import AgentNode, RelationshipEdge, SocialInteractionEvent

__all__ = [
    "AgentNode",
    "RelationshipEdge",
    "SocialInteractionEvent",
    "build_social_graph",
    "load_seed_agents",
]
