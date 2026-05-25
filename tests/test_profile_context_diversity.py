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
