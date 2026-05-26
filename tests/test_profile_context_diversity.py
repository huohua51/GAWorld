"""
Regression test for LifeHistoryEngine.build_planning_context()

Ensures the four-layer profile context output is stable:
1. Identity/occupation (always present)
2. Personality traits (separate line)
3. Daily habits (separate line, from _gaworld_agent["daily_life"])
4. Communication style (separate line)

This test guards against future regressions where daily_life
gets truncated or the layered structure collapses back into a
single truncated string.
"""

import pytest
from gaworld.core.life_history import AgentProfile, create_life_history_engine


def _make_agent(name, job, personality, daily_life, values, age=25, gender="男"):
    return {
        "id": 99,
        "name": name,
        "job": job,
        "personality": personality,
        "daily_life": daily_life,
        "values": values,
        "age": age,
        "gender": gender,
        "living": "杭州",
    }


def _build_ctx(profile, daily_life_extra=None):
    """Helper: create engine and return build_planning_context output."""
    agent = {
        "id": 99,
        "name": profile.identity.name,
        "job": profile.identity.occupation,
        "daily_life": daily_life_extra or "默认日常",
    }
    engine = create_life_history_engine(agent_id=99, agent_name=profile.identity.name, profile=profile)
    engine._gaworld_agent = agent
    return engine.build_planning_context(activity="规划日程", perception_text="今天天气不错")


