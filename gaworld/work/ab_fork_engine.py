"""Planning Layer Fork A/B Experiment Engine.

Each LLM planning call is forked into two variants:
- Variant A: baseline (no Life History Context)
- Variant B: LH Context + constrained personality injection

Results are compared using statistical metrics to determine if LH
has a significant effect on agent planning behavior.
"""
from __future__ import annotations

import json
import os
import random
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.work.ab_fork")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "enabled": False,
    "sample_rate": 1.0,  # 0.0-1.0, proportion of planning calls that fork
    "metrics_threshold": 0.05,  # p-value threshold for significance
    "output_dir": "output/planning_fork",
    "parallel_calls": True,  # run A/B calls concurrently
    "variant_b": {
        "use_fewshot": True,
        "fewshot_examples": 3,
        "use_json_schema": True,
        "use_chain_of_personality": True,
        "personality_strength": "strong",  # strong | moderate | mild
    },
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class VariantResult:
    """Result from a single planning variant."""

    variant_id: str  # "A" or "B"
    raw_response: str
    parsed: dict[str, str]  # {goal, constraint, urge, plan, expected_outcome}
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    error: str | None = None


@dataclass
class ForkComparison:
    """Result of comparing Variant A vs Variant B."""

    run_id: str
    agent_id: str
    timestep: int
    timestamp: str
    variant_a: VariantResult
    variant_b: VariantResult
    metrics: dict[str, Any]  # {action_kappa, reasoning_jaccard, trace_editdist, significance}
    is_significant: bool = False
    output_path: str | None = None


# ---------------------------------------------------------------------------
# LH Context Builder (Variant B only)
# ---------------------------------------------------------------------------

_PERSONALITY_TEMPLATES = {
    "strong": {
        "system": "你是一个性格鲜明的人。你的决定强烈受到你的性格影响。",
        "fewshot_intro": "以下是你性格如何影响决策的例子：",
    },
    "moderate": {
        "system": "你是一个有自己性格特点的人。性格会在一定程度上影响你的决定。",
        "fewshot_intro": "你的性格会在某些情况下体现：",
    },
    "mild": {
        "system": "你有自己的性格特点，这会影响你的思维方式。",
        "fewshot_intro": "参考你的性格倾向：",
    },
}


def _build_personality_examples(agent: dict, count: int = 3) -> str:
    """Generate few-shot examples showing personality → decision mapping."""
    personality = agent.get("personality", "")
    name = agent.get("name", "")

    examples = [
        {
            "situation": "工作中遇到不公平的批评",
            "personality": personality,
            "decision": "如果你是冲动型：直接反驳；如果是内向型：沉默但记在心里；如果是理性型：私下找机会解释",
        },
        {
            "situation": "朋友邀请参加一个你不太感兴趣的聚会",
            "personality": personality,
            "decision": "如果你是社交型：欣然前往；如果你是独处型：礼貌拒绝；如果是纠结型：找借口拖延",
        },
        {
            "situation": "看到有人在公共场所不守规矩",
            "personality": personality,
            "decision": "如果你是正义型：上前制止；如果你是回避型：假装没看见；如果是记录型：拍照发社交媒体",
        },
    ]

    selected = random.sample(examples, min(count, len(examples)))
    lines = [f"[示例{i+1}] 情况：{e['situation']} → 决策：{e['decision']}" for i, e in enumerate(selected)]
    return "\n".join(lines)


def _build_variant_a_prompt(
    agent: dict,
    perception_text: str,
    recall_context: dict,
    decision_refs: dict,
    intent_hint: str,
    optional_text: str,
    history_hint: str,
) -> str:
    """Build baseline planning prompt (no LH Context)."""
    memory_hint = recall_context.get("hint", "暂无重要经验")
    recollection = recall_context.get("recollection", "").strip() or "无明显回忆"
    emotion_text = decision_refs.get("emotion_text", "")
    external_hint = decision_refs.get("external_hint", "")

    prompt = f"""你是{agent['name']}。
你的感知是：{perception_text}
{emotion_text}
你的近期经验：{memory_hint}
你此刻被唤起的回忆：{recollection}
可用额外信息：{external_hint}
你今天的行为意图：{intent_hint}
其他可选参考（仅保留与当前规划强相关的部分）：
{optional_text}
你的近期历史片段：
{history_hint}

请输出 JSON：
{{
  "goal": "...",
  "constraint": "...",
  "urge": "...",
  "plan": "...",
  "expected_outcome": "..."
}}
要求：
1) 每个字段 8-30 字，中文。
2) constraint 必须是现实约束，urge 必须是内心冲动或偷懒/回避/社交/恢复倾向之一。
3) plan 要体现妥协，而不是完美理性答案。
4) 仅输出 JSON，不要其他文字。
"""
    return prompt


