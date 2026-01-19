import pandas as pd
import requests
import time
import random
import numpy as np
import re
import json
from collections import defaultdict

import os
import matplotlib.pyplot as plt
import networkx as nx

# =========================================================
# Utils
# =========================================================
def visualize_social_network(
    agents,
    step=None,
    output_dir="output/network",
    node_color_attr=None
):
    """
    agents:
        - dict: {agent_id: agent_dict}
        - or list: [agent_dict, ...]
    agent_dict 中建议包含：
        - "id" 或 "name"
        - "friends" / "social_connections"
    """

    os.makedirs(output_dir, exist_ok=True)

    G = nx.Graph()

    # ---------- 统一 agent 访问方式 ----------
    if isinstance(agents, dict):
        agent_items = agents.items()
    else:  # list
        agent_items = [(a.get("id", str(i)), a) for i, a in enumerate(agents)]

    # ---------- 加节点 ----------
    for agent_id, agent in agent_items:
        value = agent.get(node_color_attr, 0.5) if node_color_attr else 0.5
        G.add_node(agent_id, value=value)

    # ---------- 加边 ----------
    for agent_id, agent in agent_items:
        friends = (
            agent.get("friends")
            or agent.get("social_connections")
            or []
        )
        for f in friends:
            if G.has_node(f):
                G.add_edge(agent_id, f)

    # ---------- 布局 ----------
    pos = nx.spring_layout(G, seed=42)

    node_values = [G.nodes[n]["value"] for n in G.nodes]

    plt.figure(figsize=(8, 8))
    nodes = nx.draw_networkx_nodes(
        G,
        pos,
        node_size=300,
        node_color=node_values,
        cmap=plt.cm.YlGn
    )
    nx.draw_networkx_edges(G, pos, alpha=0.4)
    nx.draw_networkx_labels(G, pos, font_size=8)

    if node_color_attr:
        plt.colorbar(nodes, label=node_color_attr)

    title = "Social Network"
    if step is not None:
        title += f" (Step {step})"
    plt.title(title)

    plt.axis("off")

    filename = "social_network.png" if step is None else f"social_network_{step:03d}.png"
    plt.savefig(os.path.join(output_dir, filename), dpi=200)
    plt.close()

def visualize_agent_state_changes(
    state_history,
    agent_names,
    output_dir="output/state",
    metrics=None,
):
    os.makedirs(output_dir, exist_ok=True)
    if not metrics:
        metrics = ["emotion", "stress", "econ_security", "city_identity"]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    axes = axes.flatten()

    steps = None
    for i, metric in enumerate(metrics):
        ax = axes[i]
        for agent_id, history in state_history.items():
            series = history.get(metric, [])
            if steps is None:
                steps = list(range(len(series)))
            label = agent_names.get(agent_id, str(agent_id))
            ax.plot(steps, series, label=label, linewidth=1.8)
        ax.set_title(metric)
        ax.set_ylim(0, 1)
        ax.grid(True, alpha=0.2)

    axes[0].legend(loc="upper right", fontsize=8)
    fig.suptitle("Agent State Changes Over Time")
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    out_path = os.path.join(output_dir, "agent_state_over_time.png")
    plt.savefig(out_path, dpi=200)
    plt.close()


# =========================================================
# Ollama
# =========================================================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma3n:e4b"

def call_llm(prompt):
    r = requests.post(
        OLLAMA_URL,
        json={"model": MODEL_NAME, "prompt": prompt, "stream": False},
        timeout=120
    )
    return r.json()["response"].strip()

# =========================================================
# 参数
# =========================================================
AGENT_IDS = [31, 1, 5]   # 可扩展为 100
#AGENT_IDS = list(range(1, 3))   # 可扩展为 100
SIM_DAYS = 1
SECONDS_PER_DAY = 30

CSV_PATH = "hangzhou_agents_state_init.csv"
MD_PATH = "hangzhou_profiles_with_names.md"

# =========================================================
# 政策事件
# =========================================================
POLICY_EVENTS = [
    {
        "day": 1,
        "time": "10:00",
        "name": "平台劳动者保障政策",
        "effect": {
            "econ_security": +0.15,
            "stress": -0.10,
            "city_identity": +0.08
        }
    }
]

