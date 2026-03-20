import json
import random
import re

from llm_providers import call_llm


def _clamp(value, lo=0.0, hi=1.0):
    return float(max(lo, min(hi, value)))


def _contains_any(text, keywords):
    blob = str(text or "")
    return any(k in blob for k in keywords)


def _time_str_to_minutes(time_str):
    text = str(time_str or "")
    if not re.match(r"^\d{2}:\d{2}$", text):
        return None
    hh, mm = text.split(":")
    return int(hh) * 60 + int(mm)


def _extract_json_block(text):
    if not text:
        return ""
    block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if block_match:
        return block_match.group(1)
    inline_match = re.search(r"\{.*\}", text, re.S)
    return inline_match.group(0) if inline_match else ""


def _parse_json_dict(text):
    blob = _extract_json_block(text)
    if not blob:
        return {}
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def time_bucket(time_str):
    if not re.match(r"^\d{2}:\d{2}$", str(time_str)):
        return "unknown"
    hh = int(time_str.split(":")[0])
    if 5 <= hh < 11:
        return "morning"
    if 11 <= hh < 17:
        return "afternoon"
    if 17 <= hh < 22:
        return "evening"
    return "night"


def location_bucket(location):
    text = str(location or "")
    if any(k in text for k in ["Block", "Home", "Residential", "Village"]):
        return "home"
    if any(k in text for k in ["Office", "Labs", "School", "Clinic", "Hospital", "Studio", "Station"]):
        return "work"
    return "public"


def build_context_key(time_str, location, activity):
    return f"{time_bucket(time_str)}|{location_bucket(location)}|{activity}"


def compute_episode_salience(delta_stress, event_intensity, novelty, goal_relevance):
    salience = (
        0.35 * abs(float(delta_stress))
        + 0.25 * float(event_intensity)
        + 0.20 * float(novelty)
        + 0.20 * float(goal_relevance)
    )
    return _clamp(salience)


def update_needs(agent, time_str, activity):
    state = agent.setdefault("state", {})
    state["energy"] = float(state.get("energy", 0.75))
    state["hunger"] = float(state.get("hunger", 0.25))
    state["social_need"] = float(state.get("social_need", 0.40))
    text = str(activity or "")
    minutes = _time_str_to_minutes(time_str)
    work_like = _contains_any(
        text,
        [
            "工作",
            "上班",
            "学习",
            "上课",
            "通勤",
            "加班",
            "研究",
            "实验",
            "论文",
            "备课",
            "指导",
            "项目",
            "邮件",
            "开会",
            "会议",
            "报告",
        ],
    )
    rest_like = _contains_any(text, ["休息", "睡", "午休", "睡前", "放松", "躺", "小憩"])
    meal_like = _contains_any(
        text,
        [
            "早饭",
            "早餐",
            "午饭",
            "午餐",
            "晚饭",
            "晚餐",
            "吃饭",
            "用餐",
            "外卖",
            "餐馆",
            "餐厅",
            "食堂",
            "做饭",
            "买菜",
            "咖啡",
            "茶歇",
        ],
    )
    social_like = _contains_any(
        text,
        [
            "聊天",
            "聚会",
            "同事",
            "朋友",
            "家人",
            "拜访",
            "学生",
            "合作者",
            "组会",
            "讨论",
            "交流",
            "沟通",
            "协作",
            "社区",
            "通话",
            "会面",
        ],
    )
    active_like = _contains_any(text, ["通勤", "散步", "运动", "健身", "跑步", "采购", "买菜", "出行"])

    energy_delta = -0.012
    if work_like:
        energy_delta -= 0.02
    if active_like:
        energy_delta -= 0.01
    if rest_like:
        energy_delta += 0.08
    if meal_like:
        energy_delta += 0.01
    state["energy"] += energy_delta

    hunger_delta = 0.035
    if minutes is not None and minutes in range(690, 841):
        hunger_delta += 0.015
    if minutes is not None and minutes in range(1050, 1201):
        hunger_delta += 0.015
    if work_like or active_like:
        hunger_delta += 0.01
    if meal_like:
        hunger_delta -= 0.28
    state["hunger"] += hunger_delta

    social_delta = 0.015
    if work_like and not social_like:
        social_delta += 0.01
    if rest_like and not social_like:
        social_delta += 0.01
    if social_like:
        social_delta -= 0.08
    state["social_need"] += social_delta

    state["energy"] = _clamp(state["energy"])
    state["hunger"] = _clamp(state["hunger"])
    state["social_need"] = _clamp(state["social_need"])


