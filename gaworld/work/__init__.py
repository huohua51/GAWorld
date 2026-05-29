"""Real Work Execution subsystem.

Lets simulation agents perform actual work (designing pages, writing
code/articles/lesson plans) based on their profile-derived
capabilities, plus a mock job market they can browse and accept.

Public surface kept intentionally small — most callers only need
``router.maybe_dispatch`` and ``ingest.absorb_completed_for``.
"""

from gaworld.work.schemas import (
    AgentCapabilities,
    MarketJob,
    WorkBrief,
    WorkResult,
)

__all__ = [
    "AgentCapabilities",
    "MarketJob",
    "WorkBrief",
    "WorkResult",
]
