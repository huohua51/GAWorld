import csv
import json
import os
import random
from copy import deepcopy
from collections import defaultdict


DEFAULT_ECONOMY_CONFIG = {
    "enabled": True,
    "currency": "CNY",
    "output_dir": "output/economy",
    "state_file_prefix": "agent_",
    "state_file_suffix": "_economy.json",
    "hours_per_step": 1.0,
    "initial_savings_months_min": 1.0,
    "initial_savings_months_max": 6.0,
    "rent_income_ratio": 0.22,
    "daily_utilities_cost": 12.0,
    "base_living_cost_per_hour": 6.0,
    "min_hourly_income": 8.0,
    "income_volatility": 0.25,
    "target_work_hours_per_day": 7.0,
    "asset_safety_days": 18.0,
    "income_seek_threshold": 0.56,
    "income_seek_probability_scale": 0.9,
    "wealth_drive_seek_threshold": 0.65,
    "income_growth_when_deficit": 0.08,
    "income_seek_activities": ["工作", "兼职", "接单", "技能提升"],
    "expense_ranges": {
        "food": [8.0, 26.0],
        "clothing": [18.0, 120.0],
        "transport": [3.0, 28.0],
        "housing": [0.0, 0.0],
        "leisure": [8.0, 70.0],
        "education": [10.0, 60.0],
        "healthcare": [12.0, 90.0],
        "misc": [4.0, 22.0],
    },
}

INCOME_KEYWORDS = [
    "工作",
    "上班",
    "加班",
    "开会",
    "办公",
    "通勤",
    "接单",
    "兼职",
    "经营",
    "摆摊",
    "授课",
    "学习",
    "复习",
    "训练",
]

SLEEP_KEYWORDS = ["睡", "就寝", "休息"]

EXPENSE_KEYWORDS = {
    "food": ["吃", "饭", "餐", "做饭", "买菜", "外卖", "咖啡", "奶茶"],
    "clothing": ["衣", "鞋", "穿搭", "服饰", "购物"],
    "transport": ["通勤", "出行", "地铁", "公交", "打车", "骑行", "步行", "开车"],
    "housing": ["房租", "租房", "物业", "水电", "家务", "居住"],
    "leisure": ["娱乐", "游戏", "电影", "逛街", "聚会", "旅行", "放松"],
    "education": ["学习", "课程", "培训", "阅读", "写作", "练习"],
    "healthcare": ["医院", "看病", "药", "体检", "治疗", "康复", "健身"],
}

JOB_INCOME_BANDS = [
    (["医生", "律师", "金融", "证券", "架构", "总监", "管理"], 75.0, 150.0),
    (["工程", "研发", "程序", "算法", "产品", "设计", "教师", "会计"], 38.0, 90.0),
    (["销售", "客服", "运营", "行政", "司机", "物流", "店员", "服务"], 18.0, 55.0),
    (["学生", "失业", "待业", "退休", "无业"], 8.0, 22.0),
]


def _clip(value, low, high):
    return max(low, min(high, float(value)))


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _deep_update(base, patch):
    if not isinstance(base, dict) or not isinstance(patch, dict):
        return base
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _get_cfg(context):
    config = context.get("config", {}) if isinstance(context, dict) else {}
    cfg = deepcopy(DEFAULT_ECONOMY_CONFIG)
    user_cfg = config.get("economy", {}) if isinstance(config, dict) else {}
    if isinstance(user_cfg, dict):
        _deep_update(cfg, user_cfg)
    return cfg


def _economy_state(context):
    ext = context.setdefault("extension_state", {})
    return ext.setdefault("economy_module", {"day_rows": [], "enabled": False})


def _memory_dir(context):
    cfg = context.get("config", {}) if isinstance(context, dict) else {}
    return str(cfg.get("memory_dir", "output/memory"))


def _log_dir(context):
    cfg = context.get("config", {}) if isinstance(context, dict) else {}
    return str(cfg.get("log_dir", "output/logs"))


def _is_stateful(context):
    cfg = context.get("config", {}) if isinstance(context, dict) else {}
    return bool(cfg.get("stateful", False))


def _state_path(context, agent_id, cfg):
    filename = f"{cfg['state_file_prefix']}{agent_id}{cfg['state_file_suffix']}"
    return os.path.join(_memory_dir(context), filename)