# =========================================================
# Profile 解析
# =========================================================
def load_profile_from_md(agent_id):
    with open(MD_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    pattern = rf"## Profile {agent_id:02d}｜.*?(?=\n## Profile |\Z)"
    match = re.search(pattern, text, re.S)
    if not match:
        raise ValueError(f"Profile {agent_id} not found")
    return match.group(0)

def parse_profile(block):
    def _extract(pattern, default=""):
        match = re.search(pattern, block)
        return match.group(1) if match else default

    p = {}
    p["name"] = _extract(r"## Profile \d+｜(.+)")
    base = _extract(r"\*\*基础信息\*\*：(.+)")
    p["age"] = int(re.search(r"(\d+)岁", base).group(1))
    p["living"] = re.search(r"居住(?:于)?(.+?)[，。]", base).group(1)
    p["job"] = _extract(r"\*\*职业与工作节奏\*\*：(.+)")
    p["personality"] = _extract(r"\*\*性格与情绪特征\*\*：(.+)")
    p["daily_life"] = _extract(r"\*\*日常生活与生活习惯\*\*：(.+)")
    p["values"] = _extract(r"\*\*价值观与公共事务态度\*\*：(.+)")
    p["work_style"] = p["job"]
    return p

def build_agent(agent_id, df):
    row = df[df["id"] == agent_id].iloc[0]
    text = parse_profile(load_profile_from_md(agent_id))
    return {
        "id": agent_id,
        **text,
        "state": {
            "emotion": row["emotion"],
            "stress": row["stress"],
            "econ_security": row["econ_security"],
            "city_identity": row["city_identity"]
        },
        "memory": [],
        "social_neighbors": []
    }

# =========================================================
# 社交网络构建（核心新增）
# =========================================================
def build_social_network(agents, avg_degree=6, p_cross=0.15):
    groups = defaultdict(list)

    for a in agents:
        age_group = a["age"] // 10 * 10
        job_key = a["job"][:6]
        groups[f"{job_key}_{age_group}"].append(a["id"])

    network = {a["id"]: set() for a in agents}
    all_ids = [a["id"] for a in agents]

    # 组内连接
    for members in groups.values():
        for a in members:
            others = [m for m in members if m != a]
            k = min(len(others), avg_degree)
            for b in random.sample(others, k=k) if others else []:
                network[a].add(b)
                network[b].add(a)

    # 跨组弱连接
    for a in all_ids:
        if random.random() < p_cross:
            b = random.choice(all_ids)
            if b != a:
                network[a].add(b)
                network[b].add(a)

    return {k: list(v) for k, v in network.items()}

# =========================================================
# Schedule & Action
# =========================================================
def _extract_json_array_block(text):
    block_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    if block_match:
        return block_match.group(1)
    inline_match = re.search(r"\[.*\]", text, re.S)
    return inline_match.group(0) if inline_match else ""

def _parse_schedule(text):
    json_blob = _extract_json_array_block(text)
    if not json_blob:
        return []
    try:
        raw = json.loads(json_blob)
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    schedule = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            time_str, activity = item
        elif isinstance(item, dict) and "time" in item and "activity" in item:
            time_str, activity = item["time"], item["activity"]
        else:
            continue
        time_str = str(time_str).strip()
        activity = str(activity).strip()
        if re.match(r"^\d{2}:\d{2}$", time_str) and activity:
            schedule.append((time_str, activity))
    if not schedule:
        return []
    seen = set()
    cleaned = []
    for time_str, activity in schedule:
        if time_str in seen:
            continue
        seen.add(time_str)
        cleaned.append((time_str, activity))
    return cleaned

def _heuristic_schedule(agent):
    profile_blob = " ".join([
        agent.get("job", ""),
        agent.get("personality", ""),
        agent.get("daily_life", ""),
        agent.get("values", "")
    ])

    is_student = any(k in profile_blob for k in ["学生", "硕士", "博士", "课题组"])
    is_retired = any(k in profile_blob for k in ["退休", "无业", "待业", "失业", "家庭主妇", "家庭主夫"])
    late_schedule = any(k in profile_blob for k in ["夜间活跃", "晚睡", "作息偏晚"])

    if is_retired:
        base = [
            ("07:30", "晨练"),
            ("08:30", "吃早饭"),
            ("10:00", "买菜"),
            ("11:30", "午饭"),
            ("13:00", "午休"),
            ("16:00", "散步"),
            ("18:00", "晚饭"),
            ("20:00", "个人时间"),
            ("22:30", "睡前"),
        ]
        return base

    if is_student:
        base = [
            ("09:30", "吃早饭"),
            ("10:00", "上午学习"),
            ("12:00", "午饭"),
            ("14:00", "下午学习"),
            ("18:00", "下课"),
            ("20:30", "个人时间"),
            ("00:30", "睡前"),
        ]
        return base

    if late_schedule:
        base = [
            ("09:30", "吃早饭"),
            ("10:30", "通勤"),
            ("11:00", "上午工作"),
            ("12:30", "午饭"),
            ("14:30", "下午工作"),
        ]
        base += [("19:30", "加班" if "加班" in agent["work_style"] else "下班")]
        base += [("22:00", "个人时间"), ("01:00", "睡前")]
        return base

    base = [
        ("08:00", "吃早饭"),
        ("09:00", "通勤"),
        ("10:00", "上午工作"),
        ("12:00", "午饭"),
        ("14:00", "下午工作"),
    ]
    base += [("18:30", "加班" if "加班" in agent["work_style"] else "下班")]
    base += [("21:00", "个人时间"), ("23:30", "睡前")]
    return base

def generate_schedule(agent):
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    prompt = f"""
你是城市生活模拟器的日程生成器。请基于角色资料生成一天日程安排。
角色资料：
{profile_text}
要求：
1) 输出 JSON 数组，每项为 ["HH:MM","活动"] 或 {{"time":"HH:MM","activity":"活动"}}。
2) 6-10 项，时间升序覆盖早中晚，活动为中文短语。
3) 若角色为退休/无业/待业/失业/家庭主妇/家庭主夫/已退休，不出现“工作/通勤/上班/加班”等活动。
4) 若角色为学生，优先出现“上课/学习/实验”等活动；若作息偏晚，适度延后。
5) 仅输出 JSON，不要其他文字。
"""
    response = call_llm(prompt)
    schedule = _parse_schedule(response)
    if schedule:
        return schedule
    return _heuristic_schedule(agent)

def _extract_json_block(text):
    block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if block_match:
        return block_match.group(1)
    inline_match = re.search(r"\{.*\}", text, re.S)
    return inline_match.group(0) if inline_match else ""

def _parse_action_space(text, activities):
    json_blob = _extract_json_block(text)
    if not json_blob:
        return {}
    try:
        raw = json.loads(json_blob)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    action_space = {}
    for activity in activities:
        acts = raw.get(activity, [])
        if not isinstance(acts, list):
            continue
        cleaned = [str(a).strip() for a in acts if str(a).strip()]
        if cleaned:
            action_space[activity] = cleaned
    return action_space

def _llm_generate_actions(agent, activities, seed_actions=None):
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    seed_text = ""
    if seed_actions:
        seed_text = f"\n已有动作参考（可改写、扩展、去重）：\n{json.dumps(seed_actions, ensure_ascii=False, indent=2)}"
    prompt = f"""
你是城市生活模拟器的动作生成器。请基于角色资料，为每个活动生成具体动作。
角色资料：
{profile_text}
活动列表：{", ".join(activities)}
要求：
1) 每个活动给出 5-10 个动作，中文短语。
2) 动作要符合角色职业、性格与生活习惯。
3) 仅输出 JSON 对象，键为活动名，值为动作列表，不要输出其他文字。
{seed_text}
"""
    response = call_llm(prompt)
    action_space = _parse_action_space(response, activities)
    missing = [a for a in activities if a not in action_space]
    if missing:
        retry_prompt = f"""
请只为以下活动补全动作，仍然严格输出 JSON。
角色资料：
{profile_text}
活动列表：{", ".join(missing)}
每个活动 5-10 个动作，中文短语。
"""
        retry_response = call_llm(retry_prompt)
        retry_actions = _parse_action_space(retry_response, missing)
        for activity, acts in retry_actions.items():
            action_space[activity] = acts
    return action_space

def generate_actions(agent, schedule):
    activities = sorted({activity for _, activity in schedule})
    return _llm_generate_actions(agent, activities)

def build_action_space_for_agent(agent, base_actions):
    activities = list(base_actions.keys())
    refined_actions = _llm_generate_actions(agent, activities, seed_actions=base_actions)
    action_space = {k: list(v) for k, v in base_actions.items()}
    for activity, acts in refined_actions.items():
        action_space.setdefault(activity, [])
        for act in acts:
            if act not in action_space[activity]:
                action_space[activity].append(act)
    return action_space

DEFAULT_ACTIONS = {
    "工作": "继续处理手头工作",
    "时间": "发呆",
}

def fallback_action(activity):
    for k, v in DEFAULT_ACTIONS.items():
        if k in activity:
            return v
    return "继续当前活动"

def choose_action(agent, activity, action_space):
    options = action_space.get(activity, [])

    # === 关键兜底：防止空动作空间 ===
    #if not options:
    #    return "继续当前活动"

    if not options:
        return fallback_action(activity)

    weights = []
    s = agent["state"]

    for act in options:
        w = 1.0

        # 压力高 → 更可能摸鱼 / 情绪化
        if s["stress"] > 0.7 and any(k in act for k in ["摸鱼", "拖延", "发呆", "胡思乱想"]):
            w += 1.5

        # 情绪低 → 回避型行为
        if s["emotion"] < 0.4 and any(k in act for k in ["刷手机", "放空", "无意识"]):
            w += 1.2

        # 经济安全感高 → 自我提升
        if s["econ_security"] > 0.6 and any(k in act for k in ["读书", "学习", "规划"]):
            w += 0.8

        # 睡前更容易反思
        if activity == "睡前" and "回顾" in act:
            w += 1.0

        weights.append(max(w, 0.01))  # 防止权重为 0

    return random.choices(options, weights=weights, k=1)[0]

# =========================================================
# A. 认知模块（使用社交网络）
# =========================================================
def get_social_context(agent, agents_by_id):
    neighbors = agent["social_neighbors"]
    if not neighbors:
        return "今天几乎没有与熟人互动。"
    sampled = random.sample(neighbors, min(3, len(neighbors)))
    names = [agents_by_id[n]["name"] for n in sampled]
    return "、".join(names) + "等熟人的近况对你产生影响。"

def perception(agent, time_str, social_context, policy_event):
    prompt = f"""
你是{agent['name']}。
现在是 {time_str}。
你感知到的社交环境是：{social_context}
政策环境：{policy_event if policy_event else "无特殊变化"}

请描述你此刻对环境、他人和制度的感知。（1-2句）
"""
    return call_llm(prompt)

def planning(agent, perception_text):
    memory_hint = "；".join(agent["memory"][-2:]) if agent["memory"] else "暂无重要经验"
    prompt = f"""
你是{agent['name']}。
你的感知是：{perception_text}
你的近期经验：{memory_hint}

你此刻的短期计划是什么？（1-2句）
"""
    return call_llm(prompt)

def reflection(agent, outcome):
    prompt = f"""
你是{agent['name']}。
刚刚发生的事情是：{outcome}

你对此有何反思或情绪变化？（1-2句）
"""
    return call_llm(prompt)

# =========================================================
# 社会影响（情绪扩散）
# =========================================================
def social_influence(agent, agents_by_id):
    neighbors = agent["social_neighbors"]
    if not neighbors:
        return
    avg_emotion = sum(agents_by_id[n]["state"]["emotion"] for n in neighbors) / len(neighbors)
    agent["state"]["emotion"] += 0.1 * (avg_emotion - agent["state"]["emotion"])

# =========================================================
# 状态更新
# =========================================================
def update_state(agent):
    s = agent["state"]
    s["emotion"] += 0.05 * s["econ_security"] - 0.07 * s["stress"] + random.uniform(-0.02, 0.02)
    s["stress"] += random.uniform(-0.02, 0.03)
    for k in s:
        s[k] = float(np.clip(s[k], 0, 1))

# =========================================================
# B. 长期记忆
# =========================================================
def daily_summary(agent, logs):
    prompt = f"""
你是{agent['name']}。
这是你今天经历的关键片段：
{logs}

请总结今天最重要的一条经验或感受。
"""
    memory = call_llm(prompt)
    agent["memory"].append(memory)
    return memory

# =========================================================
# C. 主循环
# =========================================================
def validate_action_space(schedules, action_space):
    missing = set()
    if not schedules:
        return

    def iter_action_spaces():
        sample_key = next(iter(action_space.keys()))
        if isinstance(sample_key, int):
            return action_space.items()
        return ((agent_id, action_space) for agent_id in schedules.keys())

    for agent_id, space in iter_action_spaces():
        sch = schedules.get(agent_id, [])
        for _, activity in sch:
            if activity not in space:
                missing.add(activity)
    if missing:
        print("⚠️ 警告：以下活动没有定义动作空间：")
        for m in missing:
            print("  -", m)

def build_schedule_map(schedules):
    return {agent_id: {t: a for t, a in sch} for agent_id, sch in schedules.items()}

def build_master_timeline(schedules):
    times = set()
    for sch in schedules.values():
        times.update(t for t, _ in sch)
    return sorted(times)

def run_simulation():
    df = pd.read_csv(CSV_PATH)
    agents = [build_agent(i, df) for i in AGENT_IDS]
    agents_by_id = {a["id"]: a for a in agents}
    agent_names = {a["id"]: a.get("name", str(a["id"])) for a in agents}
    state_history = {
        a["id"]: {
            "emotion": [],
            "stress": [],
            "econ_security": [],
            "city_identity": [],
        }
        for a in agents
    }

    # === 构建社交网络 ===
    social_net = build_social_network(agents)
    for a in agents:
        a["social_neighbors"] = social_net[a["id"]]


    schedules = {a["id"]: generate_schedule(a) for a in agents}
    schedule_map = build_schedule_map(schedules)
    timeline = build_master_timeline(schedules)
    actions = {}
    for a in agents:
        base_actions = generate_actions(a, schedules[a["id"]])
        actions[a["id"]] = build_action_space_for_agent(a, base_actions)

    validate_action_space(schedules, actions)

    sleep_step = SECONDS_PER_DAY / (SIM_DAYS * max(len(timeline), 1))

    for day in range(1, SIM_DAYS + 1):
        print(f"\n================= Day {day} =================")
        daily_logs = defaultdict(str)


            
        for time_str in timeline:
            policy = next((p for p in POLICY_EVENTS if p["day"] == day and p["time"] == time_str), None)

            for agent in agents:
                #act = random.choice(actions.get(activity, ["继续当前活动"]))
                activity = schedule_map[agent["id"]].get(time_str, "个人时间")
                act = choose_action(agent, activity, actions[agent["id"]])
                social_context = get_social_context(agent, agents_by_id)

                perc = perception(agent, time_str, social_context, policy["name"] if policy else None)
                plan = planning(agent, perc)
                outcome = f"在【{activity}】中执行了【{act}】"
                refl = reflection(agent, outcome)

                if policy:
                    for k, v in policy["effect"].items():
                        agent["state"][k] += v

                social_influence(agent, agents_by_id)
                update_state(agent)
                for metric in state_history[agent["id"]]:
                    state_history[agent["id"]][metric].append(agent["state"][metric])

                log = f"""
[{agent['name']} @ {time_str}]
Perception: {perc}
Plan: {plan}
Action: {act}
Outcome: {outcome}
Reflection: {refl}
"""
                print(log)
                daily_logs[agent["id"]] += log

            time.sleep(sleep_step)

        for agent in agents:
            mem = daily_summary(agent, daily_logs[agent["id"]])
            print(f"🧠 {agent['name']} 的今日长期记忆：{mem}")

    print("\n✅ 模拟完成")
    visualize_social_network(agents)
    visualize_agent_state_changes(state_history, agent_names)


# =========================================================
# 入口
# =========================================================
if __name__ == "__main__":
    run_simulation()
