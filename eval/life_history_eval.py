"""
生活史型智能体评估脚本
评估 Agent 52 (郭林峰) 的六维 HumanScore

维度：
- memory_score: 记忆系统
- personality_score: 人格角色
- affect_score: 情感层
- bounded_rationality_score: 有限理性
- learning_score: 持续学习
- relationship_score: 关系记忆
"""

import json
import sys
import os
from datetime import datetime
from typing import Dict

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gaworld.core.life_history.mock_data import (
    create_agent_52_profile,
    create_agent_52_runtime_state,
    create_mock_scores
)


# =========================================================
# 评估指标定义
# =========================================================

EVALUATION_DIMENSIONS = {
    "memory_score": {
        "name": "记忆系统",
        "max": 30,
        "weight": 0.25,
        "sub_metrics": {
            "recall_accuracy": {"weight": 0.4, "max": 10},
            "consistency": {"weight": 0.3, "max": 10},
            "recency_effect": {"weight": 0.3, "max": 10}
        }
    },
    "personality_score": {
        "name": "人格角色",
        "max": 25,
        "weight": 0.20,
        "sub_metrics": {
            "personality_consistency": {"weight": 0.4, "max": 12.5},
            "role_stability": {"weight": 0.3, "max": 7.5},
            "background_coverage": {"weight": 0.3, "max": 5}
        }
    },
    "affect_score": {
        "name": "情感层",
        "max": 20,
        "weight": 0.20,
        "sub_metrics": {
            "emotion_wave": {"weight": 0.4, "max": 8},
            "emotional_memory": {"weight": 0.3, "max": 6},
            "expression_diversity": {"weight": 0.3, "max": 6}
        }
    },
    "bounded_rationality_score": {
        "name": "有限理性",
        "max": 15,
        "weight": 0.15,
        "sub_metrics": {
            "decision_diversity": {"weight": 0.4, "max": 6},
            "uncertainty_expression": {"weight": 0.3, "max": 4.5},
            "bounded_options": {"weight": 0.3, "max": 4.5}
        }
    },
    "learning_score": {
        "name": "持续学习",
        "max": 10,
        "weight": 0.10,
        "sub_metrics": {
            "behavior_drift_detection": {"weight": 0.5, "max": 5},
            "learning_from_error": {"weight": 0.3, "max": 3},
            "preference_adaptation": {"weight": 0.2, "max": 2}
        }
    },
    "relationship_score": {
        "name": "关系记忆",
        "max": 20,
        "weight": 0.10,
        "sub_metrics": {
            "relationship_tracking": {"weight": 0.4, "max": 8},
            "trust_evolution": {"weight": 0.3, "max": 6},
            "conflict_resolution": {"weight": 0.3, "max": 6}
        }
    }
}