def _build_variant_b_prompt(
    agent: dict,
    perception_text: str,
    recall_context: dict,
    decision_refs: dict,
    intent_hint: str,
    optional_text: str,
    history_hint: str,
    config: dict,
) -> str:
    """Build Variant B prompt with LH Context + constrained personality injection."""
    memory_hint = recall_context.get("hint", "暂无重要经验")
    recollection = recall_context.get("recollection", "").strip() or "无明显回忆"
    emotion_text = decision_refs.get("emotion_text", "")
    external_hint = decision_refs.get("external_hint", "")
    personality = agent.get("personality", "")

    vb_cfg = config.get("variant_b", {})
    strength = vb_cfg.get("personality_strength", "strong")
    fewshot_count = vb_cfg.get("fewshot_examples", 3)
    use_chain = vb_cfg.get("use_chain_of_personality", True)
    use_json_schema = vb_cfg.get("use_json_schema", True)

    personality_tpl = _PERSONALITY_TEMPLATES.get(strength, _PERSONALITY_TEMPLATES["strong"])

    # System instruction (role enforcement)
    system_instr = personality_tpl["system"]

    # Few-shot examples
    fewshot_block = ""
    if vb_cfg.get("use_fewshot", True):
        fewshot_block = f"\n{personality_tpl['fewshot_intro']}\n{_build_personality_examples(agent, fewshot_count)}"

    # Chain-of-personality in reasoning
    chain_block = ""
    if use_chain:
        chain_block = """
在思考你的计划时，请先分析：
1. 你的性格（{personality}）会如何影响你对当前情况的判断？
2. 这种影响会让你更倾向于做什么选择？
3. 最终计划如何在保证现实约束的同时，体现你的性格倾向？
""".format(personality=personality)

    # JSON schema constraint
    schema_block = ""
    if use_json_schema:
        schema_block = """
输出格式（严格遵循）：
{{
  "goal": "...",
  "constraint": "...",
  "urge": "...",
  "plan": "...",
  "expected_outcome": "..."
}}"""

    prompt = f"""{system_instr}{fewshot_block}
你是{agent['name']}。
你的性格是：{personality}
{chain_block}
你的感知是：{perception_text}
{emotion_text}
你的近期经验：{memory_hint}
你此刻被唤起的回忆：{recollection}
可用额外信息：{external_hint}
你今天的行为意图：{intent_hint}
其他可选参考（仅保留与当前规划强相关的部分）：
{optional_text}
你的近期历史片段：
{history_hint}
{schema_block}
要求：
1) 每个字段 8-30 字，中文。
2) constraint 必须是现实约束，urge 必须是内心冲动或偷懒/回避/社交/恢复倾向之一。
3) plan 要体现妥协，而不是完美理性答案，同时要反映你的性格特点。
4) 仅输出 JSON，不要其他文字。
"""
    return prompt


# ---------------------------------------------------------------------------
# Core Fork Engine
# ---------------------------------------------------------------------------

