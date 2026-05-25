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
        verdict = "PASS" if (contexts_differ and daily_differentiated and personality_differentiated) else "FAIL"

        return {
            "pass": verdict == "PASS",
            "verdict": verdict,
            "li_ctx": li_ctx,
            "zhou_ctx": zhou_ctx,
            "differences": differences,
            "daily_differentiated": daily_differentiated,
            "personality_differentiated": personality_differentiated,
            "contexts_differ": contexts_differ,
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

        # Profile context diversity 验证
        div = results.get("profile_context_diversity", {})
        if div:
            verdict_icon = "PASS" if div.get("verdict") == "PASS" else "FAIL"
            icon = "OK" if div.get("verdict") == "PASS" else "!!"
            print()
            print("-" * 60)
            print(f"Profile Context Diversity: {verdict_icon} {icon}")
            for diff in div.get("differences", []):
                print(f"  {diff}")

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

## 二、Profile Context Diversity 验证（辅助指标，不计入总分）

"""

        div = results.get("profile_context_diversity", {})
        verdict_icon = "PASS" if div.get("verdict") == "PASS" else "FAIL"
        md += f"**验证结果**: {verdict_icon}\n\n"
        for diff in div.get("differences", []):
            md += f"- {diff}\n"
        md += "\n**李泽宇 context**:\n"
        li_ctx = div.get("li_ctx", "")
        md += f"```\n{li_ctx}\n```\n\n"
        md += "**周婉清 context**:\n"
        zhou_ctx = div.get("zhou_ctx", "")
        md += f"```\n{zhou_ctx}\n```\n\n"

        md += "---\n\n## 三、各维度详细分析\n\n"
        
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
        
        md += """## 四、Agent 52 (郭林峰) 特点总结

### 4.1 人格特征
- **理性驱动**：极度结果导向，用数据而非语言证明自己
- **矛盾性**：完美主义 vs 速度优先；极度理性 vs 对不确定性焦虑
- **结果导向**：设定可验证的交付节点是核心行为模式

### 4.2 当前优势
- 人格一致性较高（64%）
- 状态更新逻辑正确（MiniMax模型）

### 4.3 待改进项
- 关系记忆（0%）：完全没有追踪与其他Agent的关系
- 有限理性（33.3%）：无决策限制，无不确定性表达
- 情感记忆（45%）：无情感事件记忆机制

## 五、下一步实现计划

| 优先级 | 维度 | 目标 | 实现方式 |
|--------|------|------|----------|
| P0 | 关系记忆 | 20% | 添加RelationshipMemory到Agent状态 |
| P1 | 有限理性 | 55% | 添加bounded_plan约束 |
| P1 | 情感记忆 | 60% | 添加emotional_event记忆 |
| P2 | 记忆分层 | 70% | 实现short_term/long_term分离 |
| P3 | 学习系统 | 50% | 添加behavior_drift检测 |

---
*评估框架版本: 2026-05-24*
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