def infer_episode_tags(activity, action, reflection, env_events=None, policy_event=None):
    tags = set()
    blob = " ".join([
        str(activity or ""),
        str(action or ""),
        str(reflection or ""),
        " ".join(str(e) for e in (env_events or [])),
        str(policy_event or ""),
    ])
    if any(k in blob for k in ["工作", "上班", "通勤", "加班", "会议"]):
        tags.add("work")
    if any(k in blob for k in ["家", "家人", "陪伴", "照顾"]):
        tags.add("family")
    if any(k in blob for k in ["医院", "诊所", "锻炼", "健康", "晨练"]):
        tags.add("health")
    if any(k in blob for k in ["政策", "制度", "监管"]):
        tags.add("policy")
    if any(k in blob for k in ["争执", "冲突", "不满", "抗议"]):
        tags.add("conflict")
    if any(k in blob for k in ["完成", "顺利", "满意", "进展"]):
        tags.add("success")
    if any(k in blob for k in ["失败", "挫败", "焦虑", "拖延"]):
        tags.add("failure")
    return sorted(tags) if tags else ["routine"]


def _fallback_intentions(agent, recent_episodes):
    state = agent.get("state", {})
    priorities = []
    if state.get("stress", 0.5) > 0.65:
        priorities.append("降低压力")
    if state.get("econ_security", 0.5) < 0.45:
        priorities.append("提高收入稳定性")
    if state.get("city_identity", 0.5) < 0.45:
        priorities.append("保持社区连接")
    if not priorities:
        priorities.append("维持日常节奏")
    top_tags = []
    for ep in recent_episodes[:3]:
        top_tags.extend(ep.get("tags", []))
    if "health" in top_tags:
        priorities.append("保证身体状态")
    avoidances = ["冲动决策"] if state.get("stress", 0.5) > 0.7 else ["长时间无效分心"]
    target_social = "增加与熟人的正向互动" if state.get("social_need", 0.5) > 0.55 else "保持适度社交"
    target_recovery = "确保休息与进食节奏"
    return {
        "priorities": priorities[:4],
        "avoidances": avoidances[:2],
        "target_social": target_social,
        "target_recovery": target_recovery,
    }


def build_daily_intentions(agent, recent_episodes, cfg, llm_budget_ctx):
    fallback = _fallback_intentions(agent, recent_episodes)
    if not isinstance(llm_budget_ctx, dict) or llm_budget_ctx.get("remaining", 0) <= 0:
        return fallback
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"当前状态：{json.dumps(agent.get('state', {}), ensure_ascii=False)}",
    ])
    eps = recent_episodes[:5]
    eps_text = json.dumps(
        [
            {
                "activity": e.get("final_activity", ""),
                "action": e.get("action", ""),
                "salience": e.get("salience", 0),
                "tags": e.get("tags", []),
                "reflection": e.get("reflection", ""),
            }
            for e in eps
        ],
        ensure_ascii=False,
        indent=2,
    )
    prompt = f"""
你是城市模拟器中的“每日意图生成器”。
请根据角色信息与最近高显著性经历，给出今天的行为意图。
角色信息：
{profile_text}
近期经历：
{eps_text}

只输出 JSON：
{{
  "priorities": ["...","..."],
  "avoidances": ["..."],
  "target_social": "...",
  "target_recovery": "..."
}}
要求：
1) priorities 2-4项，avoidances 1-2项。
2) 都是中文短语。
3) 不要输出其他文字。
"""
    llm_budget_ctx["remaining"] = max(0, int(llm_budget_ctx.get("remaining", 0)) - 1)
    try:
        resp = call_llm(prompt, task="daily_intentions", agent_id=agent["id"])
    except Exception:
        return fallback
    parsed = _parse_json_dict(resp)
    if not parsed:
        return fallback
    priorities = parsed.get("priorities", [])
    avoidances = parsed.get("avoidances", [])
    if not isinstance(priorities, list):
        priorities = []
    if not isinstance(avoidances, list):
        avoidances = []
    result = {
        "priorities": [str(x).strip() for x in priorities if str(x).strip()][:4] or fallback["priorities"],
        "avoidances": [str(x).strip() for x in avoidances if str(x).strip()][:2] or fallback["avoidances"],
        "target_social": str(parsed.get("target_social", "")).strip() or fallback["target_social"],
        "target_recovery": str(parsed.get("target_recovery", "")).strip() or fallback["target_recovery"],
    }
    return result


def update_habits_from_episode(agent, episode, cfg):
    behavior_cfg = (cfg or {}).get("behavior", {})
    learning_rate = float(behavior_cfg.get("habit_learning_rate", 0.08))
    habits = agent.setdefault("habits", {})
    ctx = build_context_key(episode.get("time", ""), episode.get("location", ""), episode.get("final_activity", ""))
    action = str(episode.get("action", "")).strip()
    if not action:
        return habits
    item = habits.setdefault(
        ctx,
        {
            "action_counts": {},
            "preferred_action": action,
            "strength": 0.1,
            "last_updated_day": int(episode.get("day", 0)),
        },
    )
    counts = item.setdefault("action_counts", {})
    counts[action] = int(counts.get(action, 0)) + 1
    preferred = max(counts.items(), key=lambda x: x[1])[0]
    item["preferred_action"] = preferred
    item["last_updated_day"] = int(episode.get("day", 0))
    if preferred == action:
        item["strength"] = _clamp(float(item.get("strength", 0.1)) + learning_rate * (1 - float(item.get("strength", 0.1))))
    else:
        item["strength"] = _clamp(float(item.get("strength", 0.1)) * (1 - learning_rate * 0.5))
    return habits


