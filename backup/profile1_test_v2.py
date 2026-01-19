import requests
import time
import random
import numpy as np

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

# ================== 全局参数 ==================
SIM_DAYS = 3                  # 模拟多少天
SECONDS_PER_DAY = 60           # 现实多少秒 ≈ 虚拟一天
EXTERNAL_RANDOMNESS = 0.4      # 外部随机性 0–1
SOCIAL_INFLUENCE_WEIGHT = 0.3  # 社交影响权重

TIME_SLOTS = [
    "清晨起床", "通勤路上", "上午工作",
    "中午午餐", "下午工作", "傍晚加班",
    "夜晚回家", "睡前独处"
]

# ================== 主体智能体 ==================
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

# ================== 社交网络（弱智能体） ==================
social_network = [
    {"name": "同事A", "effect": {"stress": +0.05, "emotion": -0.03}},
    {"name": "同事B", "effect": {"emotion": +0.04}},
    {"name": "大学朋友", "effect": {"emotion": +0.06, "city_identity": +0.03}},
    {"name": "父母", "effect": {"stress": -0.04, "econ_security": +0.02}},
]

# ================== 外部随机事件 ==================
RANDOM_EVENTS = [
    {"desc": "线上系统故障，工作被打断", "stress": +0.08},
    {"desc": "leader临时夸了你一句", "emotion": +0.07},
    {"desc": "看到裁员新闻", "stress": +0.06},
    {"desc": "天气很好，下班路上很舒服", "emotion": +0.05},
    {"desc": "房东发来涨租消息", "stress": +0.07, "econ_security": -0.04},
]

def maybe_external_event():
    if random.random() < EXTERNAL_RANDOMNESS:
        return random.choice(RANDOM_EVENTS)
    return None

# ================== 社交影响 ==================
def apply_social_influence(agent):
    peer = random.choice(social_network)
    for k, v in peer["effect"].items():
        agent["state"][k] += SOCIAL_INFLUENCE_WEIGHT * v

# ================== 状态更新 ==================
def update_internal_state(agent):
    s = agent["state"]
    s["emotion"] += 0.1 * s["econ_security"] - 0.1 * s["stress"] + random.uniform(-0.02, 0.02)
    s["stress"] += random.uniform(-0.03, 0.03)

    for k in s:
        s[k] = float(np.clip(s[k], 0, 1))

# ================== 生成式思考 ==================
def agent_think(day, slot, agent, external_event=None):
    event_text = f"刚刚发生了一件事：{external_event['desc']}。" if external_event else "没有发生特别的外部事件。"

    prompt = f"""
你是生活在杭州的年轻人李泽宇，从事算法工程师工作。
现在是虚拟第 {day} 天，【{slot}】。

{event_text}

你当前状态：
情绪={agent['state']['emotion']:.2f}
压力={agent['state']['stress']:.2f}
经济安全感={agent['state']['econ_security']:.2f}
城市认同={agent['state']['city_identity']:.2f}

请用第一人称，真实描述：
1. 你现在在想什么
2. 你决定采取什么行动
3. 你对今天生活的即时感受

要求：像真实生活碎碎念，不超过 120 字。
"""
    return call_llm(prompt)

# ================== 主循环 ==================
def run_simulation():
    print("▶ 开始生成式虚拟生存模拟（支持多天 / 随机性 / 社交影响）\n")

    sleep_per_slot = SECONDS_PER_DAY / (len(TIME_SLOTS) * SIM_DAYS)

    for day in range(1, SIM_DAYS + 1):
        print(f"\n📅 ===== 虚拟第 {day} 天 =====")

        for slot in TIME_SLOTS:
            external_event = maybe_external_event()
            if external_event:
                for k, v in external_event.items():
                    if k != "desc":
                        agent["state"][k] += v

            apply_social_influence(agent)
            thought = agent_think(day, slot, agent, external_event)

            print("-" * 60)
            print(f"🕒 {slot}")
            if external_event:
                print(f"【外部事件】{external_event['desc']}")
            print(thought)

            update_internal_state(agent)
            time.sleep(sleep_per_slot)

    print("\n⏹ 模拟结束")

# ================== 运行 ==================
if __name__ == "__main__":
    run_simulation()