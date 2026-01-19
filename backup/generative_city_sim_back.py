import pandas as pd
import requests
import time
import random
import numpy as np
import re
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
AGENT_IDS = list(range(1, 3))   # 可扩展为 100
SIM_DAYS = 2
SECONDS_PER_DAY = 60

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
def generate_schedule(agent):
    profile_blob = " ".join([
        agent.get("job", ""),
        agent.get("personality", ""),
        agent.get("daily_life", ""),
        agent.get("values", "")
    ])

    is_student = any(k in profile_blob for k in ["学生", "硕士", "博士", "课题组"])
    late_schedule = any(k in profile_blob for k in ["夜间活跃", "晚睡", "作息偏晚"])

    if is_student:
        base = [
            ("09:30", "吃早饭"),
            ("10:00", "上午工作"),
            ("12:00", "午饭"),
            ("14:00", "下午工作"),
            ("18:00", "下班"),
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

def generate_actions():
    return {

        "吃早饭": [
            "点外卖",
            "便利店解决",
            "自己做",
            "路上随便买点",
            "和同事一起吃",
            "边走边吃",
            "干脆不吃",
            "买了但没吃完"
        ],

        "通勤": [
            "坐地铁刷手机",
            "坐地铁发呆",
            "骑车通勤",
            "骑车顺路买咖啡",
            "开车通勤",
            "打车赶时间",
            "步行一段路",
            "通勤途中情绪低落",
            "通勤途中规划今天"
        ],

        "上午工作": [
            "专注高效工作",
            "正常工作",
            "开会",
            "被迫开会",
            "处理杂事",
            "处理他人甩锅的任务",
            "摸鱼刷手机",
            "一边工作一边分心",
            "被临时需求打断",
            "对工作产生倦怠感"
        ],

        "午饭": [
            "点外卖",
            "吃食堂",
            "与同事聚餐"
        ],

        "下午工作": [
            "继续推进核心工作",
            "处理杂事",
            "开会",
            "无意义的会议",
            "效率低下地拖延",
            "摸鱼刷手机",
            "开始期待下班",
            "情绪波动影响效率",
            "思考职业发展",
            "被领导临时点名"
        ],

        "加班": [
            "加班认真工作",
            "加班但效率很低",
            "一边加班一边摸鱼",
            "情绪低落地应付工作",
            "临时被拉去加班开会",
            "加班中产生强烈疲惫感",
            "开始怀疑加班的意义"
        ],

        "下班": [
            "直接回家",
            "顺路买菜",
            "逛街放松一下",
            "朋友聚会",
            "约会",
            "独自散步",
            "下班路上继续刷手机",
            "加班后情绪疲惫地回家",
            "临时改变下班计划"
        ],

        "个人时间": [
            "刷手机",
            "无意识刷短视频",
            "发呆",
            "读书",
            "搞卫生",
            "打游戏",
            "健身或拉伸",
            "看视频",
            "给家人打电话",
            "和朋友线上聊天",
            "反复回想白天的事情",
            "情绪性放空",
            "短暂学习新技能"
        ],

        "睡前": [
            "回顾一天",
            "简单规划明天",
            "刷手机到很晚",
            "情绪性胡思乱想",
            "对未来感到焦虑",
            "很快入睡",
            "睡前继续工作相关思考",
            "睡前刷社交媒体"
        ]
    }

def build_action_space_for_agent(agent, base_actions):
    action_space = {k: list(v) for k, v in base_actions.items()}

    def add_actions(activity, actions):
        if activity not in action_space:
            action_space[activity] = []
        for act in actions:
            if act not in action_space[activity]:
                action_space[activity].append(act)

    profile_blob = " ".join([
        agent.get("job", ""),
        agent.get("personality", ""),
        agent.get("daily_life", ""),
        agent.get("values", "")
    ])

    if any(k in profile_blob for k in ["算法", "工程师", "开发"]):
        add_actions("上午工作", ["调参实验", "写模型代码", "排查线上问题"])
        add_actions("下午工作", ["写技术方案", "复盘实验结果", "代码评审"])
        add_actions("个人时间", ["刷技术社区", "学习新框架", "写个人项目"])

    if any(k in profile_blob for k in ["设计师", "UI", "视觉"]):
        add_actions("上午工作", ["改稿", "做设计评审", "对接需求"])
        add_actions("下午工作", ["整理设计规范", "输出高保真稿", "收集灵感"])
        add_actions("个人时间", ["看展", "整理作品集", "做灵感板"])
        add_actions("下班", ["去咖啡馆", "看展"])

    if any(k in profile_blob for k in ["学生", "硕士", "博士", "课题组"]):
        add_actions("上午工作", ["去实验室", "上课", "写论文"])
        add_actions("下午工作", ["做实验", "看文献", "组会"])
        add_actions("午饭", ["吃食堂", "和同学一起吃"])
        add_actions("下班", ["回宿舍", "去操场散步"])

    if any(k in profile_blob for k in ["新媒体", "运营", "内容创作"]):
        add_actions("上午工作", ["写文案", "策划选题", "看数据"])
        add_actions("下午工作", ["剪视频", "追热点", "做A/B测试"])
        add_actions("个人时间", ["刷平台热点", "发动态"])

    if "产品经理" in profile_blob:
        add_actions("上午工作", ["写PRD", "拉会对齐需求", "做竞品分析"])
        add_actions("下午工作", ["跟进研发进度", "梳理用户反馈", "版本评审"])
        add_actions("加班", ["赶版本", "补产品文档"])

    if any(k in profile_blob for k in ["夜跑", "健身", "拉伸"]):
        add_actions("个人时间", ["夜跑", "健身或拉伸"])

    if any(k in profile_blob for k in ["咖啡馆", "看展"]):
        add_actions("个人时间", ["去咖啡馆", "看展"])

    if any(k in profile_blob for k in ["外向", "社交"]):
        add_actions("下班", ["约朋友聚会", "参加线下活动"])
        add_actions("个人时间", ["和朋友线上聊天"])

    if any(k in profile_blob for k in ["内向", "独处", "理性"]):
        add_actions("个人时间", ["独处放空", "安静听音乐"])

    if "政策" in profile_blob or "公共事务" in profile_blob:
        add_actions("个人时间", ["关注城市新闻", "刷政策资讯"])

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

    # === 构建社交网络 ===
    social_net = build_social_network(agents)
    for a in agents:
        a["social_neighbors"] = social_net[a["id"]]


    schedules = {a["id"]: generate_schedule(a) for a in agents}
    schedule_map = build_schedule_map(schedules)
    timeline = build_master_timeline(schedules)
    base_actions = generate_actions()
    actions = {a["id"]: build_action_space_for_agent(a, base_actions) for a in agents}

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


# =========================================================
# 入口
# =========================================================
if __name__ == "__main__":
    run_simulation()
