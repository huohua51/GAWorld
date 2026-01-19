import pandas as pd
import requests
import time
import random
import numpy as np
import re

# =========================================================
# Ollama 配置
# =========================================================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma3n:e4b"

def call_llm(prompt):
    r = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False
        },
        timeout=120
    )
    return r.json()["response"].strip()

# =========================================================
# 用户可调参数
# =========================================================
AGENT_ID = 25                     # 选择 Profile（1–50）
SIM_DAYS = 2                     # 模拟天数
SECONDS_PER_DAY = 60             # 现实 60 秒 ≈ 虚拟 1 天

CSV_PATH = "hangzhou_agents_state_init.csv"
MD_PATH = "hangzhou_profiles_with_names.md"

# 结构性事件（示例：政策）
SCHEDULED_EVENTS = [
    {
        "day": 1,
        "time": "10:00",
        "name": "平台劳动者保障政策",
        "effect": {
            "econ_security": +0.20,
            "stress": -0.15,
            "city_identity": +0.10
        }
    }
]

# =========================================================
# Step 1：从 MD 中读取某个 Profile 块
# =========================================================
def load_profile_from_md(md_path, agent_id):
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()

    pattern = rf"## Profile {agent_id:02d}｜.*?(?=\n## Profile |\Z)"
    match = re.search(pattern, text, re.S)

    if not match:
        raise ValueError(f"Profile {agent_id} not found in MD")

    return match.group(0)

# =========================================================
# Step 2：解析 Profile 文本为结构化字段
# =========================================================
def parse_profile_block(block):
    profile = {}

    # 姓名
    name_match = re.search(r"## Profile \d+｜(.+)", block)
    profile["name"] = name_match.group(1).strip()

    # 基础信息
    base_match = re.search(r"\*\*基础信息\*\*：(.+)", block)
    if base_match:
        base = base_match.group(1)
        age_match = re.search(r"(\d+)岁", base)
        profile["age"] = int(age_match.group(1)) if age_match else None

        living_match = re.search(r"居住(?:于)?(.+?)[，。]", base)
        profile["living"] = living_match.group(1) if living_match else ""
    else:
        profile["age"] = None
        profile["living"] = ""

    # 职业与工作节奏
    job_match = re.search(r"\*\*职业与工作节奏\*\*：(.+)", block)
    profile["job"] = job_match.group(1).strip() if job_match else ""

    # 性格
    personality_match = re.search(r"\*\*性格与情绪特征\*\*：(.+)", block)
    profile["personality"] = personality_match.group(1).strip() if personality_match else ""

    # 工作风格（直接复用职业段）
    profile["work_style"] = profile["job"]

    return profile

# =========================================================
# Step 3：构建完整 profile（MD + CSV）
# =========================================================
def build_full_profile(agent_id, md_path, csv_path):
    # 数值状态
    df = pd.read_csv(csv_path)
    row = df[df["id"] == agent_id].iloc[0]

    # 叙事 Profile
    block = load_profile_from_md(md_path, agent_id)
    text_profile = parse_profile_block(block)

    profile = {
        "id": agent_id,
        "name": text_profile["name"],
        "age": text_profile["age"],
        "job": text_profile["job"],
        "living": text_profile["living"],
        "work_style": text_profile["work_style"],
        "personality": text_profile["personality"],
        "state": {
            "emotion": row["emotion"],
            "stress": row["stress"],
            "econ_security": row["econ_security"],
            "city_identity": row["city_identity"]
        }
    }

    return profile

# =========================================================
# Step 4：Profile → DAY_SCHEDULE
# =========================================================
def generate_day_schedule(profile):
    schedule = [
        ("07:30", "起床"),
        ("08:00", "洗漱"),
        ("08:30", "吃早饭"),
        ("09:00", "通勤"),
        ("10:00", "上午工作"),
        ("12:00", "午饭"),
        ("13:00", "午休"),
        ("14:00", "下午工作"),
    ]

    if "加班" in profile["work_style"]:
        schedule += [
            ("18:30", "加班"),
            ("20:30", "晚饭"),
            ("21:30", "个人时间"),
        ]
    else:
        schedule += [
            ("18:00", "下班"),
            ("19:00", "晚饭"),
            ("20:00", "个人时间"),
        ]

    schedule.append(("23:30", "睡前"))
    return schedule

