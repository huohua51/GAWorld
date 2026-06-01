"""Cognition primitives extracted from ``generative_city_sim.py``.

Scope of this module — the *now-unblocked* subset of the legacy
``# A. 认知模块`` and ``# 社会影响`` banners:

* ``get_social_context`` — sample today's social-partner mentions
* ``perception`` — thin LLM wrapper for per-tick perception
* ``social_influence`` — relationship-weighted emotion contagion

These were originally entangled with ``HUMAN_REALISM_ENABLED``,
``relationship_weight`` (from ``human_realism``) and ``call_llm`` (from
``llm_providers``). All three sources have now migrated into the
``gaworld`` package, so this module can import them directly.

Intentionally out of scope:

* ``planning`` / ``reflection`` — still depend on ``evoke_memory``,
  ``_current_emotion_text``, ``_parse_structured_json`` and other
  helpers that live in ``generative_city_sim.py``. They'll move when
  those helpers are also extracted.
* ``interview_agent`` — depends on ``evoke_memory``.
"""

from __future__ import annotations

import random
from typing import Any

from gaworld.cognition.realism import relationship_weight
from gaworld.llm import providers as _llm_providers
from gaworld.settings import CONFIG
from gaworld.skills.prompt_helpers import render_agent_skills
from gaworld.skills.registry import SkillRegistry, get_default_registry

# NB: access ``call_llm`` via ``_llm_providers.call_llm`` rather than a
# ``from`` import. The mock installer in ``tests/fixtures/mock_llm.py``
# patches by *reassigning* the module attribute — a ``from`` import here
# would capture the original function reference and miss the patch.

_HUMAN_REALISM_CONFIG: dict[str, Any] = CONFIG.get("human_realism", {})
HUMAN_REALISM_ENABLED: bool = bool(_HUMAN_REALISM_CONFIG.get("enabled", False))


def _fos_fast_mode_cfg() -> dict[str, Any]:
    cfg = CONFIG.get("fos_fast_mode", {}) if isinstance(CONFIG, dict) else {}
    return cfg if isinstance(cfg, dict) else {}


def _deterministic_cognition_enabled() -> bool:
    return bool(_fos_fast_mode_cfg().get("deterministic_cognition", False))


def _skills_cfg() -> dict[str, Any]:
    s = CONFIG.get("skills", {}) if isinstance(CONFIG, dict) else {}
    return s if isinstance(s, dict) else {}


def _agent_skill_block(
    agent: dict[str, Any],
    *,
    registry: SkillRegistry | None = None,
) -> str:
    """Render the agent's currently-held skills as a labelled block.

    Returns an empty string when the agent has no skills, when the
    feature is disabled in config, or when the registry can't be
    loaded — callers should branch on the string.
    """
    cfg = _skills_cfg()
    if not cfg.get("inject_into_cognition", True):
        return ""
    try:
        reg = registry or get_default_registry()
        skills = reg.list_for_agent(agent)
    except Exception:  # noqa: BLE001 — never let skill rendering break perception
        return ""
    if not skills:
        return ""
    max_n = int(cfg.get("max_per_prompt", 4))
    rendered = render_agent_skills(skills, max_skills=max_n)
    if not rendered:
        return ""
    return f"你已经掌握的小技能：\n{rendered}"


# ---------------------------------------------------------------------------
# Social context sampling (per-day "who did you think about" fragments).
# ---------------------------------------------------------------------------

def get_social_context(agent: dict[str, Any], agents_by_id: dict[Any, dict[str, Any]]) -> str:
    neighbors = agent["social_neighbors"]
    agent["_recent_social_partners"] = []
    if not neighbors:
        return "今天几乎没有与熟人互动。"
    k = min(3, len(neighbors))
    if HUMAN_REALISM_ENABLED:
        sampled: list[Any] = []
        pool = list(neighbors)
        for _ in range(k):
            weights = [max(0.01, relationship_weight(agent, n)) for n in pool]
            pick = random.choices(pool, weights=weights, k=1)[0]
            sampled.append(pick)
            pool = [n for n in pool if n != pick]
            if not pool:
                break
    else:
        sampled = random.sample(neighbors, k)
    agent["_recent_social_partners"] = sampled
    fragments: list[str] = []
    relationships = agent.get("relationships", {})
    for neighbor_id in sampled:
        name = agents_by_id.get(neighbor_id, {}).get("name", str(neighbor_id))
        rel = relationships.get(str(neighbor_id), {}) if isinstance(relationships, dict) else {}
        closeness = float(rel.get("closeness", 0.5))
        obligation = float(rel.get("obligation", 0.5))
        friction = float(rel.get("friction", 0.5))
        if friction > 0.62:
            fragments.append(f"{name}最近让你有些顾虑，想到对方时会有一点摩擦感")
        elif obligation > 0.65:
            fragments.append(f"{name}最近可能等你回应或配合，这会带来一点责任压力")
        elif closeness > 0.65:
            fragments.append(f"{name}会给你支持感，你更容易想到和对方保持联系")
        else:
            fragments.append(f"{name}的近况会偶尔分散你的注意力")
    return "；".join(fragments) if fragments else "今天几乎没有与熟人互动。"


# ---------------------------------------------------------------------------
# Perception (thin LLM wrapper).
# ---------------------------------------------------------------------------

def perception(
    agent: dict[str, Any],
    time_str: str,
    social_context: str,
    env_context: str,
    policy_event: str,
) -> str:
    if _deterministic_cognition_enabled():
        social_text = str(social_context or "").strip() or "周围的人没有太多新变化"
        env_text = str(env_context or "").strip() or "环境整体比较平稳"
        policy_text = str(policy_event or "").strip()
        if policy_text:
            return f"我注意到{env_text}，也感到{social_text}，政策上的变化让我会顺手多留意一下。"
        return f"我注意到{env_text}，也感到{social_text}，所以更想先按当前节奏把这段时间过稳。"
    skill_block = _agent_skill_block(agent)
    skill_suffix = f"\n{skill_block}\n" if skill_block else ""
    prompt = f"""
你是{agent['name']}。
现在是 {time_str}。
你感知到的社交环境是：{social_context}
自然与社会环境：{env_context if env_context else "无特殊变化"}
政策环境：{policy_event if policy_event else "无特殊变化"}
{skill_suffix}
请描述你此刻对环境、他人和制度的感知。（1-2句）
"""
    return _llm_providers.call_llm(prompt, task="perception", agent_id=agent["id"])


# ---------------------------------------------------------------------------
# Social influence (relationship-weighted emotion contagion).
# ---------------------------------------------------------------------------

def social_influence(agent: dict[str, Any], agents_by_id: dict[Any, dict[str, Any]]) -> None:
    neighbors = agent["social_neighbors"]
    if not neighbors:
        return
    if HUMAN_REALISM_ENABLED:
        weights = [max(0.01, relationship_weight(agent, n)) for n in neighbors]
        total = sum(weights)
        if total <= 0:
            avg_emotion = sum(agents_by_id[n]["state"]["emotion"] for n in neighbors) / len(neighbors)
        else:
            avg_emotion = sum(
                agents_by_id[n]["state"]["emotion"] * w for n, w in zip(neighbors, weights)
            ) / total
    else:
        avg_emotion = sum(agents_by_id[n]["state"]["emotion"] for n in neighbors) / len(neighbors)
    agent["state"]["emotion"] += 0.1 * (avg_emotion - agent["state"]["emotion"])


__all__ = [
    "HUMAN_REALISM_ENABLED",
    "_agent_skill_block",
    "get_social_context",
    "perception",
    "social_influence",
]