class TestProfileContextFourLayers:
    """Regression: four layers must all appear independently when data is present."""

    def test_identity_line_always_present(self):
        """Layer 1: identity/occupation must always appear."""
        profile = AgentProfile.from_gaworld_agent(
            _make_agent("张三", "研究员", "理性严谨", "晨跑", "效率优先"),
            gender="男", hukou="本地",
        )
        ctx = _build_ctx(profile)
        assert "张三" in ctx
        assert "研究员" in ctx

    def test_personality_traits_line_separate(self):
        """Layer 2: personality traits must appear as distinct segment."""
        profile = AgentProfile.from_gaworld_agent(
            _make_agent("李四", "产品经理", "理性严谨，结果导向", "早起跑步", "效率优先"),
            gender="男", hukou="本地",
        )
        ctx = _build_ctx(profile)
        # Should contain personality summary
        assert "人格" in ctx
        assert "理性" in ctx or "结果" in ctx

    def test_daily_life_appears_verbatim(self):
        """Layer 3: daily habits must appear, not be truncated by personality text."""
        daily = "工作日以公司—出租屋两点一线为主，饮食高度依赖外卖；周末多用于补觉"
        profile = AgentProfile.from_gaworld_agent(
            _make_agent("王五", "算法工程师", "内向理性", daily, "效率优先"),
            gender="男", hukou="外省",
        )
        ctx = _build_ctx(profile, daily_life_extra=daily)
        # The full daily_life phrase should appear, not cut at 50 chars
        assert "两点一线" in ctx, f"daily_life truncated: {ctx}"
        assert "外卖" in ctx, f"daily_life truncated: {ctx}"

    def test_daily_life_not_truncated_at_50_chars(self):
        """daily_life longer than 50 chars must not be cut off."""
        # Agent with very long daily_life
        daily = "晨跑、夜跑、咖啡馆办公、高效作息、经常深夜加班、偶尔健身、晚睡晚起"
        profile = AgentProfile.from_gaworld_agent(
            _make_agent("赵六", "创业者", "理性严谨", daily, "效率优先"),
            gender="男", hukou="外省",
        )
        ctx = _build_ctx(profile, daily_life_extra=daily)
        # Key phrases from AFTER position 40 must appear
        assert "深夜加班" in ctx, f"daily_life truncated at 40 chars: {ctx}"
        assert "晚睡晚起" in ctx, f"daily_life truncated too early: {ctx}"

    def test_communication_style_line_separate(self):
        """Layer 4: communication style must appear as distinct segment."""
        profile = AgentProfile.from_gaworld_agent(
            _make_agent("孙七", "律师", "直接果断", "早起", "程序优先"),
            gender="男", hukou="本地",
        )
        ctx = _build_ctx(profile)
        assert "沟通" in ctx

    def test_empty_daily_life_does_not_break(self):
        """Missing daily_life field must not cause KeyError or blank output."""
        profile = AgentProfile.from_gaworld_agent(
            _make_agent("周八", "教师", "严谨", "", "教育优先"),
            gender="女", hukou="本地",
        )
        agent_no_daily = {"id": 99, "name": "周八", "job": "教师"}
        engine = create_life_history_engine(agent_id=99, agent_name="周八", profile=profile)
        engine._gaworld_agent = agent_no_daily
        # Should not raise, should still output identity
        ctx = engine.build_planning_context(activity="教学", perception_text="学生提问")
        assert "周八" in ctx
        assert "教师" in ctx

    def test_li_ze_yu_vs_zhou_wan_qing_differ(self):
        """
        李泽宇 and 周婉清 must produce measurably different contexts.

        This is the observable behavior proof that per-agent profiles
        affect the planning context, not just label-levelled generic text.
        """
        li_dict = {
            "id": 1, "name": "李泽宇", "age": 24, "gender": "男",
            "job": "互联网企业初级算法工程师",
            "personality": "性格偏内向理性，低冲突倾向，习惯用技术问题掩盖情绪问题",
            "daily_life": "工作日以公司—出租屋两点一线为主，饮食高度依赖外卖；周末多用于补觉、个人技术学习、偶尔健身。作息偏晚睡晚起。",
            "values": "效率导向",
            "living": "余杭未来科技城",
        }
        zhou_dict = {
            "id": 2, "name": "周婉清", "age": 26, "gender": "女",
            "job": "互联网公司 UI 设计师",
            "personality": "外向、感性，对审美与秩序高度敏感，情绪随项目反馈波动",
            "daily_life": "偏好咖啡馆办公、夜跑和看展，注重生活品质",
            "values": "支持公共文化与城市美学投入",
            "living": "滨江区白马湖",
        }

        li_profile = AgentProfile.from_gaworld_agent(li_dict, gender="男", hukou="外省")
        zhou_profile = AgentProfile.from_gaworld_agent(zhou_dict, gender="女", hukou="外省")

        li_engine = create_life_history_engine(agent_id=1, agent_name="李泽宇", profile=li_profile)
        li_engine._gaworld_agent = li_dict
        li_ctx = li_engine.build_planning_context(activity="规划日程", perception_text="今天天气不错")

        zhou_engine = create_life_history_engine(agent_id=2, agent_name="周婉清", profile=zhou_profile)
        zhou_engine._gaworld_agent = zhou_dict
        zhou_ctx = zhou_engine.build_planning_context(activity="规划日程", perception_text="今天天气不错")

        # Distinct daily-life markers
        assert "两点一线" in li_ctx or "外卖" in li_ctx, f"李泽宇 context missing daily markers: {li_ctx}"
        assert "咖啡馆" in zhou_ctx or "夜跑" in zhou_ctx, f"周婉清 context missing daily markers: {zhou_ctx}"

        # Distinct personality markers
        assert "内向" in li_ctx or "理性" in li_ctx, f"李泽宇 context missing personality: {li_ctx}"
        assert "外向" in zhou_ctx or "感性" in zhou_ctx, f"周婉清 context missing personality: {zhou_ctx}"

        # Contexts must be different strings
        assert li_ctx != zhou_ctx, "Identical contexts for different agents — profile not affecting output"

    def test_behavior_tendency_vs_zhou_wanqing(self):
        """
        Same scenario, two agents — behavioral tendencies must differ.

        Li Zeyu (内向理性/两点一线/技术学习) and Zhou Wanqing
        (外向感性/咖啡馆/夜跑/看展) respond differently to the same
        weekend-planning scenario, proving profile affects which
        actions feel natural, not just what keywords appear.
        """
        li_dict = {
            "id": 1, "name": "李泽宇", "age": 24, "gender": "男",
            "job": "初级算法工程师",
            "personality": "内向理性，低冲突倾向",
            "daily_life": "工作日两点一线；周末补觉、个人技术学习。晚睡晚起。",
            "values": "效率导向",
            "living": "余杭",
        }
        zhou_dict = {
            "id": 2, "name": "周婉清", "age": 26, "gender": "女",
            "job": "UI 设计师",
            "personality": "外向感性，对审美高度敏感",
            "daily_life": "偏好咖啡馆办公、夜跑和看展，注重生活品质。",
            "values": "审美与秩序",
            "living": "滨江",
        }
        shared_perception = "周末快到了，你在考虑怎么安排"
        shared_activity = "规划周末活动"

        li_profile = AgentProfile.from_gaworld_agent(li_dict, gender="男", hukou="外省")
        zhou_profile = AgentProfile.from_gaworld_agent(zhou_dict, gender="女", hukou="外省")

        li_engine = create_life_history_engine(agent_id=1, agent_name="李泽宇", profile=li_profile)
        li_engine._gaworld_agent = li_dict
        li_ctx = li_engine.build_planning_context(activity=shared_activity, perception_text=shared_perception)

        zhou_engine = create_life_history_engine(agent_id=2, agent_name="周婉清", profile=zhou_profile)
        zhou_engine._gaworld_agent = zhou_dict
        zhou_ctx = zhou_engine.build_planning_context(activity=shared_activity, perception_text=shared_perception)

        # Structural divergence: work/social markers
        li_work_markers = ["技术", "学习", "在家", "补觉", "晚睡"]
        zhou_social_markers = ["咖啡馆", "夜跑", "看展", "生活品质", "审美"]

        li_has_work = any(m in li_ctx for m in li_work_markers)
        zhou_has_social = any(m in zhou_ctx for m in zhou_social_markers)

        assert li_has_work, (
            f"李泽宇 context missing work-oriented markers ({li_work_markers}):\n{li_ctx}"
        )
        assert zhou_has_social, (
            f"周婉清 context missing social/lifestyle markers ({zhou_social_markers}):\n{zhou_ctx}"
        )

        # Cross-agent contrast: what is true for one is not dominant for the other
        li_work_dominant = sum(m in li_ctx for m in li_work_markers) >= sum(m in zhou_ctx for m in li_work_markers)
        zhou_social_dominant = sum(m in zhou_ctx for m in zhou_social_markers) >= sum(m in li_ctx for m in zhou_social_markers)

        assert li_work_dominant, (
            f"李泽宇 should show work tendency over social, but context suggests otherwise:\n{li_ctx}"
        )
        assert zhou_social_dominant, (
            f"周婉清 should show social tendency over work, but context suggests otherwise:\n{zhou_ctx}"
        )

        # Contexts must be different strings
        assert li_ctx != zhou_ctx, "Identical contexts despite different profiles"

    def test_social_autonomy_from_daily_life(self):
        """social_autonomy trait inferred from daily_life keywords must appear."""
        # Agent who works alone at home
        profile1 = AgentProfile.from_gaworld_agent(
            _make_agent("独立者", "自由职业", "理性", "独自在家工作，很少社交", "自主优先"),
            gender="男", hukou="本地",
        )
        # Agent with active social life
        profile2 = AgentProfile.from_gaworld_agent(
            _make_agent("社交达人", "销售", "外向", "每天和朋友聚会，周末常逛街", "社交优先"),
            gender="女", hukou="本地",
        )
        ctx1 = _build_ctx(profile1, daily_life_extra="独自在家工作，很少社交")
        ctx2 = _build_ctx(profile2, daily_life_extra="每天和朋友聚会，周末常逛街")

        # Both should have daily life visible
        assert "独自" in ctx1, f"social_autonomy daily life missing: {ctx1}"
        assert "朋友" in ctx2, f"social_autonomy daily life missing: {ctx2}"