# =========================================================
# Step 5：Profile → ACTION SPACE
# =========================================================
def generate_action_space(profile):
    actions = {
        "吃早饭": ["点外卖早餐", "便利店买面包"],
        "通勤": ["坐地铁刷手机", "骑共享单车"],
        "上午工作": ["写代码", "改 bug", "查资料"],
        "下午工作": ["继续写代码", "调模型参数", "被临时拉去开会"],
        "午饭": ["和同事吃饭", "一个人吃外卖"],
        "加班": ["继续写代码", "处理临时需求"],
        "晚饭": ["点外卖", "随便吃点"],
        "个人时间": ["刷手机", "看技术文章", "打游戏"],
        "睡前": ["刷手机", "发呆"]
    }

    if "内向" in profile["personality"]:
        actions["晚饭"] = ["一个人点外卖", "随便吃点"]

    return actions

# =========================================================
# 状态更新
# =========================================================
def clip_state(profile):
    for k in profile["state"]:
        profile["state"][k] = float(np.clip(profile["state"][k], 0, 1))

def update_state(profile):
    s = profile["state"]
    s["emotion"] += 0.08 * s["econ_security"] - 0.10 * s["stress"] + random.uniform(-0.02, 0.02)
    s["stress"] += random.uniform(-0.03, 0.03)
    clip_state(profile)

# =========================================================
# 检查结构性事件
# =========================================================
def check_scheduled_event(day, time_str):
    for e in SCHEDULED_EVENTS:
        if e["day"] == day and e["time"] == time_str:
            return e
    return None

# =========================================================
# 生成式思考（Profile 驱动）
# =========================================================
def generate_thought(profile, day, time_str, activity, action, event):
    event_text = (
        f"今天发生了一件重要事件：【{event['name']}】。" if event else "今天没有发生特殊制度性事件。"
    )

    prompt = f"""
你是{profile['name']}，{profile['age']}岁，
职业是{profile['job']}，住在{profile['living']}。
性格特征：{profile['personality']}。
工作状态：{profile['work_style']}。

现在是虚拟第 {day} 天 {time_str}，
你正在【{activity}】，采取的行动是【{action}】。
{event_text}

你当前状态：
情绪={profile['state']['emotion']:.2f}
压力={profile['state']['stress']:.2f}
经济安全感={profile['state']['econ_security']:.2f}
城市认同={profile['state']['city_identity']:.2f}

请用第一人称、真实生活语气记录你的想法与感受（≤120 字）。
"""
    return call_llm(prompt)

# =========================================================
# 主仿真循环
# =========================================================
def run_simulation():
    profile = build_full_profile(AGENT_ID, MD_PATH, CSV_PATH)
    schedule = generate_day_schedule(profile)
    actions = generate_action_space(profile)

    print(f"▶ 开始模拟：Profile {profile['id']}｜{profile['name']}\n")
    sleep_step = SECONDS_PER_DAY / (SIM_DAYS * len(schedule))

    for day in range(1, SIM_DAYS + 1):
        print(f"\n📅 ===== 虚拟第 {day} 天 =====")

        for time_str, activity in schedule:
            action = random.choice(actions.get(activity, ["继续当前活动"]))
            event = check_scheduled_event(day, time_str)

            if event:
                for k, v in event["effect"].items():
                    profile["state"][k] += v
                clip_state(profile)

            thought = generate_thought(profile, day, time_str, activity, action, event)

            print("-" * 70)
            print(f"🕒 {time_str} ｜ {activity}")
            print(f"👉 行动：{action}")
            if event:
                print(f"⚠ 结构性事件：{event['name']}")
            print(thought)

            update_state(profile)
            time.sleep(sleep_step)

    print("\n⏹ 模拟结束")

# =========================================================
# 入口
# =========================================================
if __name__ == "__main__":
    run_simulation()