def _append_agent_log(context, agent_id, text):
    if not text:
        return
    target_dir = _log_dir(context)
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, f"agent_{agent_id}.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def _rand_between(rng_cfg):
    if not isinstance(rng_cfg, (list, tuple)) or len(rng_cfg) != 2:
        return 0.0
    low = _to_float(rng_cfg[0], 0.0)
    high = _to_float(rng_cfg[1], low)
    if high < low:
        low, high = high, low
    return random.uniform(low, high)


def _contains_any(text, keywords):
    src = str(text or "")
    return any(k in src for k in keywords)


def _is_sleep_activity(text):
    return _contains_any(text, SLEEP_KEYWORDS)


def _is_income_activity(activity, action):
    return _contains_any(activity, INCOME_KEYWORDS) or _contains_any(action, INCOME_KEYWORDS)


def _job_income_band(job_text):
    job = str(job_text or "")
    for keywords, low, high in JOB_INCOME_BANDS:
        if _contains_any(job, keywords):
            return low, high
    return 22.0, 62.0


def _infer_wealth_drive(agent):
    state = agent.get("state", {}) if isinstance(agent, dict) else {}
    base = 0.45
    base += 0.25 * _to_float(state.get("risk_preference", 0.5), 0.5)
    base += 0.15 * _to_float(state.get("stress", 0.5), 0.5)
    personality = " ".join(
        str(agent.get(key, ""))
        for key in ("personality", "values", "daily_life", "job")
    )
    if _contains_any(personality, ["上进", "奋斗", "赚钱", "改善", "成长", "野心"]):
        base += 0.08
    if _contains_any(personality, ["佛系", "躺平", "知足", "淡泊"]):
        base -= 0.10
    return _clip(base, 0.08, 0.98)


def _infer_income_skill(agent):
    age = int(_to_float(agent.get("age", 30), 30))
    state = agent.get("state", {}) if isinstance(agent, dict) else {}
    econ_security = _to_float(state.get("econ_security", 0.5), 0.5)
    if age <= 22:
        age_factor = 0.35
    elif age <= 30:
        age_factor = 0.55
    elif age <= 45:
        age_factor = 0.70
    elif age <= 60:
        age_factor = 0.62
    else:
        age_factor = 0.45
    return _clip(0.55 * age_factor + 0.45 * econ_security, 0.1, 0.98)


def _empty_daily_categories():
    return {
        "food": 0.0,
        "clothing": 0.0,
        "housing": 0.0,
        "transport": 0.0,
        "leisure": 0.0,
        "education": 0.0,
        "healthcare": 0.0,
        "misc": 0.0,
    }


def _record_income(econ, amount):
    value = max(0.0, _to_float(amount, 0.0))
    econ["daily_income"] += value
    econ["lifetime_income"] += value
    econ["balance"] += value


def _record_expense(econ, category, amount):
    value = max(0.0, _to_float(amount, 0.0))
    econ["daily_expense"] += value
    econ["lifetime_expense"] += value
    econ["balance"] -= value
    if category not in econ["daily_expense_by_category"]:
        econ["daily_expense_by_category"][category] = 0.0
    econ["daily_expense_by_category"][category] += value