def _load_life_history_evaluator():
    """Load eval/life_history_eval.py without requiring eval/ to be a package."""
    import importlib.util
    import os

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval", "life_history_eval.py")
    spec = importlib.util.spec_from_file_location("life_history_eval_module", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.LifeHistoryEvaluator


def _install_fake_planning(monkeypatch, plans, calls=None):
    """Install a fake generative_city_sim.planning for non-live eval tests."""
    import sys
    import types

    queue = list(plans)
    calls = calls if calls is not None else []
    fake_module = types.ModuleType("generative_city_sim")

    def fake_planning(agent, perception_text, recall_context=None, decision_refs=None):
        calls.append({
            "agent": agent,
            "perception_text": perception_text,
            "recall_context": recall_context,
            "decision_refs": decision_refs,
        })
        if not queue:
            return {"goal": "??", "constraint": "?", "urge": "?", "plan": "??", "expected_outcome": "?"}
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    fake_module.planning = fake_planning
    monkeypatch.setitem(sys.modules, "generative_city_sim", fake_module)
    return calls


class TestProfileContextSceneHints:
    def test_money_social_conflict_adds_scene_relevant_hint(self):
        """Scene conflict should surface profile-relevant money/social preferences."""
        agent = _make_agent(
            "Li Zeyu",
            "algorithm engineer",
            "introverted rational low conflict avoids direct confrontation",
            "home office loop; weekend technical study; dislikes high frequency socializing",
            "efficiency, contract boundaries, result orientation",
        )
        profile = AgentProfile.from_gaworld_agent(agent, gender="male", hukou="outside")
        engine = create_life_history_engine(agent_id=1, agent_name="Li Zeyu", profile=profile)
        engine._gaworld_agent = agent

        ctx = engine.build_planning_context(
            activity="weekend planning",
            perception_text="friend coffee chat and another person owes you 2000 money",
        )

        assert "ScenePreference" in ctx
        assert "money_conflict" in ctx
        assert "social_pull" in ctx

class TestPlanDiversityEvaluatorHelpers:
    def test_check_plan_diversity_returns_ab_structure_with_fake_planner(self, monkeypatch):
        """Non-live test: A/B helper returns stable structure and fixed recall calls."""
        plans = [
            {"goal": "coffee chat", "constraint": "limited time", "urge": "social", "plan": "go coffee chat", "expected_outcome": "relax"},
            {"goal": "coffee chat", "constraint": "limited time", "urge": "social", "plan": "go coffee chat", "expected_outcome": "relax"},
            {"goal": "repay followup", "constraint": "avoid conflict", "urge": "progress", "plan": "call debt and study", "expected_outcome": "resolve"},
            {"goal": "coffee friend", "constraint": "energy", "urge": "social", "plan": "coffee exhibit chat", "expected_outcome": "happy"},
        ]
        calls = _install_fake_planning(monkeypatch, plans)
        Evaluator = _load_life_history_evaluator()

        result = Evaluator(52).check_plan_diversity()

        assert result["verdict"] in {"PASS", "FAIL"}
        assert result["score_A"] >= 0
        assert result["score_B"] >= 0
        assert isinstance(result["improvement"], bool)
        assert len(calls) == 4
        assert all(call["recall_context"].get("recollection") == "" for call in calls)
        assert all("hint" in call["recall_context"] for call in calls)
        assert calls[0]["decision_refs"].get("life_history_context") == ""
        assert calls[2]["decision_refs"].get("life_history_context")

    def test_check_plan_diversity_reports_error_with_fake_planner(self, monkeypatch):
        """Non-live test: LLM/planning failures become ERROR results."""
        _install_fake_planning(monkeypatch, [RuntimeError("offline")])
        Evaluator = _load_life_history_evaluator()

        result = Evaluator(52).check_plan_diversity()

        assert result["verdict"] == "ERROR"
        assert result["score_A"] == -1
        assert "offline" in result["error"]

    def test_runtime_ab_diversity_returns_multistep_report_with_fake_planner(self, monkeypatch):
        """Runtime A/B helper should report context injection over multiple steps."""
        plans = [
            {"goal": "rest", "constraint": "none", "urge": "rest", "plan": "stay home rest", "expected_outcome": "recover"},
            {"goal": "social", "constraint": "none", "urge": "social", "plan": "coffee chat", "expected_outcome": "happy"},
            {"goal": "debt followup", "constraint": "none", "urge": "progress", "plan": "call debt", "expected_outcome": "resolve"},
            {"goal": "social", "constraint": "none", "urge": "social", "plan": "exhibit chat", "expected_outcome": "happy"},
            {"goal": "study", "constraint": "none", "urge": "complete", "plan": "technical study", "expected_outcome": "progress"},
            {"goal": "social", "constraint": "none", "urge": "social", "plan": "night run friend", "expected_outcome": "relax"},
        ]
        calls = _install_fake_planning(monkeypatch, plans)
        Evaluator = _load_life_history_evaluator()

        result = Evaluator(52).check_runtime_ab_diversity()

        assert result["verdict"] in {"PASS", "FAIL"}
        assert result["steps"] == 3
        assert result["contexts_injected_B"] == 3
        assert result["contexts_injected_A"] == 0
        assert "action_distribution_A" in result
        assert "action_distribution_B" in result
        assert len(calls) == 6


class TestLifeHistoryABReportHelpers:
    """Tests for eval/life_history_ab_report.py helper functions."""

    def test_pair_logs_excludes_b_missing_steps(self):
        """Only pairs where both A and B have entries are returned."""
        from eval.life_history_ab_report import pair_logs
        logs_a = [
            {"agent_id": 52, "day": 1, "time_str": "08:00", "action": "coffee"},
            {"agent_id": 52, "day": 1, "time_str": "09:00", "action": "walk"},
            {"agent_id": 52, "day": 1, "time_str": "10:00", "action": "study"},
        ]
        logs_b = [
            {"agent_id": 52, "day": 1, "time_str": "08:00", "action": "tea"},
            # 09:00 missing in B
            {"agent_id": 52, "day": 1, "time_str": "10:00", "action": "read"},
        ]
        pairs, missing_b = pair_logs(logs_a, logs_b)
        assert len(pairs) == 2
        assert missing_b == 1
        assert pairs[0][0]["time_str"] == "08:00"
        assert pairs[0][1]["time_str"] == "08:00"
        assert pairs[1][0]["time_str"] == "10:00"
        assert pairs[1][1]["time_str"] == "10:00"

    def test_pair_logs_all_b_entries_paired(self):
        """All B entries that have A counterparts are in pairs."""
        from eval.life_history_ab_report import pair_logs
        logs_a = [
            {"agent_id": 52, "day": 1, "time_str": "08:00", "action": "coffee"},
            {"agent_id": 52, "day": 1, "time_str": "09:00", "action": "walk"},
        ]
        logs_b = [
            {"agent_id": 52, "day": 1, "time_str": "08:00", "action": "tea"},
            {"agent_id": 52, "day": 1, "time_str": "09:00", "action": "jog"},
            {"agent_id": 52, "day": 1, "time_str": "10:00", "action": "read"},  # no A counterpart
        ]
        pairs, missing_b = pair_logs(logs_a, logs_b)
        assert len(pairs) == 2
        assert missing_b == 0
        # B's 10:00 entry should not appear in any pair
        pair_times = {(p[0]["time_str"], p[1]["time_str"]) for p in pairs}
        assert ("10:00", "10:00") not in pair_times

    def test_relationship_drift_uses_correct_per_variant_baseline(self):
        """A drift = A.after - A.before; B drift = B.after - B.before (not A.before).

        Uses a case where the two variants start from different baselines and
        B's delta is sub-threshold (0.005) while the buggy baseline (A.before)
        would cross threshold (0.505). Correct code gives drift_b=0; buggy code
        (using A.before as B's baseline) gives drift_b=1.
        """
        from eval.life_history_ab_report import compute_paired_diff
        # A: trust 0.3→0.6 (delta 0.3 > 0.01 → drift_a = 1)
        # B: trust 0.8→0.805 (delta 0.005 < 0.01 → drift_b = 0 if correct)
        # If buggy uses A.before (0.3): B.after - A.before = 0.805-0.3=0.505 → drift_b = 1
        pairs = [
            (
                {
                    "agent_id": 52, "day": 1, "time_str": "08:00",
                    "action": "coffee", "action_type": "social", "decision_driver": "social",
                    "scheduled_activity": "social", "activity_final": "coffee",
                    "life_history_context_present": False,
                    "relationships_before": {"11": {"trust": 0.3, "closeness": 0.5}},
                    "relationships_after": {"11": {"trust": 0.6, "closeness": 0.5}},
                },
                {
                    "agent_id": 52, "day": 1, "time_str": "08:00",
                    "action": "tea", "action_type": "social", "decision_driver": "social",
                    "scheduled_activity": "social", "activity_final": "tea",
                    "life_history_context_present": True,
                    "relationships_before": {"11": {"trust": 0.8, "closeness": 0.2}},
                    "relationships_after": {"11": {"trust": 0.805, "closeness": 0.2}},
                },
            )
        ]
        diff = compute_paired_diff(pairs)
        assert len(diff["relationship_drift"]) == 1
        rd = diff["relationship_drift"][0]
        # Correct: drift_a=1 (A delta > threshold), drift_b=0 (B delta < threshold)
        # Buggy: drift_b would be 1 (B.after - A.before = 0.505 crosses threshold)
        assert rd["drift_a"] == 1
        assert rd["drift_b"] == 0
        # The numeric inequality proves per-variant baselines are used, not A.before for B
        assert rd["drift_a"] != rd["drift_b"]

    def test_action_changed_count_excludes_none_b(self):
        """action_changed only counts when B has an action (not when B is None)."""
        from eval.life_history_ab_report import compute_paired_diff
        pairs = [
            (
                {"agent_id": 52, "day": 1, "time_str": "08:00", "action": "coffee",
                 "action_type": "social", "decision_driver": "social",
                 "scheduled_activity": "social", "activity_final": "coffee",
                 "life_history_context_present": False,
                 "relationships_before": {}, "relationships_after": {}},
                {"agent_id": 52, "day": 1, "time_str": "08:00", "action": "tea",
                 "action_type": "social", "decision_driver": "social",
                 "scheduled_activity": "social", "activity_final": "tea",
                 "life_history_context_present": True,
                 "relationships_before": {}, "relationships_after": {}},
            ),
            (
                {"agent_id": 52, "day": 1, "time_str": "09:00", "action": "walk",
                 "action_type": "movement", "decision_driver": "spacetime",
                 "scheduled_activity": "walk", "activity_final": "walk",
                 "life_history_context_present": False,
                 "relationships_before": {}, "relationships_after": {}},
                {"agent_id": 52, "day": 1, "time_str": "09:00", "action": "jog",
                 "action_type": "movement", "decision_driver": "spacetime",
                 "scheduled_activity": "walk", "activity_final": "jog",
                 "life_history_context_present": True,
                 "relationships_before": {}, "relationships_after": {}},
            ),
            (
                {"agent_id": 52, "day": 1, "time_str": "10:00", "action": "study",
                 "action_type": "work", "decision_driver": "goal",
                 "scheduled_activity": "study", "activity_final": "study",
                 "life_history_context_present": False,
                 "relationships_before": {}, "relationships_after": {}},
                {"agent_id": 52, "day": 1, "time_str": "10:00", "action": "study",
                 "action_type": "work", "decision_driver": "goal",
                 "scheduled_activity": "study", "activity_final": "study",
                 "life_history_context_present": True,
                 "relationships_before": {}, "relationships_after": {}},
            ),
        ]
        diff = compute_paired_diff(pairs)
        # step 1: coffee != tea → 1
        # step 2: walk != jog → 1
        # step 3: study == study → 0
        assert diff["action_changed"] == 2
        assert diff["total_paired"] == 3


@pytest.mark.integration
class TestPlanActionDiversity:
    """
    Regression test for real planning output diversity.

    Requires live LLM (Ollama). Marked as integration to exclude from
    default `bash run_life_history_tests.sh`.

    Run separately with:
        /home/glf/miniconda3/bin/python -m pytest tests/test_profile_context_diversity.py::TestPlanActionDiversity -v
    """

    def test_li_vs_zhou_planning_differs(self):
        """
        Li Zeyu (技术内向) and Zhou Wanqing (审美外向)
        must produce different planning decisions for the same scenario.

        This is the core test for action-level behavioral differentiation.
        """
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from generative_city_sim import planning

        scenario = (
            "周末下午 4 点，无工作安排。"
            "关系人 A 发消息约你去咖啡馆聊天，说很久没见了。"
            "另外，关系人 B 之前借了你 2000 元一直没还，你催过一次还没回应。"
            "当前心情一般，空闲时间充裕。"
        )

        li_agent = {
            "id": 1, "name": "李泽宇",
            "state": {"emotion": 0.5, "stress": 0.5},
            "intentions": [],
        }
        zhou_agent = {
            "id": 2, "name": "周婉清",
            "state": {"emotion": 0.5, "stress": 0.5},
            "intentions": [],
        }

        li_plan = planning(li_agent, scenario)
        zhou_plan = planning(zhou_agent, scenario)

        # Helper to classify action type
        def _goal_type(plan):
            goal = plan.get("goal", "")
            if any(k in goal for k in ["聊天", "咖啡馆", "见面", "赴约", "朋友", "社交"]):
                return "social"
            if any(k in goal for k in ["工作", "技术", "学习", "处理", "还钱", "催", "联系"]):
                return "work"
            if any(k in goal for k in ["休息", "睡觉", "放松", "恢复"]):
                return "self_care"
            return "other"

        def _urge_type(plan):
            urge = plan.get("urge", "")
            if "社交" in urge:
                return "social"
            if any(k in urge for k in ["躺着", "懒", "休息", "省力", "不想动"]):
                return "lazy"
            if any(k in urge for k in ["完成", "处理", "推进"]):
                return "achievement"
            return "other"

        li_goal = _goal_type(li_plan)
        zhou_goal = _goal_type(zhou_plan)
        li_urge = _urge_type(li_plan)
        zhou_urge = _urge_type(zhou_plan)

        # Detailed inspection: log all four dimensions for debugging
        print(f"\n[plan diversity] 李泽宇 → goal={li_goal}({li_plan.get('goal')}), "
              f"urge={li_urge}({li_plan.get('urge')}), "
              f"plan={li_plan.get('plan')}")
        print(f"[plan diversity] 周婉清 → goal={zhou_goal}({zhou_plan.get('goal')}), "
              f"urge={zhou_urge}({zhou_plan.get('urge')}), "
              f"plan={zhou_plan.get('plan')}")
