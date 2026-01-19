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
#MODEL_NAME = "gemma3n:e4b"
MODEL_NAME = "gemma3:12b"

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
# 参数
# =========================================================
AGENT_ID = 9
SIM_DAYS = 2
SECONDS_PER_DAY = 60

CSV_PATH = "hangzhou_agents_state_init.csv"
MD_PATH = "hangzhou_profiles_with_names.md"

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
# Profile 解析（MD + CSV）
# =========================================================
def load_profile_from_md(md_path, agent_id):
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    pattern = rf"## Profile {agent_id:02d}｜.*?(?=\n## Profile |\Z)"
    match = re.search(pattern, text, re.S)
    if not match:
        raise ValueError("Profile not found")
    return match.group(0)

def parse_profile_block(block):
    p = {}
    p["name"] = re.search(r"## Profile \d+｜(.+)", block).group(1)
    base = re.search(r"\*\*基础信息\*\*：(.+)", block)
    if base:
        age = re.search(r"(\d+)岁", base.group(1))
        p["age"] = int(age.group(1)) if age else None
        living = re.search(r"居住(?:于)?(.+?)[，。]", base.group(1))
        p["living"] = living.group(1) if living else ""
    job = re.search(r"\*\*职业与工作节奏\*\*：(.+)", block)
    p["job"] = job.group(1) if job else ""
    personality = re.search(r"\*\*性格与情绪特征\*\*：(.+)", block)
    p["personality"] = personality.group(1) if personality else ""
    p["work_style"] = p["job"]
    return p

def build_full_profile(agent_id):
    df = pd.read_csv(CSV_PATH)
    row = df[df["id"] == agent_id].iloc[0]
    block = load_profile_from_md(MD_PATH, agent_id)
    text_p = parse_profile_block(block)

    return {
        "id": agent_id,
        "name": text_p["name"],
        "age": text_p["age"],
        "job": text_p["job"],
        "living": text_p["living"],
        "personality": text_p["personality"],
        "work_style": text_p["work_style"],
        "state": {
            "emotion": row["emotion"],
            "stress": row["stress"],
            "econ_security": row["econ_security"],
            "city_identity": row["city_identity"]
        }
    }

# =========================================================
# 日程与行动生成
# =========================================================
def generate_day_schedule(profile):
    base = [
        ("07:30", "起床"),
        ("08:30", "吃早饭"),
        ("09:00", "通勤"),
        ("10:00", "上午工作"),
        ("12:00", "午饭"),
        ("14:00", "下午工作"),
    ]
    if "加班" in profile["work_style"]:
        base += [("18:30", "加班"), ("21:30", "个人时间")]
    else:
        base += [("18:00", "下班"), ("20:00", "个人时间")]
    base.append(("23:30", "睡前"))
    return base

def generate_action_space(profile):
    actions = {
        "起床": ["赖床几分钟", "立刻起床"],
        "吃早饭": ["点外卖早餐", "便利店买面包"],
        "通勤": ["坐地铁刷手机", "骑共享单车"],
        "上午工作": ["写代码", "改 bug", "开会"],
        "下午工作": ["调模型参数", "继续写代码"],
        "加班": ["继续写代码", "处理临时需求"],
        "个人时间": ["刷手机", "看技术文章", "发呆"],
        "睡前": ["刷手机", "躺着发呆"]
    }
    if "内向" in profile["personality"]:
        actions["个人时间"] = ["一个人刷手机", "发呆"]
    return actions

# =========================================================
# 状态更新
# =========================================================
def clip_state(p):
    for k in p["state"]:
        p["state"][k] = float(np.clip(p["state"][k], 0, 1))

def update_state(p):
    s = p["state"]
    s["emotion"] += 0.08 * s["econ_security"] - 0.1 * s["stress"] + random.uniform(-0.02, 0.02)
    s["stress"] += random.uniform(-0.03, 0.03)
    clip_state(p)

# =========================================================
# 生成认知—行动循环
# =========================================================
def generate_cognitive_log(profile, day, time_str, activity, action, event):
    event_text = f"发生了事件：{event['name']}。" if event else "没有显著制度或突发事件。"

    prompt = f"""
你是{profile['name']}，{profile['age']}岁，{profile['job']}，
住在{profile['living']}，性格：{profile['personality']}。

现在是虚拟第 {day} 天 {time_str}，
当前阶段：【{activity}】，
你采取的行动是：【{action}】。
{event_text}

你当前状态：
emotion={profile['state']['emotion']:.2f}
stress={profile['state']['stress']:.2f}
econ_security={profile['state']['econ_security']:.2f}
city_identity={profile['state']['city_identity']:.2f}

请严格按以下结构输出（每项 1–2 句话）：
Perception（你感知到的环境/他人）
Thought（你脑子里在想什么）
Plan（你此刻的小规划）
Outcome（行动的直接结果）
Reflection（你对这一刻的反思或情绪变化）
"""
    return call_llm(prompt)

# =========================================================
# 主循环
# =========================================================
def run_simulation():
    profile = build_full_profile(AGENT_ID)
    schedule = generate_day_schedule(profile)
    actions = generate_action_space(profile)
    sleep_step = SECONDS_PER_DAY / (SIM_DAYS * len(schedule))

    print(f"▶ 开始模拟：Profile {profile['id']}｜{profile['name']}\n")

    for day in range(1, SIM_DAYS + 1):
        print(f"\n📅 ===== 虚拟第 {day} 天 =====")
        for time_str, activity in schedule:
            action = random.choice(actions.get(activity, ["继续当前活动"]))
            event = next(
                (e for e in SCHEDULED_EVENTS if e["day"] == day and e["time"] == time_str),
                None
            )
            if event:
                for k, v in event["effect"].items():
                    profile["state"][k] += v
                clip_state(profile)

            log = generate_cognitive_log(profile, day, time_str, activity, action, event)

            print("-" * 80)
            print(f"[Time] 第{day}天 {time_str} | {activity}")
            print(f"[Action] {action}")
            if event:
                print(f"[Event] {event['name']}")
            print(log)

            update_state(profile)
            time.sleep(sleep_step)

    print("\n⏹ 模拟结束")

# =========================================================
# 入口
# =========================================================
if __name__ == "__main__":
    run_simulation()