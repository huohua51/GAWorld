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

from config import CONFIG
from environment import EnvironmentSystem

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
# LLM backends
# =========================================================
def _extract_openai_response_text(response_json):
    if "output_text" in response_json and response_json["output_text"]:
        return str(response_json["output_text"]).strip()
    output = response_json.get("output", [])
    chunks = []
    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text"):
                text = content.get("text", "")
                if text:
                    chunks.append(text)
    return "".join(chunks).strip()

class OllamaProvider:
    def __init__(self, url, model, timeout=120):
        self.url = url
        self.model = model
        self.timeout = timeout

    def call(self, prompt):
        r = requests.post(
            self.url,
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=self.timeout
        )
        r.raise_for_status()
        data = r.json()
        return str(data.get("response", "")).strip()

class OpenAIProvider:
    def __init__(self, base_url, model, api_key=None, api_key_env="OPENAI_API_KEY", timeout=120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.timeout = timeout

    def call(self, prompt):
        api_key = self.api_key or os.environ.get(self.api_key_env)
        if not api_key:
            raise ValueError(f"Missing OpenAI API key in env var: {self.api_key_env}")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": prompt,
        }
        r = requests.post(
            f"{self.base_url}/responses",
            headers=headers,
            json=payload,
            timeout=self.timeout
        )
        r.raise_for_status()
        data = r.json()
        return _extract_openai_response_text(data)