def _save_agent_economy(context, agent, cfg):
    if not _is_stateful(context):
        return
    path = _state_path(context, agent["id"], cfg)
    payload = agent.get("economy", {})
    if not isinstance(payload, dict):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _load_agent_economy(context, agent_id, cfg):
    if not _is_stateful(context):
        return {}
    path = _state_path(context, agent_id, cfg)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _init_agent_economy(agent, cfg, context):
    saved = _load_agent_economy(context, agent["id"], cfg)
    if saved:
        saved.setdefault("daily_expense_by_category", _empty_daily_categories())
        saved.setdefault("currency", cfg["currency"])
        agent["economy"] = saved
        return

    job = str(agent.get("job", ""))
    low, high = _job_income_band(job)
    income_skill = _infer_income_skill(agent)
    wealth_drive = _infer_wealth_drive(agent)
    base_hourly_income = random.uniform(low, high) * (0.75 + 0.55 * income_skill)
    monthly_income = base_hourly_income * 8.0 * 22.0
    init_months = random.uniform(
        _to_float(cfg.get("initial_savings_months_min", 1.0), 1.0),
        _to_float(cfg.get("initial_savings_months_max", 6.0), 6.0),
    )
    init_balance = monthly_income * init_months * (0.7 + 0.6 * _to_float(agent.get("state", {}).get("econ_security", 0.5), 0.5))
    monthly_rent = monthly_income * _to_float(cfg.get("rent_income_ratio", 0.22), 0.22) * random.uniform(0.85, 1.15)

    agent["economy"] = {
        "currency": cfg["currency"],
        "wealth_drive": _clip(wealth_drive, 0.0, 1.0),
        "income_skill": _clip(income_skill, 0.0, 1.0),
        "base_hourly_income": max(_to_float(cfg.get("min_hourly_income", 8.0), 8.0), base_hourly_income),
        "hourly_income": max(_to_float(cfg.get("min_hourly_income", 8.0), 8.0), base_hourly_income),
        "income_volatility": max(0.0, _to_float(cfg.get("income_volatility", 0.25), 0.25)),
        "income_target_daily": max(40.0, base_hourly_income * _to_float(cfg.get("target_work_hours_per_day", 7.0), 7.0)),
        "monthly_rent": max(600.0, monthly_rent),
        "balance": max(0.0, init_balance),
        "daily_income": 0.0,
        "daily_expense": 0.0,
        "daily_expense_by_category": _empty_daily_categories(),
        "lifetime_income": 0.0,
        "lifetime_expense": 0.0,
        "last_location": "",
    }
    _save_agent_economy(context, agent, cfg)


def _step_hours(context, cfg):
    runtime = _economy_state(context)
    cached = _to_float(runtime.get("hours_per_step", 0.0), 0.0)
    if cached > 0:
        return cached
    step_hours = _to_float(cfg.get("hours_per_step", 1.0), 1.0)
    sim_cfg = context.get("config", {}) if isinstance(context, dict) else {}
    raw_step = sim_cfg.get("time_step_minutes")
    if isinstance(raw_step, (int, float)) and raw_step > 0:
        step_hours = max(0.1, float(raw_step) / 60.0)
    runtime["hours_per_step"] = step_hours
    return step_hours


def _add_daily_log(context, agent, line):
    daily_logs = context.get("daily_logs")
    if isinstance(daily_logs, dict):
        agent_id = agent["id"]
        daily_logs[agent_id] = daily_logs.get(agent_id, "") + line
    _append_agent_log(context, agent["id"], line)


def _estimate_behavior_expenses(agent, activity, action, location, hours, cfg):
    econ = agent.get("economy", {})
    if not isinstance(econ, dict):
        return {}
    level = 0.8 + 0.5 * _to_float(econ.get("wealth_drive", 0.5), 0.5) + 0.35 * _to_float(econ.get("income_skill", 0.5), 0.5)
    base_cost = _to_float(cfg.get("base_living_cost_per_hour", 6.0), 6.0) * max(hours, 0.1) * level
    result = {"misc": base_cost}
    text = " ".join([str(activity or ""), str(action or ""), str(location or "")])
    for category, keywords in EXPENSE_KEYWORDS.items():
        if _contains_any(text, keywords):
            amount = _rand_between(cfg.get("expense_ranges", {}).get(category, [0.0, 0.0]))
            if amount > 0:
                result[category] = result.get(category, 0.0) + amount
                result["misc"] = max(0.0, result.get("misc", 0.0) - min(result.get("misc", 0.0), amount * 0.25))
    if location and econ.get("last_location") and location != econ.get("last_location"):
        move_cost = _rand_between(cfg.get("expense_ranges", {}).get("transport", [3.0, 12.0]))
        result["transport"] = result.get("transport", 0.0) + move_cost
    econ["last_location"] = str(location or econ.get("last_location", ""))
    return result


def _update_econ_security(agent):
    econ = agent.get("economy", {})
    state = agent.get("state", {})
    if not isinstance(econ, dict) or not isinstance(state, dict):
        return
    target = max(1.0, _to_float(econ.get("income_target_daily", 80.0), 80.0) * 20.0)
    asset_score = _clip(_to_float(econ.get("balance", 0.0), 0.0) / target, 0.0, 2.0) / 2.0
    prev = _to_float(state.get("econ_security", 0.5), 0.5)
    state["econ_security"] = _clip(prev * 0.88 + (0.35 + 0.65 * asset_score) * 0.12, 0.0, 1.0)


