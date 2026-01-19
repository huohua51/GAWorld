import requests
import time
import json
import random
from datetime import datetime

# ========== Ollama 配置 ==========
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma3n:e4b"

# ========== Profile 01 初始化 ==========
agent = {
    "name": "李泽宇",
    "age": 24,
    "city": "杭州",
    "job": "互联网公司初级算法工程师",
    "state": {
        "emotion": 0.58,
        "stress": 0.62,
        "econ_security": 0.50,
        "city_identity": 0.48
    },
    "context": {
        "living": "余杭未来科技城合租公寓",
        "work_style": "加班频繁，对绩效考核敏感",
        "personality": "内向理性，低冲突倾向"
    }
}

# ========== 时间映射 ==========
TIME_SLOTS = [
    "清晨起床",
    "通勤路上",
    "上午工作",
    "中午午餐",
    "下午工作",
    "傍晚加班",
    "夜晚回家",
    "睡前独处"
]

# ========== LLM 调用 ==========
def call_llm(prompt):
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=120)
    return r.json()["response"].strip()

# ========== 生成式思考 ==========
def agent_think(time_slot, agent):
    prompt = f"""
你是一个生活在杭州的年轻人，名字叫{agent['name']}，{agent['age']}岁，
职业是{agent['job']}。

你的性格特征：{agent['context']['personality']}
当前生活状态：住在{agent['context']['living']}，{agent['context']['work_style']}。

现在是一天中的阶段：【{time_slot}】。

你当前的心理状态：
- 情绪 emotion = {agent['state']['emotion']}
- 压力 stress = {agent['state']['stress']}
- 经济安全感 econ_security = {agent['state']['econ_security']}
- 城市认同 city_identity = {agent['state']['city_identity']}

请用第一人称，真实地描述：
1. 你此刻在想什么（内心独白）
2. 你决定做什么具体行动
3. 这一阶段对你情绪或压力的影响

要求：
- 不要写成小说
- 像真实生活中的碎碎念
- 100 字以内
"""
    return call_llm(prompt)

# ========== 状态更新（简化版） ==========
def update_state(agent):
    # 情绪受压力和安全感影响
    agent["state"]["emotion"] += (
        0.1 * agent["state"]["econ_security"]
        - 0.1 * agent["state"]["stress"]
        + random.uniform(-0.02, 0.02)
    )
    agent["state"]["stress"] += random.uniform(-0.03, 0.03)

    # clip
    for k in agent["state"]:
        agent["state"][k] = max(0, min(1, agent["state"][k]))

# ========== 日志输出 ==========
def log_event(day, time_slot, thought):
    print("=" * 60)
    print(f"🕒 虚拟第 {day} 天 | {time_slot}")
    print(thought)
    print("=" * 60)

# ========== 主循环 ==========
def run_simulation(sim_minutes=1):
    start = time.time()
    virtual_day = 1

    print(f"▶ 开始生成式虚拟生存模拟：{agent['name']}")
    print("▶ 现实 1 分钟 ≈ 虚拟 1 天")
    print()

    while time.time() - start < sim_minutes * 60:
        print(f"\n📅 ===== 虚拟第 {virtual_day} 天 =====")

        for slot in TIME_SLOTS:
            thought = agent_think(slot, agent)
            log_event(virtual_day, slot, thought)
            update_state(agent)

            # 时间加速：每个阶段 2 秒
            time.sleep(2)

        virtual_day += 1

    print("\n⏹ 模拟结束")

# ========== 运行 ==========
if __name__ == "__main__":
    run_simulation(sim_minutes=1)