class AnthropicProvider:
    def __init__(
        self,
        base_url,
        model,
        api_key=None,
        api_key_env="ANTHROPIC_API_KEY",
        anthropic_version="2023-06-01",
        timeout=120,
        max_tokens=512,
        system=None,
        beta=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.anthropic_version = anthropic_version
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.system = system
        self.beta = beta

    def call(self, prompt):
        api_key = self.api_key or os.environ.get(self.api_key_env)
        if not api_key:
            raise ValueError(f"Missing Anthropic API key in env var: {self.api_key_env}")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json",
        }
        if self.beta:
            headers["anthropic-beta"] = self.beta
        payload = {
            "model": self.model,
            "max_tokens": int(self.max_tokens),
            "messages": [{"role": "user", "content": str(prompt)}],
        }
        if self.system:
            payload["system"] = self.system
        r = requests.post(
            f"{self.base_url}/v1/messages",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        chunks = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    chunks.append(text)
        return "".join(chunks).strip()

class LLMRouter:
    def __init__(self, config):
        llm_cfg = config.get("llm") or {}
        if not llm_cfg:
            llm_cfg = {
                "providers": {
                    "ollama_local": {
                        "type": "ollama",
                        "url": config.get("ollama_url"),
                        "model": config.get("model_name"),
                        "timeout": config.get("llm_timeout", 120),
                    },
                },
                "routing": {"default": "ollama_local"},
            }
        self.providers = self._build_providers(llm_cfg.get("providers", {}))
        self.routing = llm_cfg.get("routing", {})

    def _build_providers(self, providers_cfg):
        providers = {}
        for name, cfg in providers_cfg.items():
            p_type = (cfg.get("type") or "ollama").lower()
            if p_type == "ollama":
                providers[name] = OllamaProvider(
                    cfg["url"],
                    cfg["model"],
                    timeout=cfg.get("timeout", 120),
                )
            elif p_type == "openai":
                providers[name] = OpenAIProvider(
                    cfg.get("base_url", "https://api.openai.com/v1"),
                    cfg["model"],
                    api_key=cfg.get("api_key"),
                    api_key_env=cfg.get("api_key_env", "OPENAI_API_KEY"),
                    timeout=cfg.get("timeout", 120),
                )
            elif p_type in ("claude", "anthropic"):
                providers[name] = AnthropicProvider(
                    cfg.get("base_url", "https://api.anthropic.com"),
                    cfg["model"],
                    api_key=cfg.get("api_key") or cfg.get("ANTHROPIC_AUTH_TOKEN"),
                    api_key_env=cfg.get("api_key_env", "ANTHROPIC_API_KEY"),
                    anthropic_version=cfg.get("anthropic_version", "2023-06-01"),
                    timeout=cfg.get("timeout", 120),
                    max_tokens=cfg.get("max_tokens", 512),
                    system=cfg.get("system"),
                    beta=cfg.get("anthropic_beta"),
                )
            else:
                print(f"⚠️ 跳过不支持的 LLM provider 类型: {name} ({p_type})")
                continue
        if not providers:
            raise ValueError("No LLM providers configured.")
        return providers

    def _select_provider(self, task=None, agent_id=None):
        tasks = self.routing.get("tasks", {})
        if task and task in tasks:
            return tasks[task]
        agents = self.routing.get("agents", {})
        if agent_id is not None and str(agent_id) in agents:
            return agents[str(agent_id)]
        return self.routing.get("default") or next(iter(self.providers))

    def call(self, prompt, task=None, agent_id=None):
        provider_name = self._select_provider(task=task, agent_id=agent_id)
        if provider_name not in self.providers:
            raise ValueError(f"Provider '{provider_name}' not found in config.")
        return self.providers[provider_name].call(prompt)

LLM_ROUTER = LLMRouter(CONFIG)

def call_llm(prompt, task=None, agent_id=None):
    return LLM_ROUTER.call(prompt, task=task, agent_id=agent_id)

# =========================================================
# 参数
# =========================================================
AGENT_IDS = CONFIG["agent_ids"]   # 可扩展为 100
SIM_DAYS = CONFIG["sim_days"]
SECONDS_PER_DAY = CONFIG["seconds_per_day"]

CSV_PATH = CONFIG["csv_path"]
MD_PATH = CONFIG["md_path"]
STATEFUL = CONFIG["stateful"]
MEMORY_DIR = CONFIG["memory_dir"]
LOG_DIR = CONFIG["log_dir"]
MAP_PATH = CONFIG.get("map_path", "citymap.md")
PRINT_AGENT_PROFILE = CONFIG.get("print_agent_profile", False)

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

def build_agent(agent_id, df):
    row = df[df["id"] == agent_id].iloc[0]
    text = parse_profile(load_profile_from_md(agent_id))
    return {
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
# Memory & Logs
# =========================================================
def _memory_path(agent_id):
    return os.path.join(MEMORY_DIR, f"agent_{agent_id}.json")

def _schedule_path(agent_id):
    return os.path.join(MEMORY_DIR, f"agent_{agent_id}_schedule.json")

def _actions_path(agent_id):
    return os.path.join(MEMORY_DIR, f"agent_{agent_id}_actions.json")

def _location_path(agent_id):
    return os.path.join(MEMORY_DIR, f"agent_{agent_id}_locations.json")

def _log_path(agent_id):
    return os.path.join(LOG_DIR, f"agent_{agent_id}.log")

def _sim_state_path():
    return os.path.join(MEMORY_DIR, "sim_state.json")

def load_agent_memory(agent_id):
    path = _memory_path(agent_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []

def save_agent_memory(agent):
    os.makedirs(MEMORY_DIR, exist_ok=True)
    with open(_memory_path(agent["id"]), "w", encoding="utf-8") as f:
        json.dump(agent["memory"], f, ensure_ascii=False, indent=2)

def load_agent_schedule(agent_id):
    path = _schedule_path(agent_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    cleaned = []
    for item in data:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            time_str, activity = item
        elif isinstance(item, dict) and "time" in item and "activity" in item:
            time_str, activity = item["time"], item["activity"]
        else:
            continue
        time_str = str(time_str).strip()
        activity = str(activity).strip()
        if re.match(r"^\d{2}:\d{2}$", time_str) and activity:
            cleaned.append((time_str, activity))
    return cleaned

def save_agent_schedule(agent_id, schedule):
    os.makedirs(MEMORY_DIR, exist_ok=True)
    payload = []
    for time_str, activity in schedule:
        payload.append({"time": time_str, "activity": activity})
    with open(_schedule_path(agent_id), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def load_agent_actions(agent_id):
    path = _actions_path(agent_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    cleaned = {}
    for k, v in data.items():
        if isinstance(v, list):
            cleaned[k] = [str(a).strip() for a in v if str(a).strip()]
    return cleaned

def save_agent_actions(agent_id, action_space):
    os.makedirs(MEMORY_DIR, exist_ok=True)
    with open(_actions_path(agent_id), "w", encoding="utf-8") as f:
        json.dump(action_space, f, ensure_ascii=False, indent=2)

def load_agent_locations(agent_id):
    path = _location_path(agent_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}

def save_agent_locations(agent_id, locations):
    os.makedirs(MEMORY_DIR, exist_ok=True)
    with open(_location_path(agent_id), "w", encoding="utf-8") as f:
        json.dump(locations, f, ensure_ascii=False, indent=2)

def reset_agent_memory(agent_id):
    os.makedirs(MEMORY_DIR, exist_ok=True)
    with open(_memory_path(agent_id), "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)

def append_agent_log(agent, text):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(_log_path(agent["id"]), "a", encoding="utf-8") as f:
        f.write(text)

def load_sim_state():
    path = _sim_state_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}

def save_sim_state(state):
    os.makedirs(MEMORY_DIR, exist_ok=True)
    with open(_sim_state_path(), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def _split_log_blocks(log_text):
    if not log_text:
        return []
    blocks = []
    current = []
    for line in log_text.splitlines():
        if line.startswith("[") and current:
            blocks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [b for b in blocks if b]

def load_recent_log_blocks(agent_id, max_blocks=2, max_chars=500):
    path = _log_path(agent_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    blocks = _split_log_blocks(text)
    if not blocks:
        return []
    tail = blocks[-max_blocks:]
    trimmed = []
    for block in tail:
        if len(block) > max_chars:
            trimmed.append(block[-max_chars:])
        else:
            trimmed.append(block)
    return trimmed

def load_recent_actions(agent_id, max_items=6):
    path = _log_path(agent_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    actions = []
    for line in text.splitlines():
        if line.startswith("Action:"):
            action = line.split("Action:", 1)[-1].strip()
            if action:
                actions.append(action)
    return actions[-max_items:]

def _extract_keywords(text):
    if not text:
        return []
    return re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{3,}", text)

def relevant_memory(agent, context=None, max_items=3):
    memory = agent.get("memory", [])
    if not memory:
        return []
    if context:
        tokens = _extract_keywords(context)
        if tokens:
            hits = [m for m in memory if any(t in m for t in tokens)]
            if hits:
                return hits[-max_items:]
    return memory[-max_items:]

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

def resolve_location(agent, activity, time_str, city_map):
    location_set = set(_all_locations(city_map))
    home = agent["locations"].get("home", "Home")
    work = agent["locations"].get("workplace", home)

    def pick_any(candidates):
        choice = _pick_first_available(candidates, location_set)
        return choice or home

    if any(k in activity for k in ["通勤"]):
        return pick_any(["Riverside Bus Station", "Riverside Ave", "Bridge Rd", "Market St"])
    if any(k in activity for k in ["工作", "上班", "加班"]):
        return work
    if any(k in activity for k in ["学习", "上课", "实验"]):
        return pick_any(["Riverside Middle School", "Riverside Primary School", "Hangzhou Tech Labs"])
    if any(k in activity for k in ["看病", "医院", "诊所"]):
        return pick_any(["Riverside Community Hospital", "Northside Family Clinic", "Willow Pharmacy"])
    if any(k in activity for k in ["晨练", "散步", "运动", "健身", "锻炼"]):
        return pick_any(["Riverside Park", "Willow Grove Park", "Fitness Area", "Playground"])
    if any(k in activity for k in ["买菜", "购物", "市场"]):
        return pick_any(["Market St", "Riverside Supermart", "Riverside Night Market", "Corner Mart"])
    if any(k in activity for k in ["电影", "娱乐", "休闲"]):
        return pick_any(["Riverside Cinema", "Riverside Park"])
    if any(k in activity for k in ["午饭", "晚饭", "吃饭"]):
        if time_str <= "10:30":
            return home
        return pick_any(["Market St", "Riverside Night Market", "Riverside Supermart"])
    if any(k in activity for k in ["吃早饭", "睡前", "午休", "休息", "个人时间"]):
        return home

    return agent["locations"].get("current", home)

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
    memory_hint = "；".join(relevant_memory(agent, context="日程安排")) if agent.get("memory") else "暂无重要经验"
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
    memory_hint = "；".join(relevant_memory(agent, context=memory_context)) if agent.get("memory") else "暂无重要经验"
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
    recent_actions = []
    if STATEFUL:
        recent_actions = load_recent_actions(agent["id"], max_items=6)

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
    memory_hint = "；".join(relevant_memory(agent, context=perception_text, max_items=2)) if agent["memory"] else "暂无重要经验"
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
    prompt = f"""
你是{agent['name']}。
刚刚发生的事情是：{outcome}

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

    memory_hint = "；".join(relevant_memory(agent, context="访谈", max_items=3)) if agent.get("memory") else "暂无重要经验"
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
def daily_summary(agent, logs):
    prompt = f"""
你是{agent['name']}。
这是你今天经历的关键片段：
{logs}

请总结今天最重要的一条经验或感受。
"""
    memory = call_llm(prompt, task="summary", agent_id=agent["id"])
    agent["memory"].append(memory)
    save_agent_memory(agent)
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
    if PRINT_AGENT_PROFILE:
        print_agent_profiles([a["id"] for a in agents])
    start_day = 1
    if STATEFUL:
        sim_state = load_sim_state()
        last_day = sim_state.get("last_day", 0)
        if isinstance(last_day, int) and last_day >= 0:
            start_day = last_day + 1
    if STATEFUL:
        for agent in agents:
            agent["memory"] = load_agent_memory(agent["id"])
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
    city_map = load_city_map(MAP_PATH)

    # === 构建社交网络 ===
    social_net = build_social_network(agents)
    for a in agents:
        a["social_neighbors"] = social_net[a["id"]]

    for a in agents:
        cached_locations = load_agent_locations(a["id"])
        if cached_locations:
            a["locations"] = cached_locations
            a["locations"].setdefault("current", a["locations"].get("home", "Home"))
        else:
            a["locations"] = assign_agent_locations(a, city_map)
            save_agent_locations(a["id"], a["locations"])

    schedules = {}
    actions = {}
    for a in agents:
        agent_id = a["id"]
        cached_schedule = load_agent_schedule(agent_id)
        if cached_schedule:
            schedules[agent_id] = cached_schedule
        else:
            schedules[agent_id] = generate_schedule(a)
            save_agent_schedule(agent_id, schedules[agent_id])

        cached_actions = load_agent_actions(agent_id)
        if cached_actions:
            actions[agent_id] = cached_actions
        else:
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

            for agent in agents:
                #act = random.choice(actions.get(activity, ["继续当前活动"]))
                activity = schedule_map[agent["id"]].get(time_str, "个人时间")
                act = choose_action(agent, activity, actions[agent["id"]])
                location = resolve_location(agent, activity, time_str, city_map)
                agent["locations"]["current"] = location
                social_context = get_social_context(agent, agents_by_id)

                policy_desc = None
                if policy:
                    policy_desc = policy.get("description") or policy.get("name")
                perc = perception(agent, time_str, social_context, env_context, policy_desc if policy else None)
                plan = planning(agent, perc)
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

            time.sleep(sleep_step)

        for agent in agents:
            mem = daily_summary(agent, daily_logs[agent["id"]])
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
    agent = build_agent(agent_id, df)
    if STATEFUL:
        agent["memory"] = load_agent_memory(agent["id"])
    else:
        agent["memory"] = []
    answers = interview_agent(agent, questions, context=context)
    print(json.dumps(answers, ensure_ascii=False, indent=2))

def _build_arg_parser():
    import argparse
    parser = argparse.ArgumentParser(description="GAWorld simulator")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Run the full simulation")

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