def _pick_income_activity(context, agent):
    agent_id = agent.get("id")
    actions = context.get("actions", {})
    if isinstance(actions, dict):
        agent_actions = actions.get(agent_id, {})
        if isinstance(agent_actions, dict):
            candidates = [name for name in agent_actions.keys() if _contains_any(name, INCOME_KEYWORDS)]
            if candidates:
                return random.choice(candidates)
    cfg = _get_cfg(context)
    default_candidates = cfg.get("income_seek_activities", [])
    if isinstance(default_candidates, list) and default_candidates:
        return str(random.choice(default_candidates))
    return "工作"


def _should_seek_income(agent, cfg):
    econ = agent.get("economy", {})
    if not isinstance(econ, dict):
        return False
    drive = _to_float(econ.get("wealth_drive", 0.5), 0.5)
    target = max(1.0, _to_float(econ.get("income_target_daily", 80.0), 80.0))
    gap = max(0.0, target - _to_float(econ.get("daily_income", 0.0), 0.0)) / target
    safety_days = max(1.0, _to_float(cfg.get("asset_safety_days", 18.0), 18.0))
    daily_floor = max(1.0, _to_float(econ.get("daily_expense", 0.0), 0.0) + target * 0.4)
    safety_balance = daily_floor * safety_days
    asset_pressure = max(0.0, safety_balance - _to_float(econ.get("balance", 0.0), 0.0)) / max(1.0, safety_balance)
    motive = drive * 0.55 + gap * 0.30 + asset_pressure * 0.25
    threshold = _to_float(cfg.get("income_seek_threshold", 0.56), 0.56)
    if motive < threshold:
        return False
    probability = _clip(motive * _to_float(cfg.get("income_seek_probability_scale", 0.9), 0.9), 0.0, 0.95)
    return random.random() < probability


def on_simulation_start(context):
    cfg = _get_cfg(context)
    runtime = _economy_state(context)
    runtime["enabled"] = bool(cfg.get("enabled", True))
    if not runtime["enabled"]:
        return
    os.makedirs(cfg.get("output_dir", "output/economy"), exist_ok=True)
    _step_hours(context, cfg)
    for agent in context.get("agents", []):
        if not isinstance(agent, dict) or "id" not in agent:
            continue
        _init_agent_economy(agent, cfg, context)
        econ = agent.get("economy", {})
        init_line = (
            f"[EconomyInit] balance={econ.get('balance', 0.0):.2f} {econ.get('currency', 'CNY')} "
            f"hourly_income={econ.get('hourly_income', 0.0):.2f} "
            f"wealth_drive={econ.get('wealth_drive', 0.0):.2f}"
        )
        _append_agent_log(context, agent["id"], init_line)


def on_day_start(context):
    cfg = _get_cfg(context)
    runtime = _economy_state(context)
    if not runtime.get("enabled", False):
        return
    for agent in context.get("agents", []):
        econ = agent.get("economy", {})
        if not isinstance(econ, dict):
            continue
        econ["daily_income"] = 0.0
        econ["daily_expense"] = 0.0
        econ["daily_expense_by_category"] = _empty_daily_categories()
        base_hour = max(
            _to_float(cfg.get("min_hourly_income", 8.0), 8.0),
            _to_float(econ.get("base_hourly_income", 8.0), 8.0),
        )
        volatility = _to_float(econ.get("income_volatility", cfg.get("income_volatility", 0.25)), 0.25)
        daily_shift = 1.0 + random.uniform(-volatility, volatility) * (1.0 - 0.35 * _to_float(econ.get("income_skill", 0.5), 0.5))
        econ["hourly_income"] = max(_to_float(cfg.get("min_hourly_income", 8.0), 8.0), base_hour * daily_shift)

        housing = max(0.0, _to_float(econ.get("monthly_rent", 0.0), 0.0) / 30.0)
        utilities = max(0.0, _to_float(cfg.get("daily_utilities_cost", 12.0), 12.0))
        if housing > 0:
            _record_expense(econ, "housing", housing)
        if utilities > 0:
            _record_expense(econ, "housing", utilities)

        _update_econ_security(agent)
        line = (
            f"[EconomyDayStart D{context.get('day', '')}] fixed_expense={housing + utilities:.2f} "
            f"hourly_income={econ.get('hourly_income', 0.0):.2f} balance={econ.get('balance', 0.0):.2f}\n"
        )
        _add_daily_log(context, agent, line)


