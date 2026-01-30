import pandas as pd
import time
import random
import numpy as np
import re
import json
from collections import defaultdict
import os
import shutil
import matplotlib.pyplot as plt
import networkx as nx

from config import CONFIG
from environment import EnvironmentSystem
from llm_providers import call_llm
from memory_store import (
    append_agent_log,
    load_agent_actions,
    load_agent_locations,
    load_agent_location_action_bias,
    load_agent_memory,
    load_agent_schedule,
    load_recent_actions,
    load_recent_log_blocks,
    load_sim_state,
    reset_agent_memory,
    retrieve_relevant_memories,
    save_agent_actions,
    save_agent_location_action_bias,
    save_agent_locations,
    save_agent_memory,
    save_agent_schedule,
    save_sim_state,
    seed_vector_db_from_memory,
    vector_db_add_entry,
    VECTOR_DB_TOP_K,
    _format_memory_hint,
    _memory_action_bias,
)

# =========================================================
# Utils
# =========================================================
def _clear_dir(path):
    if not path or not os.path.exists(path):
        return
    for name in os.listdir(path):
        target = os.path.join(path, name)
        try:
            if os.path.islink(target) or os.path.isfile(target):
                os.remove(target)
            elif os.path.isdir(target):
                shutil.rmtree(target)
        except OSError:
            continue

def reset_simulation():
    memory_dir = CONFIG.get("memory_dir", "output/memory")
    log_dir = CONFIG.get("log_dir", "output/logs")
    _clear_dir(memory_dir)
    _clear_dir(log_dir)
    vector_db_path = CONFIG.get("vector_db_path")
    if vector_db_path and os.path.exists(vector_db_path):
        try:
            if os.path.isdir(vector_db_path):
                shutil.rmtree(vector_db_path)
            else:
                os.remove(vector_db_path)
        except OSError:
            pass
    for output_dir in ["output/state", "output/network"]:
        if output_dir not in (memory_dir, log_dir):
            _clear_dir(output_dir)

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
        sample_history = next(iter(state_history.values()), {})
        metrics = list(sample_history.keys())

    if not metrics:
        return

    cols = 3 if len(metrics) > 4 else 2
    rows = int(np.ceil(len(metrics) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 4.2, rows * 3.2), sharex=True)
    axes = np.array(axes).reshape(-1)

    steps = None
    for i, metric in enumerate(metrics):
        ax = axes[i]
        for agent_id, history in state_history.items():
            series = history.get(metric, [])
            if steps is None:
                steps = list(range(len(series)))
            label = agent_names.get(agent_id, str(agent_id))
            ax.plot(steps, series, label=label, linewidth=1.6)
        ax.set_title(metric)
        ax.set_ylim(0, 1)
        ax.grid(True, alpha=0.2)

    for j in range(len(metrics), len(axes)):
        axes[j].axis("off")

    axes[0].legend(loc="upper right", fontsize=8)
    fig.suptitle("Agent State Changes Over Time")
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    out_path = os.path.join(output_dir, "agent_state_over_time.png")
    plt.savefig(out_path, dpi=200)
    plt.close()

def save_state_history(state_history, output_dir="output/state"):
    os.makedirs(output_dir, exist_ok=True)
    rows = []
    for agent_id, history in state_history.items():
        for metric, series in history.items():
            for step, value in enumerate(series):
                rows.append({
                    "agent_id": agent_id,
                    "step": step,
                    "metric": metric,
                    "value": float(value),
                })
    if not rows:
        return
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(output_dir, "agent_state_history.csv"), index=False)


# =========================================================
# 参数
# =========================================================
AGENT_IDS = CONFIG["agent_ids"]   # 可扩展为 100
SIM_DAYS = CONFIG["sim_days"]
SECONDS_PER_DAY = CONFIG["seconds_per_day"]

CSV_PATH = CONFIG["csv_path"]
MD_PATH = CONFIG["md_path"]
STATEFUL = CONFIG["stateful"]
MAP_PATH = CONFIG.get("map_path", "citymap.md")
PRINT_AGENT_PROFILE = CONFIG.get("print_agent_profile", False)
BACKGROUND = CONFIG.get("background", "")

# =========================================================
# 政策事件
# =========================================================
POLICY_EVENTS = CONFIG["policy_events"]

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

