import requests
import time
import random
import numpy as np
from datetime import timedelta

# ================== Ollama ==================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma3n:e4b"

def call_llm(prompt):
    r = requests.post(
        OLLAMA_URL,
        json={"model": MODEL_NAME, "prompt": prompt, "stream": False},
        timeout=120
    )
    return r.json()["response"].strip()

# ================== 仿真参数 ==================
SIM_DAYS = 2                  # 模拟多少天
SECONDS_PER_DAY = 60           # 现实 60 秒 ≈ 虚拟 1 天
EXTERNAL_RANDOMNESS = 0.6      # 世界不确定性强度（0–1）

# ================== 智能体 ==================
agent = {
    "name": "李泽宇",
    "job": "互联网公司初级算法工程师",
    "state": {
        "emotion": 0.58,
        "stress": 0.62,
        "econ_security": 0.50,
        "city_identity": 0.48
    }
}

# ================== 一天的时间轴 ==================
DAY_SCHEDULE = [
    ("07:30", "起床"),
    ("08:00", "洗漱"),
    ("08:30", "吃早饭"),
    ("09:00", "通勤"),
    ("10:00", "上午工作"),
    ("12:00", "午饭"),
    ("13:00", "午休"),
    ("14:00", "下午工作"),
    ("18:30", "下班或加班"),
    ("20:00", "晚饭"),
    ("21:00", "个人时间"),
    ("23:30", "睡前"),
]

# ================== 行动库 ==================
ACTIONS = {
    "吃早饭": ["点外卖早餐", "便利店买面包", "不吃早饭直接出门"],
    "通勤": ["坐地铁刷手机", "骑共享单车", "打车"],
    "上午工作": ["写代码", "改 bug", "开会", "摸鱼刷技术社区"],
    "午饭": ["和同事吃饭", "一个人吃", "随便点外卖"],
    "下午工作": ["继续写代码", "调模型参数", "被临时拉去开会"],
    "下班或加班": ["准点下班", "被动加班", "主动加班"],
    "晚饭": ["随便吃点", "点外卖", "和朋友吃"],
    "个人时间": ["刷手机", "打游戏", "看技术文章", "发呆"],
}

# ================== 随机事件池（含概率） ==================
RANDOM_EVENTS = [
    {
        "desc": "leader 临时布置紧急任务",
        "prob": 0.12,
        "effect": {"stress": +0.10}
    },
    {
        "desc": "代码被 review 夸了一句",
        "prob": 0.08,
        "effect": {"emotion": +0.08}
    },
    {
        "desc": "看到行业裁员新闻",
        "prob": 0.10,
        "effect": {"stress": +0.06}
    },
    {
        "desc": "天气很好，心情放松",
        "prob": 0.07,
        "effect": {"emotion": +0.05}
    },
    {
        "desc": "房东发来涨租提醒",
        "prob": 0.05,
        "effect": {"stress": +0.08, "econ_security": -0.05}
    },
]

def sample_random_event():
    if random.random() > EXTERNAL_RANDOMNESS:
        return None
    r = random.random()
    acc = 0
    for e in RANDOM_EVENTS:
        acc += e["prob"]
        if r < acc:
            return e
    return None

# ================== 状态更新 ==================
def update_state(agent):
    s = agent["state"]
    s["emotion"] += 0.08 * s["econ_security"] - 0.10 * s["stress"] + random.uniform(-0.02, 0.02)
    s["stress"] += random.uniform(-0.03, 0.03)
    for k in s:
        s[k] = float(np.clip(s[k], 0, 1))

# ================== 生成式解释 ==================
def generate_thought(day, time_str, activity, action, agent, event):
    event_text = f"刚刚发生了一件事：{event['desc']}。" if event else "没有发生特别的外部事件。"

    prompt = f"""
你是李泽宇，生活在杭州，从事算法工程师工作。
现在是虚拟第 {day} 天 {time_str}，你正在进行的生活阶段是【{activity}】。

你采取的具体行动是：【{action}】。
{event_text}

你当前状态：
情绪={agent['state']['emotion']:.2f}
压力={agent['state']['stress']:.2f}
经济安全感={agent['state']['econ_security']:.2f}

请用第一人称，真实记录：
- 你当下的想法
- 你为什么会这么做
- 你对生活的即时感受

要求：像真实生活记录，不超过 120 字。
"""
    return call_llm(prompt)

# ================== 主循环 ==================
def run_simulation():
    print("▶ 开始生成式虚拟生存模拟（细粒度日常 + 概率事件）\n")
    sleep_per_step = SECONDS_PER_DAY / (SIM_DAYS * len(DAY_SCHEDULE))

    for day in range(1, SIM_DAYS + 1):
        print(f"\n📅 ===== 虚拟第 {day} 天 =====")

        for time_str, activity in DAY_SCHEDULE:
            action = random.choice(ACTIONS.get(activity, ["继续日常"]))
            event = sample_random_event()

            if event:
                for k, v in event["effect"].items():
                    agent["state"][k] += v

            thought = generate_thought(day, time_str, activity, action, agent, event)

            print("-" * 70)
            print(f"🕒 {time_str} ｜ {activity}")
            print(f"👉 行动：{action}")
            if event:
                print(f"⚠ 随机事件：{event['desc']}")
            print(thought)

            update_state(agent)
            time.sleep(sleep_per_step)

    print("\n⏹ 模拟结束")

# ================== 运行 ==================
if __name__ == "__main__":
    run_simulation()