def on_agent_pre_step(context):
    cfg = _get_cfg(context)
    runtime = _economy_state(context)
    if not runtime.get("enabled", False):
        return
    agent = context.get("agent", {})
    step = context.get("step", {})
    if not isinstance(agent, dict) or not isinstance(step, dict):
        return
    activity = str(step.get("activity", step.get("scheduled_activity", "")))
    if _is_sleep_activity(activity):
        return
    if _is_income_activity(activity, ""):
        return
    if not _should_seek_income(agent, cfg):
        return
    next_activity = _pick_income_activity(context, agent)
    if not next_activity:
        return
    step["activity"] = next_activity
    step["change_reason"] = "wealth_pursuit_income_seek"
    step["economy_forced_income"] = True


def on_agent_post_step(context):
    cfg = _get_cfg(context)
    runtime = _economy_state(context)
    if not runtime.get("enabled", False):
        return
    agent = context.get("agent", {})
    step = context.get("step", {})
    if not isinstance(agent, dict) or not isinstance(step, dict):
        return
    econ = agent.get("economy", {})
    if not isinstance(econ, dict):
        return

    activity = str(step.get("activity", ""))
    action = str(step.get("action", ""))
    location = str(step.get("location", ""))
    if _is_sleep_activity(activity):
        return
    hours = _step_hours(context, cfg)
    income = 0.0
    if _is_income_activity(activity, action) or bool(step.get("economy_forced_income", False)):
        effort = 1.0 + 0.45 * _to_float(econ.get("wealth_drive", 0.5), 0.5) + 0.25 * _to_float(econ.get("income_skill", 0.5), 0.5)
        volatility = random.uniform(-_to_float(econ.get("income_volatility", 0.25), 0.25), _to_float(econ.get("income_volatility", 0.25), 0.25))
        income = max(0.0, _to_float(econ.get("hourly_income", 0.0), 0.0) * hours * effort * (1.0 + volatility))
        if random.random() < 0.10 + 0.20 * _to_float(econ.get("wealth_drive", 0.5), 0.5):
            income += _to_float(econ.get("hourly_income", 0.0), 0.0) * 0.5
    if income > 0:
        _record_income(econ, income)

    expense_map = _estimate_behavior_expenses(agent, activity, action, location, hours, cfg)
    for category, amount in expense_map.items():
        _record_expense(econ, category, amount)

    _update_econ_security(agent)
    net = _to_float(econ.get("daily_income", 0.0), 0.0) - _to_float(econ.get("daily_expense", 0.0), 0.0)
    line = (
        f"[EconomyStep D{context.get('day', '')} {context.get('time_str', '')}] "
        f"income={income:.2f} expense={sum(expense_map.values()):.2f} net_today={net:.2f} "
        f"balance={econ.get('balance', 0.0):.2f}\n"
    )
    _add_daily_log(context, agent, line)


def on_day_end(context):
    cfg = _get_cfg(context)
    runtime = _economy_state(context)
    if not runtime.get("enabled", False):
        return
    day = int(_to_float(context.get("day", 0), 0))
    for agent in context.get("agents", []):
        if not isinstance(agent, dict):
            continue
        econ = agent.get("economy", {})
        if not isinstance(econ, dict):
            continue

        daily_income = _to_float(econ.get("daily_income", 0.0), 0.0)
        daily_expense = _to_float(econ.get("daily_expense", 0.0), 0.0)
        net = daily_income - daily_expense
        drive = _to_float(econ.get("wealth_drive", 0.5), 0.5)
        if net < 0 and drive >= _to_float(cfg.get("wealth_drive_seek_threshold", 0.65), 0.65):
            scale = abs(net) / max(1.0, _to_float(econ.get("income_target_daily", 80.0), 80.0))
            growth = _clip(scale * _to_float(cfg.get("income_growth_when_deficit", 0.08), 0.08) * drive, 0.0, 0.20)
            econ["base_hourly_income"] = _to_float(econ.get("base_hourly_income", 10.0), 10.0) * (1.0 + growth)
            econ["income_skill"] = _clip(_to_float(econ.get("income_skill", 0.5), 0.5) + 0.02 * drive, 0.0, 1.0)
        econ["income_target_daily"] = max(
            40.0,
            _to_float(econ.get("base_hourly_income", 8.0), 8.0) * _to_float(cfg.get("target_work_hours_per_day", 7.0), 7.0) * (0.90 + 0.35 * drive),
        )
        _update_econ_security(agent)
        _save_agent_economy(context, agent, cfg)

        runtime["day_rows"].append(
            {
                "day": day,
                "agent_id": agent.get("id"),
                "income": round(daily_income, 4),
                "expense": round(daily_expense, 4),
                "net": round(net, 4),
                "balance": round(_to_float(econ.get("balance", 0.0), 0.0), 4),
                "wealth_drive": round(drive, 4),
                "hourly_income": round(_to_float(econ.get("hourly_income", 0.0), 0.0), 4),
                "econ_security": round(_to_float(agent.get("state", {}).get("econ_security", 0.5), 0.5), 4),
            }
        )

        summary = (
            f"[EconomyDayEnd D{day}] income={daily_income:.2f} expense={daily_expense:.2f} "
            f"net={net:.2f} balance={econ.get('balance', 0.0):.2f} "
            f"drive={drive:.2f} target_daily={econ.get('income_target_daily', 0.0):.2f}\n"
        )
        _add_daily_log(context, agent, summary)