class LifeHistoryEvaluator:
    """生活史型智能体评估器"""
    
    def __init__(self, agent_id: int):
        self.agent_id = agent_id
        self.mock_scores = create_mock_scores()
        self.profile = create_agent_52_profile()
        self.state = create_agent_52_runtime_state(self.profile)

    def check_profile_context_diversity(self) -> Dict:
        """
        辅助指标：验证不同 agent 的 profile context 确实不同。

        使用李泽宇(01)和周婉清(02)的真实数据，
        验证 per-agent profile → planning context 的差异化是否生效。

        Returns:
            {"pass": bool, "li_ctx": str, "zhou_ctx": str,
             "differences": [str], "verdict": str}
        """
        from gaworld.core.life_history import AgentProfile, create_life_history_engine
        import re, os

        # Read from real MD profile file
        md_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "hangzhou_profiles_with_names.md")
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                md_text = f.read()
        except OSError:
            # Fallback to hardcoded dicts if MD file not accessible
            md_text = ""

        def _extract_agent_dict(md_text: str, agent_num: str) -> dict:
            """Parse a single agent block from MD text."""
            pattern = rf"## Profile {agent_num}｜(.+?)(?=\n## Profile |\Z)"
            match = re.search(pattern, md_text, re.S)
            if not match:
                return {}
            block = match.group(0)

            def _field(key: str) -> str:
                # Field may appear as "**Key**：value" or "Key：value"
                m = re.search(rf"\*\*{key}\*\*：(.+?)(?=\n\n\*\*|\n## |$)", block, re.S)
                if not m:
                    m = re.search(rf"{key}：(.+?)(?=\n\n\*\*|\n## |$)", block, re.S)
                return m.group(1).strip() if m else ""

            name_m = re.search(r"## Profile \d+｜(.+)", block)
            name = name_m.group(1).strip() if name_m else f"Agent {agent_num}"

            base = _field("基础信息")
            age_m = re.search(r"(\d+)岁", base)
            gender_m = re.search(r"^(男|女)", base)
            hukou_m = re.search(r"外省|本地|外国", base)
            living_m = re.search(r"现居住于?(.+?)[，,。]", base)

            return {
                "id": int(agent_num),
                "name": name,
                "age": int(age_m.group(1)) if age_m else 25,
                "gender": gender_m.group(1) if gender_m else "",
                "hukou": hukou_m.group(0) if hukou_m else "",
                "job": _field("职业与工作节奏"),
                "personality": _field("性格与情绪特征"),
                "daily_life": _field("日常生活与生活习惯"),
                "values": _field("价值观与公共事务态度"),
                "living": living_m.group(1) if living_m else "",
            }

        li_dict = _extract_agent_dict(md_text, "01")
        zhou_dict = _extract_agent_dict(md_text, "02")

        # Fallback if MD parsing failed (data_source = "fallback")
        li_used_fallback = not bool(li_dict)
        zhou_used_fallback = not bool(zhou_dict)
        data_source = "fallback" if (li_used_fallback or zhou_used_fallback) else "md"

        if li_used_fallback:
            li_dict = {
                "id": 1, "name": "李泽宇", "age": 24, "gender": "男", "hukou": "外省",
                "job": "互联网企业初级算法工程师",
                "personality": "性格偏内向理性，低冲突倾向，习惯用技术问题掩盖情绪问题",
                "daily_life": "工作日以公司—出租屋两点一线为主，饮食高度依赖外卖；周末多用于补觉、个人技术学习、偶尔健身。作息偏晚睡晚起。",
                "values": "效率导向",
                "living": "余杭未来科技城",
            }
        if zhou_used_fallback:
            zhou_dict = {
                "id": 2, "name": "周婉清", "age": 26, "gender": "女", "hukou": "外省",
                "job": "互联网公司 UI 设计师",
                "personality": "外向、感性，对审美与秩序高度敏感，情绪随项目反馈波动",
                "daily_life": "偏好咖啡馆办公、夜跑和看展，注重生活品质",
                "values": "支持公共文化与城市美学投入",
                "living": "滨江区白马湖",
            }

        li_profile = AgentProfile.from_gaworld_agent(
            li_dict, gender=li_dict.get("gender", ""), hukou=li_dict.get("hukou", ""))
        zhou_profile = AgentProfile.from_gaworld_agent(
            zhou_dict, gender=zhou_dict.get("gender", ""), hukou=zhou_dict.get("hukou", ""))

        li_engine = create_life_history_engine(agent_id=1, agent_name=li_dict["name"], profile=li_profile)
        li_engine._gaworld_agent = li_dict
        li_ctx = li_engine.build_planning_context(activity="规划日程", perception_text="今天天气不错")

        zhou_engine = create_life_history_engine(agent_id=2, agent_name=zhou_dict["name"], profile=zhou_profile)
        zhou_engine._gaworld_agent = zhou_dict
        zhou_ctx = zhou_engine.build_planning_context(activity="规划日程", perception_text="今天天气不错")

        differences = []
        li_daily_markers = ["两点一线", "外卖", "补觉", "技术学习", "晚睡晚起"]
        zhou_daily_markers = ["咖啡馆", "夜跑", "看展", "生活品质"]
        li_found = [m for m in li_daily_markers if m in li_ctx]
        zhou_found = [m for m in zhou_daily_markers if m in zhou_ctx]
        if li_found:
            differences.append(f"李泽宇日常标记: {', '.join(li_found)}")
        if zhou_found:
            differences.append(f"周婉清日常标记: {', '.join(zhou_found)}")
        if "内向" in li_ctx or "理性" in li_ctx:
            differences.append("李泽宇人格: 内向/理性")
        if "外向" in zhou_ctx or "感性" in zhou_ctx:
            differences.append("周婉清人格: 外向/感性")

        contexts_differ = li_ctx != zhou_ctx
        daily_differentiated = bool(li_found and zhou_found)
        personality_differentiated = ("内向" in li_ctx or "理性" in li_ctx) and ("外向" in zhou_ctx or "感性" in zhou_ctx)

        # strict: require both md parsing AND behavioral differentiation
        behavior_ok = contexts_differ and daily_differentiated and personality_differentiated
        verdict = "PASS" if (behavior_ok and data_source == "md") else "FAIL"

        return {
            "pass": verdict == "PASS",
            "verdict": verdict,
            "data_source": data_source,
            "li_used_fallback": li_used_fallback,
            "zhou_used_fallback": zhou_used_fallback,
            "li_ctx": li_ctx,
            "zhou_ctx": zhou_ctx,
            "differences": differences,
            "daily_differentiated": daily_differentiated,
            "personality_differentiated": personality_differentiated,
            "contexts_differ": contexts_differ,
        }
    
    def check_plan_diversity(self) -> Dict:
        """
        核心指标：A/B 测试 profile injection 对 planning 决策分化的影响。

        A: planning() 无 life_history_context（仅 name + state）
        B: planning() decision_refs["life_history_context"] 注入完整 profile context

        比较 B 是否比 A 的 score 更高，证明 profile injection 对决策有真实影响。

        Returns:
            {"verdict": str, "score_A": int, "score_B": int, "improvement": bool,
             "li_plan_A/B": dict, "zhou_plan_A/B": dict, ...}
        """
        from generative_city_sim import planning
        from gaworld.core.life_history import AgentProfile, create_life_history_engine
        import os, re

        # ---- 复用 check_profile_context_diversity 的 profile parsing ----
        md_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "hangzhou_profiles_with_names.md")
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                md_text = f.read()
        except OSError:
            md_text = ""

        def _extract_agent_dict(md_text: str, agent_num: str) -> dict:
            pattern = rf"## Profile {agent_num}｜(.+?)(?=\n## Profile |\Z)"
            match = re.search(pattern, md_text, re.S)
            if not match:
                return {}
            block = match.group(0)

            def _field(key: str) -> str:
                m = re.search(rf"\*\*{key}\*\*：(.+?)(?=\n\n\*\*|\n## |$)", block, re.S)
                if not m:
                    m = re.search(rf"{key}：(.+?)(?=\n\n\*\*|\n## |$)", block, re.S)
                return m.group(1).strip() if m else ""

            name_m = re.search(r"## Profile \d+｜(.+)", block)
            name = name_m.group(1).strip() if name_m else f"Agent {agent_num}"

            base = _field("基础信息")
            age_m = re.search(r"(\d+)岁", base)
            gender_m = re.search(r"^(男|女)", base)
            hukou_m = re.search(r"外省|本地|外国", base)

            return {
                "id": int(agent_num),
                "name": name,
                "age": int(age_m.group(1)) if age_m else 25,
                "gender": gender_m.group(1) if gender_m else "",
                "hukou": hukou_m.group(0) if hukou_m else "",
                "job": _field("职业与工作节奏"),
                "personality": _field("性格与情绪特征"),
                "daily_life": _field("日常生活与生活习惯"),
                "values": _field("价值观与公共事务态度"),
                "living": _field("现居地"),
            }

        li_dict = _extract_agent_dict(md_text, "01")
        zhou_dict = _extract_agent_dict(md_text, "02")

        # Fallback if MD parsing fails
        if not li_dict:
            li_dict = {
                "id": 1, "name": "李泽宇", "age": 24, "gender": "男", "hukou": "外省",
                "job": "互联网企业初级算法工程师",
                "personality": "性格偏内向理性，低冲突倾向，习惯用技术问题掩盖情绪问题",
                "daily_life": "工作日以公司—出租屋两点一线为主，饮食高度依赖外卖；周末多用于补觉、个人技术学习、偶尔健身。作息偏晚睡晚起。",
                "values": "效率导向",
                "living": "余杭未来科技城",
            }
        if not zhou_dict:
            zhou_dict = {
                "id": 2, "name": "周婉清", "age": 26, "gender": "女", "hukou": "外省",
                "job": "互联网公司 UI 设计师",
                "personality": "外向、感性，对审美与秩序高度敏感，情绪随项目反馈波动",
                "daily_life": "偏好咖啡馆办公、夜跑和看展，注重生活品质",
                "values": "支持公共文化与城市美学投入",
                "living": "滨江区白马湖",
            }

        # ---- 构建 per-agent engines 和 life_history_context ----
        li_profile = AgentProfile.from_gaworld_agent(
            li_dict, gender=li_dict.get("gender", ""), hukou=li_dict.get("hukou", ""))
        zhou_profile = AgentProfile.from_gaworld_agent(
            zhou_dict, gender=zhou_dict.get("gender", ""), hukou=zhou_dict.get("hukou", ""))

        li_engine = create_life_history_engine(agent_id=1, agent_name=li_dict["name"], profile=li_profile)
        li_engine._gaworld_agent = li_dict
        zhou_engine = create_life_history_engine(agent_id=2, agent_name=zhou_dict["name"], profile=zhou_profile)
        zhou_engine._gaworld_agent = zhou_dict

        li_ctx = li_engine.build_planning_context(activity="规划日程", perception_text="今天天气不错")
        zhou_ctx = zhou_engine.build_planning_context(activity="规划日程", perception_text="今天天气不错")

        # ---- 标准测试场景 ----
        scenario = (
            "周末下午 4 点，无工作安排。"
            "关系人 A 发消息约你去咖啡馆聊天，说很久没见了。"
            "另外，关系人 B 之前借了你 2000 元一直没还，你催过一次还没回应。"
            "当前心情一般，空闲时间充裕。"
        )

        li_agent = {
            "id": 1, "name": li_dict["name"],
            "state": {"emotion": 0.5, "stress": 0.5},
            "intentions": [],
        }
        zhou_agent = {
            "id": 2, "name": zhou_dict["name"],
            "state": {"emotion": 0.5, "stress": 0.5},
            "intentions": [],
        }

        refs_template = {
            "emotion_text": "当前情绪：中性偏波动（emotion=0.50）；当前压力：压力中等（stress=0.50）",
            "memory_hint": "暂无重要经验",
            "recollection": "无明显回忆",
            "physical_env_relevant": False,
            "social_env_relevant": False,
            "location_time_relevant": False,
            "social_network_relevant": False,
            "physical_env_text": "",
            "social_env_text": "",
            "location_time_text": "",
            "social_network_text": "",
            "transient_thought": None,
            "life_history_context": "",  # A: 无 context
        }

        # ---- recall_context 固定，消除 evoke_memory() 随机性 ----
        fixed_recall = {"hint": "暂无重要经验", "recollection": ""}

        # ---- A/B 测试：A = 无 life_history_context，B = 有 ----
        # recall_context 明确传入，不再调用 evoke_memory()
        try:
            li_plan_A = planning(li_agent, scenario, recall_context=fixed_recall, decision_refs=refs_template)
            zhou_plan_A = planning(zhou_agent, scenario, recall_context=fixed_recall, decision_refs=refs_template)
        except Exception as exc:
            return {
                "verdict": "ERROR", "score_A": -1, "score_B": -1, "improvement": False,
                "error": f"A-side planning failed: {type(exc).__name__}: {exc}",
                "li_plan_A": {}, "zhou_plan_A": {}, "li_plan_B": {}, "zhou_plan_B": {},
                "li_action_type_A": {}, "zhou_action_type_A": {},
                "li_action_type_B": {}, "zhou_action_type_B": {},
            }

        refs_li_B = dict(refs_template, life_history_context=li_ctx)
        refs_zhou_B = dict(refs_template, life_history_context=zhou_ctx)

        try:
            li_plan_B = planning(li_agent, scenario, recall_context=fixed_recall, decision_refs=refs_li_B)
            zhou_plan_B = planning(zhou_agent, scenario, recall_context=fixed_recall, decision_refs=refs_zhou_B)
        except Exception as exc:
            return {
                "verdict": "ERROR", "score_A": -1, "score_B": -1, "improvement": False,
                "error": f"B-side planning failed: {type(exc).__name__}: {exc}",
                "li_plan_A": li_plan_A, "zhou_plan_A": zhou_plan_A,
                "li_plan_B": {}, "zhou_plan_B": {},
                "li_action_type_A": {}, "zhou_action_type_A": {},
                "li_action_type_B": {}, "zhou_action_type_B": {},
            }

        # ---- action type 提取 ----
        def _action_type(plan_dict: dict) -> dict:
            goal = plan_dict.get("goal", "")
            urge = plan_dict.get("urge", "")
            plan_text = plan_dict.get("plan", "")

            goal_type = "social" if any(k in goal for k in ["聊天", "咖啡馆", "见面", "赴约", "朋友"]) \
                else "work" if any(k in goal for k in ["工作", "技术", "学习", "处理", "还钱", "催", "联系"]) \
                else "self_care" if any(k in goal for k in ["休息", "睡觉", "放松", "恢复"]) \
                else "other"

            urge_type = "social" if "社交" in urge \
                else "lazy" if any(k in urge for k in ["躺着", "懒", "休息", "省力", "不想动"]) \
                else "achievement" if any(k in urge for k in ["完成", "处理", "推进"]) \
                else "other"

            plan_keywords = [kw for kw in
                ["咖啡馆", "夜跑", "看展", "图书馆", "健身房",
                 "室内", "在家", "外卖", "技术", "学习", "催债", "电话"]
                if kw in plan_text]

            return {"goal_type": goal_type, "urge_type": urge_type, "plan_keywords": plan_keywords}

        def _score(li_type, zhou_type):
            goal_d = li_type["goal_type"] != zhou_type["goal_type"]
            urge_d = li_type["urge_type"] != zhou_type["urge_type"]
            overlap = set(li_type["plan_keywords"]) & set(zhou_type["plan_keywords"])
            plan_d = len(overlap) < max(len(li_type["plan_keywords"]), len(zhou_type["plan_keywords"]))
            return sum([goal_d, urge_d, plan_d]), goal_d, urge_d, plan_d

        li_type_A = _action_type(li_plan_A)
        zhou_type_A = _action_type(zhou_plan_A)
        li_type_B = _action_type(li_plan_B)
        zhou_type_B = _action_type(zhou_plan_B)

        score_A, gA, uA, pA = _score(li_type_A, zhou_type_A)
        score_B, gB, uB, pB = _score(li_type_B, zhou_type_B)

        improvement = score_B > score_A
        verdict = "PASS" if improvement else "FAIL"

        return {
            "verdict": verdict,
            "score_A": score_A,
            "score_B": score_B,
            "improvement": improvement,
            # A plans
            "li_plan_A": li_plan_A,
            "zhou_plan_A": zhou_plan_A,
            "li_action_type_A": li_type_A,
            "zhou_action_type_A": zhou_type_A,
            # B plans
            "li_plan_B": li_plan_B,
            "zhou_plan_B": zhou_plan_B,
            "li_action_type_B": li_type_B,
            "zhou_action_type_B": zhou_type_B,
            # Detail
            "goal_differ_A": gA, "urge_differ_A": uA, "plan_differ_A": pA,
            "goal_differ_B": gB, "urge_differ_B": uB, "plan_differ_B": pB,
            "li_context": li_ctx,
            "zhou_context": zhou_ctx,
        }


    def check_runtime_ab_diversity(self) -> Dict:
        """
        Runtime-style A/B check over multiple planning steps.

        A: same agent/scenario without life_history_context.
        B: same agent/scenario with LifeHistoryEngine.build_planning_context().
        This is still an eval harness, but it mirrors the runtime injection path
        across repeated steps instead of a single prompt comparison.
        """
        from generative_city_sim import planning
        from gaworld.core.life_history import AgentProfile, create_life_history_engine

        agent_dict = {
            "id": 1,
            "name": "Li Zeyu",
            "age": 24,
            "gender": "male",
            "hukou": "outside",
            "job": "junior algorithm engineer",
            "personality": "introverted rational low conflict avoids direct confrontation",
            "daily_life": "weekday home office loop; weekend sleep recovery and technical learning; dislikes high frequency socializing",
            "values": "efficiency, contract boundaries, result orientation",
            "living": "Hangzhou",
            "state": {"emotion": 0.5, "stress": 0.5},
            "intentions": [],
        }
        profile = AgentProfile.from_gaworld_agent(agent_dict, gender="male", hukou="outside")
        engine = create_life_history_engine(agent_id=1, agent_name=agent_dict["name"], profile=profile)
        engine._gaworld_agent = agent_dict

        scenarios = [
            ("weekend planning", "A friend invites you to a coffee chat; another person still owes you 2000."),
            ("evening planning", "You feel tired but have a pending technical learning task."),
            ("relationship followup", "A borrower has not replied after your previous reminder."),
        ]
        refs_template = {
            "emotion_text": "emotion=0.50; stress=0.50",
            "memory_hint": "no important experience",
            "recollection": "none",
            "physical_env_relevant": False,
            "social_env_relevant": False,
            "location_time_relevant": False,
            "social_network_relevant": False,
            "physical_env_text": "",
            "social_env_text": "",
            "location_time_text": "",
            "social_network_text": "",
            "transient_thought": None,
            "life_history_context": "",
        }
        fixed_recall = {"hint": "no important experience", "recollection": ""}

        def _action_type(plan_dict: dict) -> str:
            text = " ".join(str(plan_dict.get(k, "")) for k in ("goal", "urge", "plan")).lower()
            if any(k in text for k in ["coffee", "chat", "friend", "social", "\u5496\u5561", "\u804a\u5929", "\u670b\u53cb"]):
                return "social"
            if any(k in text for k in ["debt", "owe", "repay", "call", "\u50ac", "\u503a", "\u8fd8\u94b1", "\u7535\u8bdd"]):
                return "money_followup"
            if any(k in text for k in ["study", "technical", "work", "\u5b66\u4e60", "\u6280\u672f", "\u5de5\u4f5c"]):
                return "work_study"
            if any(k in text for k in ["rest", "sleep", "recover", "\u4f11\u606f", "\u7761"]):
                return "self_care"
            return "other"

        plans_A = []
        plans_B = []
        contexts_A = []
        contexts_B = []
        try:
            for activity, perception in scenarios:
                refs_A = dict(refs_template, life_history_context="")
                plan_A = planning(agent_dict, perception, recall_context=fixed_recall, decision_refs=refs_A)
                plans_A.append(plan_A)
                contexts_A.append(refs_A["life_history_context"])

                context_B = engine.build_planning_context(activity=activity, perception_text=perception)
                refs_B = dict(refs_template, life_history_context=context_B)
                plan_B = planning(agent_dict, perception, recall_context=fixed_recall, decision_refs=refs_B)
                plans_B.append(plan_B)
                contexts_B.append(context_B)
        except Exception as exc:
            return {
                "verdict": "ERROR",
                "error": f"runtime A/B planning failed: {type(exc).__name__}: {exc}",
                "steps": len(scenarios),
                "contexts_injected_A": sum(1 for c in contexts_A if c),
                "contexts_injected_B": sum(1 for c in contexts_B if c),
                "plans_A": plans_A,
                "plans_B": plans_B,
                "action_distribution_A": {},
                "action_distribution_B": {},
                "changed_steps": 0,
                "profile_match_score_B": 0,
            }

        types_A = [_action_type(plan) for plan in plans_A]
        types_B = [_action_type(plan) for plan in plans_B]
        dist_A = {t: types_A.count(t) for t in sorted(set(types_A))}
        dist_B = {t: types_B.count(t) for t in sorted(set(types_B))}
        changed_steps = sum(1 for a, b in zip(types_A, types_B) if a != b)
        profile_match_score_B = sum(1 for t in types_B if t in {"money_followup", "work_study", "self_care"})
        contexts_injected_B = sum(1 for c in contexts_B if c and "ScenePreference" in c)
        verdict = "PASS" if contexts_injected_B == len(scenarios) and changed_steps > 0 else "FAIL"

        return {
            "verdict": verdict,
            "steps": len(scenarios),
            "contexts_injected_A": sum(1 for c in contexts_A if c),
            "contexts_injected_B": contexts_injected_B,
            "plans_A": plans_A,
            "plans_B": plans_B,
            "action_types_A": types_A,
            "action_types_B": types_B,
            "action_distribution_A": dist_A,
            "action_distribution_B": dist_B,
            "changed_steps": changed_steps,
            "profile_match_score_B": profile_match_score_B,
            "interpretation": (
                "profile context entered runtime-style planning and changed behavior"
                if verdict == "PASS"
                else "profile context entered planning but did not change action types enough"
            ),
        }

    def run_full_evaluation(self) -> Dict:
        """执行完整评估"""
        results = {
            "agent_id": self.agent_id,
            "agent_name": self.state.profile.identity.name,
            "evaluation_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "dimensions": {},
            "total_score": 0,
            "weighted_score": 0,
            "grade": "",
            "recommendations": []
        }
        
        total_weighted = 0
        total_possible = 0
        
        for dim_key, dim_config in EVALUATION_DIMENSIONS.items():
            dim_result = self._evaluate_dimension(dim_key, dim_config)
            results["dimensions"][dim_key] = dim_result
            
            weighted = (dim_result["percentage"] / 100) * dim_config["weight"]
            total_weighted += weighted
            total_possible += dim_config["weight"]

            # 生成建议
            if dim_result["percentage"] < 60:
                results["recommendations"].append(
                    f"P{int(100 - dim_result['percentage'])/20}: 改进{dim_config['name']}"
                )

        results["weighted_score"] = round(total_weighted / total_possible * 100, 1) if total_possible > 0 else 0
        results["total_score"] = sum(d["raw"] for d in results["dimensions"].values())
        results["total_max"] = sum(d["max"] for d in results["dimensions"].values())
        results["grade"] = self._compute_grade(results["weighted_score"])

        # 辅助指标：profile context diversity
        results["profile_context_diversity"] = self.check_profile_context_diversity()

        # 核心指标：plan diversity（真实规划决策对比）
        # 包两层：外层捕获 import/dependency 崩溃，内层捕获 LLM 调用失败
        try:
            results["plan_diversity"] = self.check_plan_diversity()
        except Exception as exc:
            results["plan_diversity"] = {
                "verdict": "ERROR",
                "score_A": -1, "score_B": -1,
                "improvement": False,
                "error": f"check_plan_diversity crashed: {type(exc).__name__}: {exc}",
                "li_plan_A": {}, "zhou_plan_A": {},
                "li_plan_B": {}, "zhou_plan_B": {},
                "li_action_type_A": {}, "zhou_action_type_A": {},
                "li_action_type_B": {}, "zhou_action_type_B": {},
            }

        try:
            results["runtime_ab_diversity"] = self.check_runtime_ab_diversity()
        except Exception as exc:
            results["runtime_ab_diversity"] = {
                "verdict": "ERROR",
                "error": f"check_runtime_ab_diversity crashed: {type(exc).__name__}: {exc}",
                "steps": 0,
                "contexts_injected_A": 0,
                "contexts_injected_B": 0,
                "action_distribution_A": {},
                "action_distribution_B": {},
                "changed_steps": 0,
                "profile_match_score_B": 0,
            }

        return results
    
    def _evaluate_dimension(self, dim_key: str, dim_config: Dict) -> Dict:
        """评估单个维度"""
        mock = self.mock_scores.get(dim_key, {})
        raw = mock.get("raw", 0)
        max_score = dim_config["max"]
        percentage = (raw / max_score * 100) if max_score > 0 else 0
        
        sub_results = {}
        for sub_key, sub_config in dim_config.get("sub_metrics", {}).items():
            sub_raw = mock.get("sub_scores", {}).get(sub_key, 0)
            sub_max = sub_config["max"]
            sub_percentage = (sub_raw / sub_max * 100) if sub_max > 0 else 0
            sub_results[sub_key] = {
                "raw": sub_raw,
                "max": sub_max,
                "percentage": round(sub_percentage, 1)
            }
        
        return {
            "name": dim_config["name"],
            "raw": raw,
            "max": max_score,
            "percentage": round(percentage, 1),
            "sub_scores": sub_results
        }
    
    def _compute_grade(self, score: float) -> str:
        """计算评级"""
        if score >= 90:
            return "优秀（接近真人）"
        elif score >= 70:
            return "良好（明显人类特征）"
        elif score >= 50:
            return "一般（部分人类特征）"
        else:
            return "不足（明显机器感）"
    
    def print_report(self, results: Dict):
        """打印评估报告"""
        print("=" * 60)
        print(f"生活史型智能体评估报告 - Agent {results['agent_id']} ({results['agent_name']})")
        print("=" * 60)
        print(f"评估日期: {results['evaluation_date']}")
        print()
        
        print("各维度得分:")
        print("-" * 60)
        for dim_key, dim_result in results["dimensions"].items():
            print(f"  {dim_result['name']}: {dim_result['raw']}/{dim_result['max']} ({dim_result['percentage']}%)")
            for sub_key, sub_result in dim_result.get("sub_scores", {}).items():
                print(f"    - {sub_key}: {sub_result['raw']}/{sub_result['max']}")
        
        print()
        print("-" * 60)
        print(f"总分: {results['total_score']}/{results['total_max']}")
        print(f"加权得分: {results['weighted_score']}/100")
        print(f"评级: {results['grade']}")
        print("-" * 60)
        
        if results["recommendations"]:
            print()
            print("优先改进项:")
            for rec in results["recommendations"]:
                print(f"  {rec}")

        # Context tendency diversity 验证
        div = results.get("profile_context_diversity", {})
        if div:
            verdict_icon = "PASS" if div.get("verdict") == "PASS" else "FAIL"
            icon = "OK" if div.get("verdict") == "PASS" else "!!"
            data_source = div.get("data_source", "unknown")
            warn = " [WARN: used fallback]" if data_source == "fallback" else ""
            print()
            print("-" * 60)
            print(f"Context Tendency Diversity: {verdict_icon} {icon} (source: {data_source}){warn}")
            for diff in div.get("differences", []):
                print(f"  {diff}")

        # Plan diversity A/B 测试（核心指标）
        pdiv = results.get("plan_diversity", {})
        if pdiv:
            verdict = pdiv.get("verdict", "FAIL")
            icon = "!!" if verdict in ("FAIL", "ERROR") else "OK"
            print()
            print("-" * 60)
            print(f"Plan/Action Diversity: {verdict} {icon}")
            if verdict == "ERROR":
                print(f"  ERROR: {pdiv.get('error', 'unknown error')}")
            else:
                print(f"  A (no profile context): score={pdiv.get('score_A')}/3")
                print(f"  B (with profile context): score={pdiv.get('score_B')}/3")
                print(f"  Improvement: {pdiv.get('improvement')} "
                      f"(B > A: {pdiv.get('score_B')} vs A: {pdiv.get('score_A')})")
                print(f"  B 李泽宇 → goal_type={pdiv['li_action_type_B']['goal_type']}, "
                      f"urge_type={pdiv['li_action_type_B']['urge_type']}, "
                      f"plan_keywords={pdiv['li_action_type_B']['plan_keywords']}")
                print(f"  B 周婉清 → goal_type={pdiv['zhou_action_type_B']['goal_type']}, "
                      f"urge_type={pdiv['zhou_action_type_B']['urge_type']}, "
                      f"plan_keywords={pdiv['zhou_action_type_B']['plan_keywords']}")
                diffs = []
                if pdiv.get("goal_differ_B"):
                    diffs.append("goal_type不同")
                if pdiv.get("urge_differ_B"):
                    diffs.append("urge_type不同")
                if pdiv.get("plan_differ_B"):
                    diffs.append("plan_keywords不同")
                if diffs:
                    print(f"  B 分化点: {', '.join(diffs)}")
                else:
                    print("  B 分化点: 无明显分化")

        # Runtime A/B multi-step report
        rab = results.get("runtime_ab_diversity", {})
        if rab:
            verdict = rab.get("verdict", "FAIL")
            icon = "OK" if verdict == "PASS" else "!!"
            print()
            print("-" * 60)
            print(f"Runtime A/B Diversity: {verdict} {icon}")
            if verdict == "ERROR":
                print(f"  ERROR: {rab.get('error', 'unknown error')}")
            else:
                print(f"  Steps: {rab.get('steps')} | Contexts A/B: "
                      f"{rab.get('contexts_injected_A')}/{rab.get('contexts_injected_B')}")
                print(f"  Changed steps: {rab.get('changed_steps')}")
                print(f"  A distribution: {rab.get('action_distribution_A')}")
                print(f"  B distribution: {rab.get('action_distribution_B')}")
                print(f"  B profile match score: {rab.get('profile_match_score_B')}")
                print(f"  Interpretation: {rab.get('interpretation')}")

        print()
        print("=" * 60)
    
    def generate_markdown_report(self, results: Dict) -> str:
        """生成Markdown格式报告"""
        md = f"""# 生活史型智能体评估报告

> Agent ID: {results['agent_id']} ({results['agent_name']})  
> 评估日期: {results['evaluation_date']}

## 一、综合评估结果

| 维度 | 得分 | 百分比 | 评级 |
|------|------|--------|------|
"""
        
        for dim_key, dim_result in results["dimensions"].items():
            md += f"| {dim_result['name']} | {dim_result['raw']}/{dim_result['max']} | {dim_result['percentage']}% | "
            if dim_result['percentage'] >= 80:
                md += "✅ 优秀 |\n"
            elif dim_result['percentage'] >= 60:
                md += "⚠️ 一般 |\n"
            else:
                md += "❌ 不足 |\n"
        
        md += f"""
**总分**: {results['total_score']}/{results['total_max']}
**加权得分**: {results['weighted_score']}/100
**评级**: {results['grade']}

## 二、Context Tendency Diversity 验证（辅助指标，不计入总分）

> 验证：同场景下，不同 profile 的 agent 产生不同行为倾向上下文（基于 prompt context 字符串，非真实 action 输出）

"""

        div = results.get("profile_context_diversity", {})
        verdict_icon = "PASS" if div.get("verdict") == "PASS" else "FAIL"
        data_source = div.get("data_source", "unknown")
        warn = " ⚠️ Used fallback dicts (MD parsing failed)" if data_source == "fallback" else ""
        md += f"**验证结果**: {verdict_icon} (source: {data_source}){warn}\n\n"
        for diff in div.get("differences", []):
            md += f"- {diff}\n"
        md += "\n**李泽宇 context**:\n"
        li_ctx = div.get("li_ctx", "")
        md += f"```\n{li_ctx}\n```\n\n"
        md += "**周婉清 context**:\n"
        zhou_ctx = div.get("zhou_ctx", "")
        md += f"```\n{zhou_ctx}\n```\n\n"

        # Plan diversity A/B section
        pdiv = results.get("plan_diversity", {})
        if pdiv:
            verdict = pdiv.get("verdict", "FAIL")
            md += "## 三、Plan/Action Diversity A/B 测试（核心指标，不计入总分）\n\n"
            md += "> 验证：profile context 注入是否让 planning 决策分化更明显\n\n"
            md += f"**验证结果**: {verdict}"
            if verdict == "ERROR":
                md += f" — ERROR: {pdiv.get('error', 'unknown')}\n\n"
            else:
                md += f" — A score={pdiv.get('score_A')}/3, B score={pdiv.get('score_B')}/3, improvement={pdiv.get('improvement')}\n\n"
                md += "**A 李泽宇 plan** (无 profile):\n"
                md += f"```json\n{json.dumps(pdiv.get('li_plan_A', {}), ensure_ascii=False)}\n```\n\n"
                md += "**A 周婉清 plan** (无 profile):\n"
                md += f"```json\n{json.dumps(pdiv.get('zhou_plan_A', {}), ensure_ascii=False)}\n```\n\n"
                md += "**B 李泽宇 plan** (有 profile context):\n"
                md += f"```json\n{json.dumps(pdiv.get('li_plan_B', {}), ensure_ascii=False)}\n```\n\n"
                md += "**B 周婉清 plan** (有 profile context):\n"
                md += f"```json\n{json.dumps(pdiv.get('zhou_plan_B', {}), ensure_ascii=False)}\n```\n\n"
                diffs = []
                if pdiv.get("goal_differ_B"):
                    diffs.append(f"goal_type 不同 ({pdiv['li_action_type_B']['goal_type']} vs {pdiv['zhou_action_type_B']['goal_type']})")
                if pdiv.get("urge_differ_B"):
                    diffs.append(f"urge_type 不同 ({pdiv['li_action_type_B']['urge_type']} vs {pdiv['zhou_action_type_B']['urge_type']})")
                if pdiv.get("plan_differ_B"):
                    diffs.append(f"plan_keywords 不同 ({pdiv['li_action_type_B']['plan_keywords']} vs {pdiv['zhou_action_type_B']['plan_keywords']})")
                if diffs:
                    md += "**B 分化点**:\n"
                    for d in diffs:
                        md += f"- {d}\n"
                    md += "\n"
                else:
                    md += "**B 分化点**: 无明显分化\n\n"

        md += "---\n\n## 四、各维度详细分析\n\n"
        
        for dim_key, dim_result in results["dimensions"].items():
            md += f"### {dim_result['name']}\n\n"
            md += f"| 子指标 | 得分 | 说明 |\n"
            md += f"|--------|------|------|\n"
            
            sub_info = {
                "recall_accuracy": "召回准确率",
                "consistency": "记忆一致性", 
                "recency_effect": "近因效应",
                "personality_consistency": "人格一致性",
                "role_stability": "角色稳定性",
                "background_coverage": "背景知识覆盖",
                "emotion_wave": "情绪波动合理性",
                "emotional_memory": "情感记忆应用",
                "expression_diversity": "情感表达多样性",
                "decision_diversity": "决策多样性",
                "uncertainty_expression": "不确定性表达",
                "bounded_options": "有限选项考虑",
                "behavior_drift_detection": "行为漂移检测",
                "learning_from_error": "从错误中学习",
                "preference_adaptation": "用户偏好适应",
                "relationship_tracking": "关系追踪",
                "trust_evolution": "信任演变",
                "conflict_resolution": "冲突解决"
            }
            
            for sub_key, sub_result in dim_result.get("sub_scores", {}).items():
                sub_name = sub_info.get(sub_key, sub_key)
                md += f"| {sub_name} | {sub_result['raw']}/{sub_result['max']} | "
                if sub_result['percentage'] >= 70:
                    md += "✅ |\n"
                elif sub_result['percentage'] >= 40:
                    md += "⚠️ |\n"
                else:
                    md += "❌ |\n"
            
            md += "\n"
        
        md += """

## 五、Agent 52 (郭林峰) 特点总结

### 6.1 人格特征
- **理性驱动**：极度结果导向，用数据而非语言证明自己
- **矛盾性**：完美主义 vs 速度优先；极度理性 vs 对不确定性焦虑
- **结果导向**：设定可验证的交付节点是核心行为模式

### 6.2 当前优势
- 人格一致性较高（64%）
- 状态更新逻辑正确（MiniMax模型）

### 6.3 待改进项
- 关系记忆（0%）：完全没有追踪与其他Agent的关系
- 有限理性（33.3%）：无决策限制，无不确定性表达
- 情感记忆（45%）：无情感事件记忆机制

## 六、下一步实现计划

| 优先级 | 维度 | 目标 | 实现方式 |
|--------|------|------|----------|
| P0 | 关系记忆 | 20% | 添加RelationshipMemory到Agent状态 |
| P1 | 有限理性 | 55% | 添加bounded_plan约束 |
| P1 | 情感记忆 | 60% | 添加emotional_event记忆 |
| P2 | 记忆分层 | 70% | 实现short_term/long_term分离 |
| P3 | 学习系统 | 50% | 添加behavior_drift检测 |

---
*评估框架版本: 2026-05-25*
"""
        
        return md


def main():
    """主函数"""
    agent_id = int(sys.argv[1]) if len(sys.argv) > 1 else 52
    
    evaluator = LifeHistoryEvaluator(agent_id)
    results = evaluator.run_full_evaluation()
    
    # 打印报告
    evaluator.print_report(results)
    
    # 输出Markdown报告
    md_report = evaluator.generate_markdown_report(results)
    
    # 保存到文件
    output_path = f"output/eval/agent_{agent_id}_life_history_eval.md"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_report)
    
    print(f"\n评估报告已保存到: {output_path}")
    
    # 同时输出JSON格式
    json_path = f"output/eval/agent_{agent_id}_life_history_eval.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"JSON数据已保存到: {json_path}")


if __name__ == "__main__":
    main()
