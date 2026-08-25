"""Real Work Execution subsystem.

Lets simulation agents perform actual work (designing pages, writing
code/articles/lesson plans) based on their profile-derived
capabilities, plus a mock job market they can browse and accept.

Public surface kept intentionally small — most callers only need
``router.maybe_dispatch`` and ``ingest.absorb_completed_for``.
"""

from gaworld.work.artifact_facts import ArtifactFact, extract_facts, verify_review
from gaworld.work.continuity import CHECKPOINT_VERSION, WorkflowCheckpointChannel, next_step
from gaworld.work.plan_registry import PlanRegistry
from gaworld.work.coordination import JointAssignmentChannel, actual_final_conflict_free, occupancy_table
from gaworld.work.review import ReviewAction, ReviewChannel
from gaworld.work.schemas import (
    AgentCapabilities,
    MarketJob,
    WorkBrief,
    WorkResult,
)

__all__ = [
    "ArtifactFact",
    "extract_facts",
    "verify_review",
    "WorkflowCheckpointChannel",
    "CHECKPOINT_VERSION",
    "next_step",
    "PlanRegistry",
    "JointAssignmentChannel",
    "actual_final_conflict_free",
    "occupancy_table",
    "AgentCapabilities",
    "MarketJob",
    "ReviewAction",
    "ReviewChannel",
    "WorkBrief",
    "WorkResult",
]
