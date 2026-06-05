"""Tests for Planning Fork A/B Experiment Engine."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime

import pytest

from gaworld.work.ab_fork_engine import (
    ABForkEngine,
    DEFAULT_CONFIG,
    ForkComparison,
    VariantResult,
    _build_variant_a_prompt,
    _build_variant_b_prompt,
    _build_personality_examples,
)
from gaworld.work.metrics import (
    calculate_action_kappa,
    calculate_reasoning_jaccard,
    calculate_trace_edit_distance,
    aggregate_significance,
    levenshtein_distance,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_agent():
    return {
        "id": "agent_001",
        "name": "张三",
        "age": 35,
        "job": "软件工程师",
        "personality": "内向、理性、追求完美",
        "daily_life": "早出晚归，加班较多",
        "values": "重视技术成长，看重工作成就",
    }


@pytest.fixture
def sample_recall_context():
    return {
        "hint": "最近在项目中遇到一些挑战",
        "recollection": "上次加班到很晚，感觉很疲惫",
    }


@pytest.fixture
def sample_decision_refs():
    return {
        "emotion_text": "当前情绪：有些焦虑",
        "memory_hint": "近期经验：项目进度压力大",
        "recollection": "无明显回忆",
        "physical_env_relevant": False,
        "social_env_relevant": True,
        "social_env_text": "公司最近有新政策",
        "location_time_relevant": False,
        "social_network_relevant": False,
        "external_hint": "外部信息：行业动态",
    }


@pytest.fixture
def engine_with_temp_dir(tmp_path):
    config = {**DEFAULT_CONFIG, "output_dir": str(tmp_path / "output")}
    return ABForkEngine(config)


# ---------------------------------------------------------------------------
# Variant Prompt Building
# ---------------------------------------------------------------------------

class TestVariantPrompts:
    def test_variant_a_prompt_built(self, sample_agent, sample_recall_context, sample_decision_refs):
        prompt = _build_variant_a_prompt(
            agent=sample_agent,
            perception_text="今天天气不错",
            recall_context=sample_recall_context,
            decision_refs=sample_decision_refs,
            intent_hint="完成项目",
            optional_text="无其他参考",
            history_hint="最近表现正常",
        )
        assert "你是张三" in prompt
        assert "今天天气不错" in prompt
        # Should NOT contain personality injection
        assert "性格" not in prompt or "性格" in sample_decision_refs.get("emotion_text", "")
        assert "约束" in prompt  # JSON schema field

    def test_variant_b_prompt_contains_personality(self, sample_agent, sample_recall_context, sample_decision_refs):
        config = {**DEFAULT_CONFIG, "variant_b": {"use_chain_of_personality": True, "personality_strength": "strong"}}
        prompt = _build_variant_b_prompt(
            agent=sample_agent,
            perception_text="今天天气不错",
            recall_context=sample_recall_context,
            decision_refs=sample_decision_refs,
            intent_hint="完成项目",
            optional_text="无其他参考",
            history_hint="最近表现正常",
            config=config,
        )
        assert "性格" in prompt
        assert "内向、理性、追求完美" in prompt
        # Chain-of-personality section
        assert "你的性格" in prompt or "性格" in prompt

    def test_variant_b_prompt_fewshot_examples(self, sample_agent, sample_recall_context, sample_decision_refs):
        config = {**DEFAULT_CONFIG, "variant_b": {"use_fewshot": True, "fewshot_examples": 3}}
        prompt = _build_variant_b_prompt(
            agent=sample_agent,
            perception_text="今天天气不错",
            recall_context=sample_recall_context,
            decision_refs=sample_decision_refs,
            intent_hint="完成项目",
            optional_text="无其他参考",
            history_hint="最近表现正常",
            config=config,
        )
        # Few-shot examples should be present
        assert "示例" in prompt or "例" in prompt


# ---------------------------------------------------------------------------
# Personality Examples
# ---------------------------------------------------------------------------

class TestPersonalityExamples:
    def test_build_personality_examples_count(self, sample_agent):
        examples = _build_personality_examples(sample_agent, count=3)
        # Should produce 3 example lines
        assert "示例" in examples or "情况" in examples
        lines = examples.strip().split("\n")
        assert len(lines) == 3

    def test_build_personality_examples_different_agent(self):
        agent = {"name": "李四", "personality": "冲动型人格"}
        examples = _build_personality_examples(agent, count=2)
        assert len(examples.strip().split("\n")) == 2


# ---------------------------------------------------------------------------
# Engine Core
# ---------------------------------------------------------------------------

class TestABForkEngine:
    def test_engine_disabled_by_default(self):
        engine = ABForkEngine()
        assert engine.config["enabled"] is False
        assert engine.should_fork() is False

    def test_engine_enabled_with_sample_rate(self):
        config = {**DEFAULT_CONFIG, "enabled": True, "sample_rate": 1.0}
        engine = ABForkEngine(config)
        assert engine.should_fork() is True

    def test_engine_disabled_with_zero_sample_rate(self):
        config = {**DEFAULT_CONFIG, "enabled": True, "sample_rate": 0.0}
        engine = ABForkEngine(config)
        assert engine.should_fork() is False

    def test_engine_output_dir_created(self, tmp_path):
        output_dir = tmp_path / "fork_output"
        config = {**DEFAULT_CONFIG, "output_dir": str(output_dir)}
        engine = ABForkEngine(config)
        assert output_dir.exists()

    def test_trace_from_parsed(self, engine_with_temp_dir):
        parsed = {
            "goal": "完成项目",
            "constraint": "时间有限",
            "urge": "想要休息",
            "plan": "加班赶进度",
            "expected_outcome": "按时交付",
        }
        trace = engine_with_temp_dir._trace_from_parsed(parsed)
        assert "完成项目" in trace
        assert "→" in trace


# ---------------------------------------------------------------------------
# Variant Result Parsing
# ---------------------------------------------------------------------------

class TestVariantParsing:
    def test_parse_valid_json_response(self, engine_with_temp_dir):
        raw = '{"goal": "完成项目", "constraint": "时间有限", "urge": "想要休息", "plan": "加班赶进度", "expected_outcome": "按时交付"}'
        parsed = engine_with_temp_dir._parse_planning_response(raw)
        assert parsed["goal"] == "完成项目"
        assert parsed["plan"] == "加班赶进度"

    def test_parse_json_with_extra_text(self, engine_with_temp_dir):
        raw = "以下是规划：\n{" + '"goal": "完成项目", "constraint": "时间有限", "urge": "想要休息", "plan": "加班赶进度", "expected_outcome": "按时交付"}' + "\n请注意执行。"
        parsed = engine_with_temp_dir._parse_planning_response(raw)
        assert parsed["goal"] == "完成项目"

    def test_parse_invalid_response(self, engine_with_temp_dir):
        raw = "这不是有效的JSON响应"
        parsed = engine_with_temp_dir._parse_planning_response(raw)
        assert parsed == {}

    def test_parse_empty_response(self, engine_with_temp_dir):
        parsed = engine_with_temp_dir._parse_planning_response("")
        assert parsed == {}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_action_kappa_identical_outputs(self):
        items_a = ["完成项目", "时间有限", "想要休息", "加班赶进度", "按时交付"]
        items_b = ["完成项目", "时间有限", "想要休息", "加班赶进度", "按时交付"]
        kappa = calculate_action_kappa(items_a, items_b)
        # Identical outputs should give high kappa (close to 1.0)
        assert kappa > 0.9

    def test_action_kappa_different_outputs(self):
        items_a = ["完成项目", "时间有限", "想要休息", "加班赶进度", "按时交付"]
        items_b = ["不完成项目", "时间无限", "不想休息", "不加班", "延迟交付"]
        kappa = calculate_action_kappa(items_a, items_b)
        # Different outputs should give lower kappa
        assert kappa < 0.5

    def test_action_kappa_empty(self):
        assert calculate_action_kappa([], []) == 0.0
        assert calculate_action_kappa(["a"], []) == 0.0

    def test_reasoning_jaccard_identical(self):
        text = "这是一个测试文本用于测试Jaccard相似度"
        jaccard = calculate_reasoning_jaccard(text, text)
        assert jaccard == 1.0

    def test_reasoning_jaccard_different(self):
        jaccard = calculate_reasoning_jaccard("今天天气很好", "明天可能要下雨")
        assert 0.0 <= jaccard <= 1.0

    def test_reasoning_jaccard_empty(self):
        assert calculate_reasoning_jaccard("", "") == 1.0
        assert calculate_reasoning_jaccard("text", "") == 0.0
        assert calculate_reasoning_jaccard("", "text") == 0.0

    def test_levenshtein_identical(self):
        assert levenshtein_distance("hello", "hello") == 0

    def test_levenshtein_insertion(self):
        assert levenshtein_distance("hello", "hallo") == 1

    def test_levenshtein_deletion(self):
        assert levenshtein_distance("hello", "helo") == 1

    def test_levenshtein_substitution(self):
        assert levenshtein_distance("hello", "hellx") == 1

    def test_levenshtein_empty(self):
        assert levenshtein_distance("", "") == 0
        assert levenshtein_distance("hello", "") == 5
        assert levenshtein_distance("", "hello") == 5

    def test_trace_edit_distance(self):
        trace_a = "goal → constraint → urge → plan → outcome"
        trace_b = "goal → different_constraint → urge → different_plan → outcome"
        result = calculate_trace_edit_distance(trace_a, trace_b)
        assert "distance" in result
        assert "normalized_distance" in result
        assert "p_value" in result
        assert result["distance"] >= 0
        assert 0.0 <= result["normalized_distance"] <= 1.0

    def test_trace_edit_distance_identical(self):
        trace = "goal → constraint → urge → plan → outcome"
        result = calculate_trace_edit_distance(trace, trace)
        assert result["distance"] == 0
        assert result["normalized_distance"] == 0.0
        assert result["p_value"] == 1.0

    def test_aggregate_significance_all_metrics(self):
        metrics = {
            "action_kappa": 0.3,  # Low kappa = more different
            "reasoning_jaccard": 0.3,  # Low Jaccard = more different
            "trace_p_value": 0.01,  # Significant difference
        }
        result = aggregate_significance(metrics)
        assert "significant" in result
        assert "p_value" in result
        assert result["significant"] is True
        assert result["p_value"] < 0.05

    def test_aggregate_significance_no_difference(self):
        metrics = {
            "action_kappa": 0.95,  # High kappa = similar
            "reasoning_jaccard": 0.95,  # High Jaccard = similar
            "trace_p_value": 0.5,  # Not significant
        }
        result = aggregate_significance(metrics)
        assert result["significant"] is False
        assert result["p_value"] > 0.05

    def test_aggregate_significance_empty_metrics(self):
        result = aggregate_significance({})
        assert result["significant"] is False
        assert result["p_value"] == 1.0


# ---------------------------------------------------------------------------
# ForkComparison Dataclass
# ---------------------------------------------------------------------------

class TestForkComparison:
    def test_fork_comparison_create(self):
        variant_a = VariantResult(variant_id="A", raw_response="response_a", parsed={"goal": "a"})
        variant_b = VariantResult(variant_id="B", raw_response="response_b", parsed={"goal": "b"})
        comparison = ForkComparison(
            run_id="run_001",
            agent_id="agent_001",
            timestep=0,
            timestamp="2026-05-30T12:00:00",
            variant_a=variant_a,
            variant_b=variant_b,
            metrics={"action_kappa": 0.5},
            is_significant=True,
        )
        assert comparison.variant_a.parsed["goal"] == "a"
        assert comparison.variant_b.parsed["goal"] == "b"
        assert comparison.is_significant is True


# ---------------------------------------------------------------------------
# Save Comparison
# ---------------------------------------------------------------------------

class TestSaveComparison:
    def test_save_comparison_creates_file(self, tmp_path):
        output_dir = tmp_path / "fork_output"
        config = {**DEFAULT_CONFIG, "output_dir": str(output_dir)}
        engine = ABForkEngine(config)

        variant_a = VariantResult(variant_id="A", raw_response="response_a", parsed={"goal": "a"})
        variant_b = VariantResult(variant_id="B", raw_response="response_b", parsed={"goal": "b"})
        comparison = ForkComparison(
            run_id="run_001",
            agent_id="agent_001",
            timestep=5,
            timestamp="2026-05-30T12:00:00",
            variant_a=variant_a,
            variant_b=variant_b,
            metrics={"action_kappa": 0.5},
            is_significant=True,
        )

        path = engine._save_comparison(comparison)
        assert os.path.exists(path)

        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["agent_id"] == "agent_001"
        assert saved["timestep"] == 5
        assert saved["is_significant"] is True

    def test_significance_summary_updated(self, tmp_path):
        output_dir = tmp_path / "fork_output"
        config = {**DEFAULT_CONFIG, "output_dir": str(output_dir)}
        engine = ABForkEngine(config)

        variant_a = VariantResult(variant_id="A", raw_response="response_a", parsed={})
        variant_b = VariantResult(variant_id="B", raw_response="response_b", parsed={})
        comparison = ForkComparison(
            run_id="run_001",
            agent_id="agent_001",
            timestep=0,
            timestamp="2026-05-30T12:00:00",
            variant_a=variant_a,
            variant_b=variant_b,
            metrics={},
            is_significant=False,
        )

        engine._save_comparison(comparison)

        today = datetime.now().strftime("%Y-%m-%d")
        summary_path = os.path.join(str(output_dir), f"run-{today}", "significance_summary.json")
        assert os.path.exists(summary_path)

        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
        assert "runs" in summary
        assert len(summary["runs"]) == 1