class ABForkEngine:
    """A/B Fork Engine for planning layer experiments."""

    def __init__(self, config: dict | None = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.output_dir = self.config.get("output_dir", "output/planning_fork")
        os.makedirs(self.output_dir, exist_ok=True)

    def should_fork(self) -> bool:
        """Determine if this particular planning call should fork (based on sample_rate)."""
        if not self.config.get("enabled", False):
            return False
        return random.random() < self.config.get("sample_rate", 1.0)

    def plan_with_fork(
        self,
        agent: dict,
        perception_text: str,
        recall_context: dict,
        decision_refs: dict,
        intent_hint: str,
        optional_text: str,
        history_hint: str,
        call_llm_fn,
        timestep: int = 0,
    ) -> ForkComparison | None:
        """Execute A/B fork comparison for a single planning call.

        Returns None if should_fork() is False (caller should use normal planning).
        """
        if not self.should_fork():
            return None

        from gaworld.work.metrics import (
            calculate_action_kappa,
            calculate_reasoning_jaccard,
            calculate_trace_edit_distance,
            aggregate_significance,
        )

        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        agent_id = agent.get("id", "unknown")
        timestamp = datetime.now().isoformat()

        # Build prompts
        prompt_a = _build_variant_a_prompt(
            agent, perception_text, recall_context, decision_refs,
            intent_hint, optional_text, history_hint,
        )
        prompt_b = _build_variant_b_prompt(
            agent, perception_text, recall_context, decision_refs,
            intent_hint, optional_text, history_hint, self.config,
        )

        # Execute calls
        if self.config.get("parallel_calls", True):
            variant_a, variant_b = self._call_parallel(call_llm_fn, prompt_a, prompt_b, agent)
        else:
            variant_a, variant_b = self._call_sequential(call_llm_fn, prompt_a, prompt_b, agent)

        # Parse outputs
        parsed_a = self._parse_planning_response(variant_a.raw_response)
        parsed_b = self._parse_planning_response(variant_b.raw_response)

        variant_a.parsed = parsed_a
        variant_b.parsed = parsed_b

        # Calculate metrics
        metrics = {}
        try:
            metrics["action_kappa"] = calculate_action_kappa(
                list(parsed_a.values()), list(parsed_b.values())
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("action_kappa calculation failed: %s", exc)
            metrics["action_kappa"] = None

        try:
            metrics["reasoning_jaccard"] = calculate_reasoning_jaccard(
                parsed_a.get("plan", ""), parsed_b.get("plan", "")
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("reasoning_jaccard calculation failed: %s", exc)
            metrics["reasoning_jaccard"] = None

        try:
            trace_a = self._trace_from_parsed(parsed_a)
            trace_b = self._trace_from_parsed(parsed_b)
            ed_result = calculate_trace_edit_distance(trace_a, trace_b)
            metrics["trace_edit_distance"] = ed_result["distance"]
            metrics["trace_p_value"] = ed_result.get("p_value")
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("trace_edit_distance calculation failed: %s", exc)
            metrics["trace_edit_distance"] = None
            metrics["trace_p_value"] = None

        try:
            sig_result = aggregate_significance(metrics)
            metrics["significance"] = sig_result
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("aggregate_significance calculation failed: %s", exc)
            metrics["significance"] = {"significant": False, "p_value": 1.0}

        threshold = self.config.get("metrics_threshold", 0.05)
        is_significant = (
            metrics.get("significance", {}).get("p_value", 1.0) < threshold
        )

        comparison = ForkComparison(
            run_id=run_id,
            agent_id=agent_id,
            timestep=timestep,
            timestamp=timestamp,
            variant_a=variant_a,
            variant_b=variant_b,
            metrics=metrics,
            is_significant=is_significant,
        )

        # Save to disk
        output_path = self._save_comparison(comparison)
        comparison.output_path = output_path

        _LOG.info(
            "AB fork completed for agent %s step %d: significant=%s",
            agent_id, timestep, is_significant,
        )
        return comparison

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_parallel(
        self, call_llm_fn, prompt_a: str, prompt_b: str, agent: dict
    ) -> tuple[VariantResult, VariantResult]:
        """Execute both variant calls concurrently."""
        agent_id = agent.get("id", "unknown")

        def call_a():
            import time
            start = time.perf_counter()
            try:
                raw = call_llm_fn(prompt_a, task="planning", agent_id=agent_id, variant="A")
                return VariantResult(variant_id="A", raw_response=raw, parsed={})
            except Exception as exc:  # noqa: BLE001
                return VariantResult(variant_id="A", raw_response="", error=str(exc))

        def call_b():
            import time
            start = time.perf_counter()
            try:
                raw = call_llm_fn(prompt_b, task="planning", agent_id=agent_id, variant="B")
                return VariantResult(variant_id="B", raw_response=raw, parsed={})
            except Exception as exc:  # noqa: BLE001
                return VariantResult(variant_id="B", raw_response="", error=str(exc))

        with ThreadPoolExecutor(max_workers=2) as exc:
            future_a = exc.submit(call_a)
            future_b = exc.submit(call_b)
            result_a = future_a.result()
            result_b = future_b.result()

        return result_a, result_b

    def _call_sequential(
        self, call_llm_fn, prompt_a: str, prompt_b: str, agent: dict
    ) -> tuple[VariantResult, VariantResult]:
        """Execute variant calls one after another."""
        agent_id = agent.get("id", "")
        try:
            raw_a = call_llm_fn(prompt_a, task="planning", agent_id=agent_id, variant="A")
            variant_a = VariantResult(variant_id="A", raw_response=raw_a, parsed={})
        except Exception as exc:  # noqa: BLE001
            variant_a = VariantResult(variant_id="A", raw_response="", error=str(exc))

        try:
            raw_b = call_llm_fn(prompt_b, task="planning", agent_id=agent_id, variant="B")
            variant_b = VariantResult(variant_id="B", raw_response=raw_b, parsed={})
        except Exception as exc:  # noqa: BLE001
            variant_b = VariantResult(variant_id="B", raw_response="", error=str(exc))

        return variant_a, variant_b

    def _parse_planning_response(self, raw: str) -> dict[str, str]:
        """Parse JSON from LLM planning response."""
        if not raw:
            return {}
        # Try to extract JSON block
        import re
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if not json_match:
            return {}
        try:
            parsed = json.loads(json_match.group())
            # Validate required keys
            required = ["goal", "constraint", "urge", "plan", "expected_outcome"]
            return {k: str(parsed.get(k, "")) for k in required}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _trace_from_parsed(self, parsed: dict) -> str:
        """Build a decision trace string from parsed planning output."""
        return " → ".join([
            parsed.get("goal", ""),
            parsed.get("constraint", ""),
            parsed.get("urge", ""),
            parsed.get("plan", ""),
            parsed.get("expected_outcome", ""),
        ])

    def _save_comparison(self, comparison: ForkComparison) -> str:
        """Write comparison result to JSON file."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        run_prefix = f"run-{date_str}"

        # Organize by agent_id / timestep
        agent_dir = os.path.join(
            self.output_dir, run_prefix, "variants", comparison.agent_id
        )
        os.makedirs(agent_dir, exist_ok=True)

        path = os.path.join(agent_dir, f"step_{comparison.timestep}.json")
        payload = {
            "run_id": comparison.run_id,
            "agent_id": comparison.agent_id,
            "timestep": comparison.timestep,
            "timestamp": comparison.timestamp,
            "variant_a": {
                "raw": comparison.variant_a.raw_response,
                "parsed": comparison.variant_a.parsed,
                "error": comparison.variant_a.error,
            },
            "variant_b": {
                "raw": comparison.variant_b.raw_response,
                "parsed": comparison.variant_b.parsed,
                "error": comparison.variant_b.error,
            },
            "metrics": comparison.metrics,
            "is_significant": comparison.is_significant,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # Also update significance summary
        self._update_significance_summary(run_prefix, comparison)

        return path

    def _update_significance_summary(self, run_prefix: str, comparison: ForkComparison):
        """Append to or create significance summary file for the run."""
        summary_path = os.path.join(self.output_dir, run_prefix, "significance_summary.json")

        if os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary = json.load(f)
            except (json.JSONDecodeError, OSError):
                summary = {"runs": []}
        else:
            summary = {"runs": []}

        summary["runs"].append({
            "agent_id": comparison.agent_id,
            "timestep": comparison.timestep,
            "metrics": comparison.metrics,
            "is_significant": comparison.is_significant,
        })

        # Recalculate aggregate significance
        runs = summary.get("runs", [])
        if len(runs) >= 2:
            total_significant = sum(1 for r in runs if r.get("is_significant"))
            summary["aggregate_significance_rate"] = total_significant / len(runs)

        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_engine: ABForkEngine | None = None


def get_engine(config: dict | None = None) -> ABForkEngine:
    """Get or create the global ABForkEngine instance."""
    global _engine
    if _engine is None:
        _engine = ABForkEngine(config)
    elif config is not None:
        # Update config if provided
        _engine.config.update(config)
    return _engine