def build_agent(agent_id, df, city_map=None):
    row = df[df["id"] == agent_id].iloc[0]
    text = parse_profile(load_profile_from_md(agent_id))
    agent = {
        "id": agent_id,
        **text,
        "gender": row.get("gender", ""),
        "hukou": row.get("hukou", ""),
        "residence": row.get("residence", ""),
        "state": {
            "emotion": float(row["emotion"]),
            "stress": float(row["stress"]),
            "econ_security": float(row["econ_security"]),
            "city_identity": float(row["city_identity"]),
            "policy_sensitivity": float(row.get("policy_sensitivity", 0.5)),
            "platform_dependence": float(row.get("platform_dependence", 0.5)),
            "risk_preference": float(row.get("risk_preference", 0.5)),
            "voice_propensity": float(row.get("voice_propensity", 0.5)),
            "mobility_intent": float(row.get("mobility_intent", 0.5)),
        },
        "memory": [],
        "social_neighbors": []
    }
    if city_map is None:
        city_map = load_city_map(MAP_PATH)
    init_agent_locations(agent, city_map)
    return agent

def print_agent_profiles(agent_ids):
    print("\n================= Agent Profiles =================")
    for agent_id in agent_ids:
        try:
            block = load_profile_from_md(agent_id)
        except ValueError as exc:
            print(f"⚠️ {exc}")
            continue
        print(block.strip())
        print()

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
# Map & Location
# =========================================================
def load_city_map(map_path):
    if not os.path.exists(map_path):
        return {}
    hubs = {}
    current_hub = None
    with open(map_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            hub_match = re.match(r"-\s*Hub:\s*(.+)", line)
            if hub_match:
                current_hub = hub_match.group(1).strip()
                hubs.setdefault(current_hub, [])
                continue
            nearby_match = re.match(r"-\s*Nearby:\s*(.+)", line)
            if nearby_match and current_hub:
                hubs[current_hub].append(nearby_match.group(1).strip())
    return hubs

def load_city_map_text(map_path):
    if not os.path.exists(map_path):
        return ""
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""

def _all_locations(city_map):
    locs = []
    for hub, nearby in city_map.items():
        locs.append(hub)
        locs.extend(nearby)
    return list(dict.fromkeys(locs))

def _pick_first_available(candidates, location_set):
    for c in candidates:
        if c in location_set:
            return c
    return None

def _infer_workplace(agent, location_set):
    profile_blob = " ".join([
        agent.get("job", ""),
        agent.get("personality", ""),
        agent.get("daily_life", ""),
        agent.get("values", "")
    ])
    if any(k in profile_blob for k in ["学生", "硕士", "博士", "学校", "上课", "老师", "教师", "教育"]):
        return _pick_first_available(
            ["Riverside Middle School", "Riverside Primary School", "Little River Daycare"],
            location_set
        )
    if any(k in profile_blob for k in ["医院", "医生", "护士", "医疗", "诊所"]):
        return _pick_first_available(
            ["Riverside Community Hospital", "Northside Family Clinic"],
            location_set
        )
    if any(k in profile_blob for k in ["研发", "工程", "技术", "程序", "互联网", "算法", "产品", "数据"]):
        return _pick_first_available(
            ["Hangzhou Tech Labs", "RnD Center", "Admin Office"],
            location_set
        )
    if any(k in profile_blob for k in ["银行", "金融", "证券", "财务"]):
        return _pick_first_available(
            ["Riverside Bank Branch"],
            location_set
        )
    if any(k in profile_blob for k in ["物流", "仓储", "配送", "快递"]):
        return _pick_first_available(
            ["Riverside Logistics", "Warehouse A", "Warehouse B"],
            location_set
        )
    if any(k in profile_blob for k in ["设计", "工作室"]):
        return _pick_first_available(
            ["Willow Design Studio"],
            location_set
        )
    if any(k in profile_blob for k in ["警察", "公安", "消防"]):
        return _pick_first_available(
            ["Riverside Police Station", "Riverside Fire Station"],
            location_set
        )
    return _pick_first_available(
        ["C-01 (Village Center)", "Riverside Night Market", "Market St"],
        location_set
    )

def _infer_home(agent, location_set):
    candidates = ["Central Block", "North Block", "South Block"]
    home = _pick_first_available(candidates, location_set)
    if home:
        return home
    return random.choice(list(location_set)) if location_set else "Home"

def assign_agent_locations(agent, city_map):
    location_set = set(_all_locations(city_map))
    home = _infer_home(agent, location_set)
    workplace = _infer_workplace(agent, location_set) or home
    return {
        "home": home,
        "workplace": workplace,
        "current": home,
    }

def init_agent_locations(agent, city_map):
    cached_locations = load_agent_locations(agent["id"]) if STATEFUL else {}
    if cached_locations:
        agent["locations"] = cached_locations
        agent["locations"].setdefault("current", agent["locations"].get("home", "Home"))
        return agent["locations"]
    agent["locations"] = assign_agent_locations(agent, city_map)
    if STATEFUL:
        save_agent_locations(agent["id"], agent["locations"])
    return agent["locations"]

def resolve_location(agent, activity, time_str, city_map):
    location_set = set(_all_locations(city_map))
    home = agent["locations"].get("home", "Home")
    work = agent["locations"].get("workplace", home)
    current = agent["locations"].get("current", home)

    def pick_any(candidates):
        choice = _pick_first_available(candidates, location_set)
        return choice or home

    def _time_to_minutes(t):
        if not re.match(r"^\d{2}:\d{2}$", str(t)):
            return None
        hh, mm = t.split(":")
        return int(hh) * 60 + int(mm)

    def _profile_flags(a):
        profile_blob = " ".join([
            a.get("job", ""),
            a.get("personality", ""),
            a.get("daily_life", ""),
            a.get("values", ""),
            a.get("work_style", ""),
        ])
        is_student = any(k in profile_blob for k in ["学生", "硕士", "博士", "课题组", "上课", "学习"])
        is_retired = any(k in profile_blob for k in ["退休", "无业", "待业", "失业", "家庭主妇", "家庭主夫", "已退休"])
        late_schedule = any(k in profile_blob for k in ["夜间活跃", "晚睡", "作息偏晚"])
        overtime = "加班" in a.get("work_style", "")
        return is_student, is_retired, late_schedule, overtime

    def _public_pool():
        keywords = ["Park", "Cinema", "Market", "Library", "Community", "Center", "Riverwalk",
                    "Grove", "Playground", "Fitness", "Picnic", "Pocket", "Night Market"]
        pool = [loc for loc in location_set if any(k in loc for k in keywords)]
        if not pool:
            pool = [loc for loc in location_set if loc not in {home, work}]
        return pool

    def _time_bias():
        minutes = _time_to_minutes(time_str)
        is_student, is_retired, late_schedule, overtime = _profile_flags(agent)
        if minutes is None:
            return {"home": 0.4, "work": 0.3, "public": 0.3, "current": 0.2}
        if late_schedule:
            minutes = (minutes - 60) % (24 * 60)

        if minutes >= 22 * 60 or minutes < 6 * 60:
            base = {"home": 0.75, "work": 0.05, "public": 0.2, "current": 0.25}
        elif minutes < 9 * 60:
            base = {"home": 0.45, "work": 0.2, "public": 0.35, "current": 0.25}
        elif minutes < 17 * 60 + 30:
            if is_retired:
                base = {"home": 0.45, "work": 0.15, "public": 0.4, "current": 0.25}
            elif is_student:
                base = {"home": 0.2, "work": 0.55, "public": 0.25, "current": 0.2}
            else:
                base = {"home": 0.2, "work": 0.6, "public": 0.2, "current": 0.2}
        else:
            base = {"home": 0.55, "work": 0.1, "public": 0.35, "current": 0.25}
            if overtime:
                base["work"] += 0.1
                base["home"] -= 0.05
        s = agent.get("state", {})
        mobility = s.get("mobility_intent", 0.5)
        stress = s.get("stress", 0.5)
        if mobility > 0.65:
            base["public"] += 0.1
            base["home"] -= 0.05
        if mobility < 0.35:
            base["home"] += 0.1
            base["public"] -= 0.05
        if stress > 0.7:
            base["home"] += 0.08
            base["public"] -= 0.05
        return base

    def _weighted_pick(candidate_weights):
        if not candidate_weights:
            return home
        items = list(candidate_weights.items())
        locs, weights = zip(*items)
        return random.choices(locs, weights=weights, k=1)[0]

    def _add_weight(weights, loc, w):
        if not loc or w <= 0:
            return
        if loc not in location_set:
            return
        weights[loc] = weights.get(loc, 0) + w

    if any(k in activity for k in ["通勤"]):
        return pick_any(["Riverside Bus Station", "Riverside Ave", "Bridge Rd", "Market St"])

    activity_candidates = []
    if any(k in activity for k in ["工作", "上班", "加班"]):
        activity_candidates.append(work)
    if any(k in activity for k in ["学习", "上课", "实验"]):
        activity_candidates += ["Riverside Middle School", "Riverside Primary School", "Hangzhou Tech Labs"]
    if any(k in activity for k in ["看病", "医院", "诊所"]):
        activity_candidates += ["Riverside Community Hospital", "Northside Family Clinic", "Willow Pharmacy"]
    if any(k in activity for k in ["晨练", "散步", "运动", "健身", "锻炼"]):
        activity_candidates += ["Riverside Park", "Willow Grove Park", "Fitness Area", "Playground"]
    if any(k in activity for k in ["买菜", "购物", "市场"]):
        activity_candidates += ["Market St", "Riverside Supermart", "Riverside Night Market", "Corner Mart"]
    if any(k in activity for k in ["电影", "娱乐", "休闲"]):
        activity_candidates += ["Riverside Cinema", "Riverside Park"]

    weights = {}
    bias = _time_bias()
    _add_weight(weights, home, bias["home"])
    _add_weight(weights, work, bias["work"])
    _add_weight(weights, current, bias["current"])

    public_pool = _public_pool()
    if public_pool:
        for loc in random.sample(public_pool, k=min(2, len(public_pool))):
            _add_weight(weights, loc, bias["public"])

    for loc in activity_candidates:
        _add_weight(weights, loc, 1.2)

    if any(k in activity for k in ["午饭", "晚饭", "吃饭"]):
        if time_str <= "10:30":
            _add_weight(weights, home, 0.6)
        _add_weight(weights, "Market St", 0.8)
        _add_weight(weights, "Riverside Night Market", 0.8)
        _add_weight(weights, "Riverside Supermart", 0.6)

    if any(k in activity for k in ["吃早饭", "睡前", "午休", "休息", "个人时间"]):
        _add_weight(weights, home, 0.8)

    choice = _weighted_pick(weights)
    return choice or home

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
    memory_hits = retrieve_relevant_memories(agent, "日程安排", max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    prompt = f"""
你是城市生活模拟器的日程生成器。请基于角色资料生成一天日程安排。
角色资料：
{profile_text}
可参考的近期记忆：{memory_hint}
要求：
1) 输出 JSON 数组，每项为 ["HH:MM","活动"] 或 {{"time":"HH:MM","activity":"活动"}}。
2) 6-10 项，时间升序覆盖早中晚，活动为中文短语。
3) 若角色为退休/无业/待业/失业/家庭主妇/家庭主夫/已退休，不出现“工作/通勤/上班/加班”等活动。
4) 若角色为学生，优先出现“上课/学习/实验”等活动；若作息偏晚，适度延后。
5) 仅输出 JSON，不要其他文字。
"""
    response = call_llm(prompt, task="schedule", agent_id=agent["id"])
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

def _parse_location_bias(text, activities):
    json_blob = _extract_json_block(text)
    if not json_blob:
        return {}
    try:
        raw = json.loads(json_blob)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    bias_map = {}
    for activity in activities:
        item = raw.get(activity, {})
        if not isinstance(item, dict):
            continue
        prefer = item.get("prefer", [])
        avoid = item.get("avoid", [])
        if not isinstance(prefer, list):
            prefer = []
        if not isinstance(avoid, list):
            avoid = []
        cleaned_prefer = [str(a).strip() for a in prefer if str(a).strip()]
        cleaned_avoid = [str(a).strip() for a in avoid if str(a).strip()]
        if cleaned_prefer or cleaned_avoid:
            bias_map[activity] = {
                "prefer": cleaned_prefer,
                "avoid": cleaned_avoid,
            }
    return bias_map

def _parse_policy_effect(text):
    json_blob = _extract_json_block(text)
    if not json_blob:
        return {}
    try:
        raw = json.loads(json_blob)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    allowed = {
        "emotion",
        "stress",
        "econ_security",
        "city_identity",
        "policy_sensitivity",
        "platform_dependence",
        "risk_preference",
        "voice_propensity",
        "mobility_intent",
    }
    effect = {}
    for k in allowed:
        if k in raw:
            try:
                effect[k] = float(raw[k])
            except (TypeError, ValueError):
                continue
    return effect

def _llm_generate_actions(agent, activities, seed_actions=None):
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    memory_context = " ".join(activities)
    memory_hits = retrieve_relevant_memories(agent, memory_context, max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    seed_text = ""
    if seed_actions:
        seed_text = f"\n已有动作参考（可改写、扩展、去重）：\n{json.dumps(seed_actions, ensure_ascii=False, indent=2)}"
    prompt = f"""
你是城市生活模拟器的动作生成器。请基于角色资料，为每个活动生成具体动作。
角色资料：
{profile_text}
活动列表：{", ".join(activities)}
可参考的近期记忆：{memory_hint}
要求：
1) 每个活动给出 5-10 个动作，中文短语。
2) 动作要符合角色职业、性格与生活习惯。
3) 仅输出 JSON 对象，键为活动名，值为动作列表，不要输出其他文字。
{seed_text}
"""
    response = call_llm(prompt, task="actions", agent_id=agent["id"])
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
        retry_response = call_llm(retry_prompt, task="actions", agent_id=agent["id"])
        retry_actions = _parse_action_space(retry_response, missing)
        for activity, acts in retry_actions.items():
            action_space[activity] = acts
    return action_space

def _llm_generate_location_bias(agent, location, city_map_text, action_space):
    activities = list(action_space.keys())
    if not activities:
        return {}
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    actions_text = json.dumps(action_space, ensure_ascii=False, indent=2)
    prompt = f"""
你是城市生活模拟器的“地点动作偏好”生成器。请基于角色资料、地点与城市地图，
为每个活动在该地点给出“偏好动作/避免动作”。

角色资料：
{profile_text}

地点：{location}

城市地图（完整）：
{city_map_text}

活动与可选动作（仅可从下列动作中选择）：
{actions_text}

要求：
1) 仅输出 JSON 对象，键为活动名，值为对象：{{"prefer":[...], "avoid":[...]}}。
2) prefer/avoid 中的动作必须来自给定动作列表，使用完全一致的动作文本。
3) 每个活动 0-5 个 prefer，0-5 个 avoid，允许为空数组。
4) 不要输出其他文字。
"""
    response = call_llm(prompt, task="location_actions", agent_id=agent["id"])
    return _parse_location_bias(response, activities)

def get_location_action_bias(agent, location, city_map_text, action_space):
    if not city_map_text:
        return {}
    bias_cache = agent.setdefault("location_action_bias", {})
    cached = bias_cache.get(location)
    if isinstance(cached, dict):
        return cached
    bias = _llm_generate_location_bias(agent, location, city_map_text, action_space)
    bias_cache[location] = bias
    save_agent_location_action_bias(agent["id"], bias_cache)
    return bias

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

def choose_action(agent, activity, action_space, context=None, location_bias=None):
    options = action_space.get(activity, [])

    # === 关键兜底：防止空动作空间 ===
    #if not options:
    #    return "继续当前活动"

    if not options:
        return fallback_action(activity)

    weights = []
    s = agent["state"]
    recent_actions = []
    memory_hits = []
    if STATEFUL:
        recent_actions = load_recent_actions(agent["id"], max_items=6)
    if context or activity:
        query = context if context else activity
        memory_hits = retrieve_relevant_memories(agent, query, max_items=2)

    bias = (location_bias or {}).get(activity, {})
    prefer_set = set(bias.get("prefer", [])) if isinstance(bias, dict) else set()
    avoid_set = set(bias.get("avoid", [])) if isinstance(bias, dict) else set()

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

        # 历史行动偏好：更可能重复近期做过的行为
        if act in recent_actions:
            w += 0.4
        w += _memory_action_bias(act, memory_hits)

        # 地点偏好：同一地点的行为倾向
        if act in prefer_set:
            w += 1.0
        if act in avoid_set:
            w -= 0.6

        weights.append(max(w, 0.01))  # 防止权重为 0

    return random.choices(options, weights=weights, k=1)[0]

# =========================================================
# Policy effect inference
# =========================================================
def infer_event_effect(agent, event_desc, event_type="event"):
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    prompt = f"""
你是城市生活模拟器的影响评估器。请基于事件描述与角色资料，推断该事件对角色状态的短期影响。
角色资料：
{profile_text}
事件类型：{event_type}
事件描述：{event_desc}
要求：
1) 仅输出 JSON 对象，键为 emotion、stress、econ_security、city_identity、policy_sensitivity、
   platform_dependence、risk_preference、voice_propensity、mobility_intent 的子集。
2) 值为 -0.2 到 0.2 的小幅浮点数，正值为提升，负值为下降。
3) 不要输出其他文字。
"""
    response = call_llm(prompt, task="event_effect", agent_id=agent["id"])
    effect = _parse_policy_effect(response)
    if not effect:
        return {}
    for k in effect:
        effect[k] = float(np.clip(effect[k], -0.2, 0.2))
    return effect

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

def perception(agent, time_str, social_context, env_context, policy_event):
    prompt = f"""
你是{agent['name']}。
现在是 {time_str}。
你感知到的社交环境是：{social_context}
自然与社会环境：{env_context if env_context else "无特殊变化"}
政策环境：{policy_event if policy_event else "无特殊变化"}

请描述你此刻对环境、他人和制度的感知。（1-2句）
"""
    return call_llm(prompt, task="perception", agent_id=agent["id"])

def planning(agent, perception_text):
    memory_hits = retrieve_relevant_memories(agent, perception_text, max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    history_hint = "暂无历史"
    if STATEFUL:
        history_blocks = load_recent_log_blocks(agent["id"], max_blocks=2, max_chars=380)
        if history_blocks:
            history_hint = "\n---\n".join(history_blocks)
    prompt = f"""
你是{agent['name']}。
你的感知是：{perception_text}
你的近期经验：{memory_hint}
你的近期历史片段：
{history_hint}

你此刻的短期计划是什么？（1-2句）
"""
    return call_llm(prompt, task="planning", agent_id=agent["id"])

def reflection(agent, outcome):
    memory_hits = retrieve_relevant_memories(agent, outcome, max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    prompt = f"""
你是{agent['name']}。
刚刚发生的事情是：{outcome}
你的相关记忆：{memory_hint}

你对此有何反思或情绪变化？（1-2句）
"""
    return call_llm(prompt, task="reflection", agent_id=agent["id"])

def _parse_interview(text, questions):
    json_blob = _extract_json_array_block(text)
    if not json_blob:
        return []
    try:
        raw = json.loads(json_blob)
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    parsed = []
    for i, item in enumerate(raw):
        if isinstance(item, (list, tuple)) and len(item) == 2:
            q, a = item
        elif isinstance(item, dict):
            q = item.get("question")
            a = item.get("answer")
        else:
            continue
        q = str(q).strip() if q else ""
        a = str(a).strip() if a else ""
        if not q:
            q = questions[i] if i < len(questions) else ""
        if q and a:
            parsed.append({"question": q, "answer": a})
    return parsed

def interview_agent(agent, questions, context=None, max_questions=6):
    if not questions:
        return []
    if isinstance(questions, str):
        questions = [q.strip() for q in questions.splitlines() if q.strip()]
    else:
        questions = [str(q).strip() for q in questions if str(q).strip()]
    if not questions:
        return []
    questions = questions[:max_questions]

    memory_hits = retrieve_relevant_memories(agent, "访谈", max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    context_text = context if context else "无"
    question_text = "\n".join(f"- {q}" for q in questions)
    prompt = f"""
你是{agent['name']}。
这是一次访谈，回答要真实且基于角色经历。
背景：{context_text}
你的近期经验：{memory_hint}

请逐题回答以下问题，每题1-3句。
要求：
1) 输出 JSON 数组，每项为 {{"question":"...","answer":"..."}} 或 ["question","answer"]。
2) 仅输出 JSON，不要其他文字。
问题列表：
{question_text}
"""
    response = call_llm(prompt, task="interview", agent_id=agent["id"])
    parsed = _parse_interview(response, questions)
    if parsed:
        return parsed
    fallback = response.strip()
    if not fallback:
        return []
    return [{"question": q, "answer": fallback} for q in questions]

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
    s.setdefault("policy_sensitivity", 0.5)
    s.setdefault("platform_dependence", 0.5)
    s.setdefault("risk_preference", 0.5)
    s.setdefault("voice_propensity", 0.5)
    s.setdefault("mobility_intent", 0.5)

    s["emotion"] += 0.05 * s["econ_security"] - 0.07 * s["stress"] + random.uniform(-0.02, 0.02)
    s["stress"] += 0.03 * (1 - s["econ_security"]) + random.uniform(-0.02, 0.03)
    s["econ_security"] += 0.02 * (1 - s["stress"]) - 0.015 * s["platform_dependence"] + random.uniform(-0.015, 0.02)
    s["city_identity"] += 0.03 * (s["emotion"] - 0.5) - 0.02 * s["mobility_intent"] + random.uniform(-0.01, 0.01)
    s["policy_sensitivity"] += 0.02 * (s["stress"] - 0.5) + random.uniform(-0.01, 0.01)
    s["platform_dependence"] += 0.02 * (1 - s["econ_security"]) + random.uniform(-0.01, 0.01)
    s["risk_preference"] += 0.02 * (s["emotion"] - s["stress"]) + random.uniform(-0.01, 0.01)
    s["voice_propensity"] += 0.02 * (s["city_identity"] - 0.5) + 0.01 * (s["emotion"] - 0.5) + random.uniform(-0.01, 0.01)
    s["mobility_intent"] += 0.03 * (s["stress"] - s["city_identity"]) + random.uniform(-0.01, 0.01)

    for k in s:
        s[k] = float(np.clip(s[k], 0, 1))

# =========================================================
# B. 长期记忆
# =========================================================
def daily_summary(agent, logs, day=None):
    prompt = f"""
你是{agent['name']}。
这是你今天经历的关键片段：
{logs}

请总结今天最重要的一条经验或感受。
"""
    memory = call_llm(prompt, task="summary", agent_id=agent["id"])
    agent["memory"].append(memory)
    save_agent_memory(agent)
    vector_db_add_entry(agent["id"], "memory", memory, sim_day=day, sim_time="end_of_day")
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
    city_map = load_city_map(MAP_PATH)
    city_map_text = load_city_map_text(MAP_PATH)
    agents = [build_agent(i, df, city_map=city_map) for i in AGENT_IDS]
    if PRINT_AGENT_PROFILE:
        print_agent_profiles([a["id"] for a in agents])
    start_day = 1
    if STATEFUL:
        # Resume day count for persistent simulations.
        sim_state = load_sim_state()
        last_day = sim_state.get("last_day", 0)
        if isinstance(last_day, int) and last_day >= 0:
            start_day = last_day + 1
    if STATEFUL:
        for agent in agents:
            agent["memory"] = load_agent_memory(agent["id"])
            seed_vector_db_from_memory(agent)
    else:
        for agent in agents:
            agent["memory"] = []
            reset_agent_memory(agent["id"])
    agents_by_id = {a["id"]: a for a in agents}
    agent_names = {a["id"]: a.get("name", str(a["id"])) for a in agents}
    state_metrics = list(agents[0]["state"].keys()) if agents else []
    state_history = {
        a["id"]: {
            metric: [] for metric in state_metrics
        }
        for a in agents
    }
    env_system = EnvironmentSystem(CONFIG.get("environment", {}), llm_fn=call_llm)
    background_text = str(BACKGROUND).strip()

    # === 构建社交网络 ===
    social_net = build_social_network(agents)
    for a in agents:
        a["social_neighbors"] = social_net[a["id"]]

    for a in agents:
        if not a.get("locations"):
            init_agent_locations(a, city_map)
        a["location_action_bias"] = load_agent_location_action_bias(a["id"])
        locs = a.get("locations", {})
        init_loc_line = (
            f"[InitLocation] {a.get('name', a['id'])}: "
            f"home={locs.get('home', 'Home')} "
            f"work={locs.get('workplace', locs.get('home', 'Home'))} "
            f"current={locs.get('current', locs.get('home', 'Home'))}\n"
        )
        print(init_loc_line.strip())
        append_agent_log(a, init_loc_line)

    schedules = {}
    actions = {}
    for a in agents:
        agent_id = a["id"]
        cached_schedule = load_agent_schedule(agent_id)
        if cached_schedule:
            schedules[agent_id] = cached_schedule
        else:
            # Generate schedule once per agent unless cache exists.
            schedules[agent_id] = generate_schedule(a)
            save_agent_schedule(agent_id, schedules[agent_id])

        cached_actions = load_agent_actions(agent_id)
        if cached_actions:
            actions[agent_id] = cached_actions
        else:
            # Action space is expensive; cache for reuse across runs.
            base_actions = generate_actions(a, schedules[agent_id])
            actions[agent_id] = build_action_space_for_agent(a, base_actions)
            save_agent_actions(agent_id, actions[agent_id])

    schedule_map = build_schedule_map(schedules)
    timeline = build_master_timeline(schedules)

    validate_action_space(schedules, actions)

    sleep_step = SECONDS_PER_DAY / (SIM_DAYS * max(len(timeline), 1))

    for day in range(start_day, start_day + SIM_DAYS):
        print(f"\n================= Day {day} =================")
        daily_logs = defaultdict(str)

        day_header = f"\n================= Day {day} =================\n"
        for agent in agents:
            daily_logs[agent["id"]] += day_header
            append_agent_log(agent, day_header)
            
        for time_str in timeline:
            policy = next((p for p in POLICY_EVENTS if p["day"] == day and p["time"] == time_str), None)
            env_system.tick(day, time_str, agents)
            env_events = env_system.get_events()
            env_context = env_system.get_context_text()
            if background_text:
                env_context = f"背景：{background_text} 当前环境事件：{env_context}"

            for agent in agents:
                #act = random.choice(actions.get(activity, ["继续当前活动"]))
                activity = schedule_map[agent["id"]].get(time_str, "个人时间")
                location = resolve_location(agent, activity, time_str, city_map)
                agent["locations"]["current"] = location
                social_context = get_social_context(agent, agents_by_id)

                policy_desc = None
                if policy:
                    policy_desc = policy.get("description") or policy.get("name")
                # Core cognition loop: perceive -> plan -> act -> reflect.
                perc = perception(agent, time_str, social_context, env_context, policy_desc if policy else None)
                plan = planning(agent, perc)
                location_bias = get_location_action_bias(
                    agent,
                    location,
                    city_map_text,
                    actions[agent["id"]],
                )
                act = choose_action(
                    agent,
                    activity,
                    actions[agent["id"]],
                    context=f"{activity} {perc}",
                    location_bias=location_bias,
                )
                outcome = f"在【{activity}】中执行了【{act}】"
                refl = reflection(agent, outcome)

                if env_events:
                    for ev in env_events:
                        inferred = infer_event_effect(agent, ev.get("description", ev.get("name", "")), ev.get("type", "event"))
                        for k, v in inferred.items():
                            agent["state"][k] += v

                if policy:
                    inferred = infer_event_effect(agent, policy_desc, "policy")
                    for k, v in inferred.items():
                        agent["state"][k] += v

                social_influence(agent, agents_by_id)
                update_state(agent)
                for metric in state_history[agent["id"]]:
                    state_history[agent["id"]][metric].append(agent["state"][metric])

                log = f"""
[{agent['name']} @ {time_str}]
Location: {location}
Environment: {env_context}
Perception: {perc}
Plan: {plan}
Action: {act}
Outcome: {outcome}
Reflection: {refl}
"""
                print(log)
                daily_logs[agent["id"]] += log
                append_agent_log(agent, log)
                vector_db_add_entry(agent["id"], "log", log, sim_day=day, sim_time=time_str)
                vector_db_add_entry(agent["id"], "plan", plan, sim_day=day, sim_time=time_str)
                vector_db_add_entry(agent["id"], "reflection", refl, sim_day=day, sim_time=time_str)
                vector_db_add_entry(agent["id"], "action", outcome, sim_day=day, sim_time=time_str)

            time.sleep(sleep_step)

        for agent in agents:
            mem = daily_summary(agent, daily_logs[agent["id"]], day=day)
            print(f"🧠 {agent['name']} 的今日长期记忆：{mem}")
        if STATEFUL:
            save_sim_state({"last_day": day})

    print("\n✅ 模拟完成")
    visualize_social_network(agents)
    save_state_history(state_history)
    visualize_agent_state_changes(state_history, agent_names, metrics=state_metrics)


# =========================================================
# 入口
# =========================================================
def _parse_question_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).splitlines() if v.strip()]

def _cli_interview_agent(agent_id, questions, context=None):
    df = pd.read_csv(CSV_PATH)
    city_map = load_city_map(MAP_PATH)
    agent = build_agent(agent_id, df, city_map=city_map)
    if STATEFUL:
        agent["memory"] = load_agent_memory(agent["id"])
        seed_vector_db_from_memory(agent)
    else:
        agent["memory"] = []
    answers = interview_agent(agent, questions, context=context)
    print(json.dumps(answers, ensure_ascii=False, indent=2))

def _build_arg_parser():
    import argparse
    parser = argparse.ArgumentParser(description="GAWorld simulator")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Run the full simulation")
    subparsers.add_parser("reset", help="Reset simulation memory/logs/cache")

    interview = subparsers.add_parser("interview", help="Interview a specific agent by ID")
    interview.add_argument("--agent-id", type=int, required=True, help="Agent ID to interview")
    interview.add_argument(
        "--question",
        action="append",
        dest="questions",
        help="Interview question (can be used multiple times)",
    )
    interview.add_argument(
        "--questions-file",
        help="Path to a UTF-8 text file with one question per line",
    )
    interview.add_argument(
        "--context",
        default=None,
        help="Optional background context for the interview",
    )
    return parser

def _load_questions_from_file(path):
    if not path:
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except OSError:
        return []

def _main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.command == "reset":
        reset_simulation()
        print("✅ 已重置模拟：清空记忆、日志与缓存。")
        return

    if args.command == "interview":
        questions = []
        questions.extend(_parse_question_list(args.questions))
        questions.extend(_load_questions_from_file(args.questions_file))
        if not questions:
            parser.error("Provide at least one --question or a --questions-file.")
        _cli_interview_agent(args.agent_id, questions, context=args.context)
        return

    run_simulation()

if __name__ == "__main__":
    _main()