def consolidate_day(agent, day, episodes, cfg, llm_budget_ctx):
    memory_cfg = (cfg or {}).get("memory", {})
    top_k = int(memory_cfg.get("daily_consolidation_top_k", 12))
    selected = sorted(
        episodes,
        key=lambda e: float(e.get("decayed_salience", e.get("salience", 0.0))),
        reverse=True,
    )[:top_k]
    fallback_intentions = _fallback_intentions(agent, selected)
    if not selected:
        return {
            "summary": "今天整体较平稳，按常规节奏推进。",
            "intentions": fallback_intentions,
            "top_episode_ids": [],
            "memory_text": f"[Day {day}] 今天整体较平稳，按常规节奏推进。",
        }
    summary_lines = [
        f"{e.get('time', '')} {e.get('final_activity', '')} -> {e.get('action', '')} (salience={float(e.get('salience', 0.0)):.2f})"
        for e in selected[:5]
    ]
    base_summary = "；".join(summary_lines)
    result = {
        "summary": base_summary,
        "intentions": fallback_intentions,
        "top_episode_ids": [str(e.get("episode_id", "")) for e in selected if e.get("episode_id")],
    }
    if isinstance(llm_budget_ctx, dict) and llm_budget_ctx.get("remaining", 0) > 0:
        prompt = f"""
你是城市模拟器中的“日终经验整合器”。
请根据以下经历生成一句经验总结，并给出明日行为意图。
角色：{agent.get('name', '')}
经历：
{json.dumps(summary_lines, ensure_ascii=False, indent=2)}
输出 JSON：
{{
  "summary": "...",
  "priorities": ["...","..."],
  "avoidances": ["..."],
  "target_social": "...",
  "target_recovery": "..."
}}
仅输出 JSON。
"""
        llm_budget_ctx["remaining"] = max(0, int(llm_budget_ctx.get("remaining", 0)) - 1)
        try:
            resp = call_llm(prompt, task="memory_consolidation", agent_id=agent["id"])
        except Exception:
            resp = ""
        parsed = _parse_json_dict(resp)
        if parsed:
            result["summary"] = str(parsed.get("summary", "")).strip() or result["summary"]
            result["intentions"] = {
                "priorities": [str(x).strip() for x in parsed.get("priorities", []) if str(x).strip()][:4]
                or fallback_intentions["priorities"],
                "avoidances": [str(x).strip() for x in parsed.get("avoidances", []) if str(x).strip()][:2]
                or fallback_intentions["avoidances"],
                "target_social": str(parsed.get("target_social", "")).strip() or fallback_intentions["target_social"],
                "target_recovery": str(parsed.get("target_recovery", "")).strip() or fallback_intentions["target_recovery"],
            }
    result["memory_text"] = f"[Day {day} Consolidation] {result['summary']}"
    return result


def relationship_update(agent, neighbor_id, interaction_signal, cfg):
    relationships = agent.setdefault("relationships", {})
    key = str(neighbor_id)
    item = relationships.setdefault(
        key,
        {
            "closeness": 0.5,
            "trust": 0.5,
            "last_interaction_day": int(agent.get("current_day", 0)),
        },
    )
    signal = str(interaction_signal or "neutral")
    if signal == "positive":
        item["closeness"] = _clamp(float(item.get("closeness", 0.5)) + 0.03)
        item["trust"] = _clamp(float(item.get("trust", 0.5)) + 0.02)
    elif signal == "negative":
        item["closeness"] = _clamp(float(item.get("closeness", 0.5)) - 0.04)
        item["trust"] = _clamp(float(item.get("trust", 0.5)) - 0.03)
    else:
        item["closeness"] = _clamp(float(item.get("closeness", 0.5)) + 0.01)
    item["last_interaction_day"] = int(agent.get("current_day", 0))
    return item


def relationship_weight(agent, neighbor_id):
    rel = agent.get("relationships", {})
    item = rel.get(str(neighbor_id), {})
    return float(item.get("closeness", 0.5))


def infer_interaction_signal(reflection_text):
    text = str(reflection_text or "")
    if any(k in text for k in ["满意", "开心", "顺利", "支持", "放松"]):
        return "positive"
    if any(k in text for k in ["冲突", "焦虑", "烦躁", "不满", "争执"]):
        return "negative"
    return "neutral"


def intention_text(intentions):
    if not isinstance(intentions, dict):
        return "无明确意图"
    priorities = intentions.get("priorities", [])
    avoidances = intentions.get("avoidances", [])
    social = intentions.get("target_social", "")
    recovery = intentions.get("target_recovery", "")
    p_text = "、".join(str(x) for x in priorities if str(x).strip()) or "无"
    a_text = "、".join(str(x) for x in avoidances if str(x).strip()) or "无"
    return f"优先：{p_text}；避免：{a_text}；社交：{social or '无'}；恢复：{recovery or '无'}"