def on_simulation_end(context):
    cfg = _get_cfg(context)
    runtime = _economy_state(context)
    if not runtime.get("enabled", False):
        return
    output_dir = cfg.get("output_dir", "output/economy")
    os.makedirs(output_dir, exist_ok=True)

    day_rows = runtime.get("day_rows", [])
    if day_rows:
        daily_path = os.path.join(output_dir, "daily_ledger.csv")
        with open(daily_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "day",
                    "agent_id",
                    "income",
                    "expense",
                    "net",
                    "balance",
                    "wealth_drive",
                    "hourly_income",
                    "econ_security",
                ],
            )
            writer.writeheader()
            writer.writerows(day_rows)
        per_agent_rows = defaultdict(list)
        for row in day_rows:
            agent_id = row.get("agent_id")
            if agent_id is None:
                continue
            per_agent_rows[int(agent_id)].append(row)
        agents_dir = os.path.join(output_dir, "agents")
        os.makedirs(agents_dir, exist_ok=True)
        for agent_id, rows in per_agent_rows.items():
            path = os.path.join(agents_dir, f"agent_{agent_id}_ledger.csv")
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "day",
                        "agent_id",
                        "income",
                        "expense",
                        "net",
                        "balance",
                        "wealth_drive",
                        "hourly_income",
                        "econ_security",
                    ],
                )
                writer.writeheader()
                writer.writerows(rows)

    snapshot_path = os.path.join(output_dir, "wealth_snapshot.csv")
    snapshot_json_dir = os.path.join(output_dir, "agents")
    os.makedirs(snapshot_json_dir, exist_ok=True)
    with open(snapshot_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "agent_id",
                "currency",
                "balance",
                "lifetime_income",
                "lifetime_expense",
                "wealth_drive",
                "base_hourly_income",
                "hourly_income",
                "income_target_daily",
            ],
        )
        writer.writeheader()
        for agent in context.get("agents", []):
            econ = agent.get("economy", {})
            if not isinstance(econ, dict):
                continue
            agent_row = {
                "agent_id": agent.get("id"),
                "currency": econ.get("currency", cfg.get("currency", "CNY")),
                "balance": round(_to_float(econ.get("balance", 0.0), 0.0), 4),
                "lifetime_income": round(_to_float(econ.get("lifetime_income", 0.0), 0.0), 4),
                "lifetime_expense": round(_to_float(econ.get("lifetime_expense", 0.0), 0.0), 4),
                "wealth_drive": round(_to_float(econ.get("wealth_drive", 0.0), 0.0), 4),
                "base_hourly_income": round(_to_float(econ.get("base_hourly_income", 0.0), 0.0), 4),
                "hourly_income": round(_to_float(econ.get("hourly_income", 0.0), 0.0), 4),
                "income_target_daily": round(_to_float(econ.get("income_target_daily", 0.0), 0.0), 4),
            }
            writer.writerow(agent_row)
            agent_id = agent_row["agent_id"]
            if agent_id is None:
                continue
            json_path = os.path.join(snapshot_json_dir, f"agent_{agent_id}_snapshot.json")
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(
                    {
                        "agent_id": agent_id,
                        "name": agent.get("name", ""),
                        "economy": econ,
                    },
                    jf,
                    ensure_ascii=False,
                    indent=2,
                )
