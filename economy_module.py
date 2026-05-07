"""Economy module – realistic personal finance simulation for GAWorld.

Refactored to model the Chinese personal economic system with:
  1. Progressive income tax (个人所得税) & social insurance (五险一金)
  2. Engel-coefficient-based consumption allocation
  3. Multi-account system (checking / savings / investment / housing-fund)
  4. Investment & savings behaviour driven by risk preference
  5. Macro-economic cycles & micro-economic shock events

Hook interface is unchanged: on_simulation_start / on_day_start /
on_agent_pre_step / on_agent_post_step / on_day_end / on_simulation_end.
"""

import csv
import json
import math
import os
import random
from collections import defaultdict
from copy import deepcopy

# ---------------------------------------------------------------------------
# 1. DEFAULT CONFIGURATION
# ---------------------------------------------------------------------------

DEFAULT_ECONOMY_CONFIG = {
    "enabled": True,
    "currency": "CNY",
    "output_dir": "output/economy",
    "state_file_prefix": "agent_",
    "state_file_suffix": "_economy.json",
    "hours_per_step": 1.0,

    # --- Initial assets ---
    "initial_savings_months_min": 1.0,
    "initial_savings_months_max": 6.0,
    "inheritance_enabled": True,
    "inheritance_base_probability": 0.28,
    "inheritance_age_peak_low": 30,
    "inheritance_age_peak_high": 55,
    "inheritance_ratio_min": 0.25,
    "inheritance_ratio_max": 2.00,
    "inheritance_hukou_bonus": {
        "urban": 0.04, "city": 0.04, "town": 0.02,
        "rural": -0.03, "village": -0.03,
    },

    # --- Salary & income ---
    "min_hourly_income": 8.0,
    "income_volatility": 0.25,
    "target_work_hours_per_day": 7.0,
    "work_days_per_month": 22,
    "work_hours_per_day": 8,

    # --- Tax (China 2024 progressive brackets) ---
    "tax": {
        "enabled": True,
        "monthly_exemption": 5000.0,
        # Additional special deductions (租房/子女/赡养老人/etc), per-agent override
        "default_special_deduction": 1500.0,
        "brackets": [
            # (upper_bound, rate, quick_deduction)
            (3000,   0.03,    0),
            (12000,  0.10,  210),
            (25000,  0.20, 1410),
            (35000,  0.25, 2660),
            (55000,  0.30, 4410),
            (80000,  0.35, 7160),
            (float("inf"), 0.45, 15160),
        ],
    },

    # --- Social insurance (个人缴纳部分 typical rates) ---
    "social_insurance": {
        "enabled": True,
        "pension_rate": 0.08,          # 养老保险 8%
        "medical_rate": 0.02,          # 医疗保险 2%
        "unemployment_rate": 0.005,    # 失业保险 0.5%
        "work_injury_rate": 0.0,       # 工伤 (employer only)
        "maternity_rate": 0.0,         # 生育 (employer only)
        "housing_fund_rate": 0.08,     # 住房公积金 8%
        # Employer matching (for housing fund balance accumulation)
        "housing_fund_employer_rate": 0.08,
        # Social insurance base salary cap (3x local average, Hangzhou ~36000)
        "base_cap": 36000.0,
        "base_floor": 4462.0,
    },

    # --- Spending & Engel coefficient ---
    "spending": {
        # Engel coefficient by income quintile (monthly net income thresholds)
        "engel_curve": [
            # (net_income_up_to, engel_coefficient, savings_rate)
            (4000,   0.48, 0.05),   # low income
            (7000,   0.38, 0.15),   # lower-middle
            (12000,  0.30, 0.25),   # middle
            (20000,  0.22, 0.32),   # upper-middle
            (float("inf"), 0.15, 0.40),  # high income
        ],
        # Budget allocation template (% of total consumption, rest goes to misc)
        "budget_template": {
            "food":       0.30,   # adjusted by engel
            "housing":    0.25,   # rent + utilities
            "transport":  0.10,
            "clothing":   0.06,
            "leisure":    0.10,
            "education":  0.08,
            "healthcare": 0.06,
            "misc":       0.05,
        },
        # Income elasticity of demand per category
        "income_elasticity": {
            "food":       0.5,    # necessity – low elasticity
            "housing":    0.8,
            "transport":  0.7,
            "clothing":   1.2,    # luxury-leaning
            "leisure":    1.5,    # luxury
            "education":  1.1,
            "healthcare": 0.6,    # necessity
            "misc":       1.0,
        },
        "daily_variance": 0.25,  # random variance on daily spending
    },

    # --- Investment & savings ---
    "investment": {
        "enabled": True,
        # Annual return rates (mean, std_dev) for each asset class
        "asset_returns": {
            "deposits":  (0.025, 0.005),    # 定期存款 ~2.5%
            "funds":     (0.06,  0.08),      # 基金 ~6% mean, volatile
            "stocks":    (0.08,  0.22),      # 股票 ~8% mean, very volatile
        },
        # Default portfolio allocation by risk tolerance level
        "portfolio_profiles": {
            "conservative": {"deposits": 0.70, "funds": 0.25, "stocks": 0.05},
            "moderate":     {"deposits": 0.40, "funds": 0.40, "stocks": 0.20},
            "aggressive":   {"deposits": 0.15, "funds": 0.35, "stocks": 0.50},
        },
        # Monthly auto-transfer from checking to savings/investment
        "auto_save_enabled": True,
        # Threshold: keep this many months of expenses in checking
        "checking_buffer_months": 2.0,
    },

    # --- Economic cycle (macro environment) ---
    "macro": {
        "enabled": True,
        "initial_inflation_rate": 0.025,    # annual
        "initial_unemployment_rate": 0.052,
        "cycle_phase_duration_days": (60, 180),  # how long each phase lasts
        "phases": ["expansion", "peak", "contraction", "trough"],
        "phase_effects": {
            "expansion":   {"income_mult": 1.05, "expense_mult": 1.02, "layoff_risk": 0.002, "raise_chance": 0.03},
            "peak":        {"income_mult": 1.08, "expense_mult": 1.06, "layoff_risk": 0.005, "raise_chance": 0.02},
            "contraction": {"income_mult": 0.95, "expense_mult": 1.04, "layoff_risk": 0.015, "raise_chance": 0.005},
            "trough":      {"income_mult": 0.90, "expense_mult": 0.98, "layoff_risk": 0.025, "raise_chance": 0.002},
        },
        # Industry-specific boom/bust modifiers
        "industry_conditions": {
            "tech":     1.0,
            "finance":  1.0,
            "medical":  1.0,
            "education": 1.0,
            "service":  1.0,
            "trade":    1.0,
            "default":  1.0,
        },
    },

    # --- Shock events ---
    "shocks": {
        "enabled": True,
        # Per-agent daily probability of each shock type
        "layoff_base_prob": 0.001,
        "raise_base_prob": 0.008,
        "medical_emergency_prob": 0.0005,
        "medical_cost_range": (2000.0, 50000.0),
        "bonus_month_prob": 0.0,   # set > 0 for random bonuses outside year-end
        # Year-end bonus (13th month salary)
        "year_end_bonus_enabled": True,
        "year_end_bonus_months": 1.0,  # typically 1-3 months
    },

    # --- Behavior triggers (backward compat) ---
    "rent_income_ratio": 0.22,
    "daily_utilities_cost": 12.0,
    "base_living_cost_per_hour": 6.0,
    "asset_safety_days": 18.0,
    "income_seek_threshold": 0.56,
    "income_seek_probability_scale": 0.9,
    "wealth_drive_seek_threshold": 0.65,
    "income_growth_when_deficit": 0.08,
    "income_seek_activities": ["工作", "兼职", "接单", "技能提升"],
    "expense_ranges": {
        "food": [8.0, 26.0], "clothing": [18.0, 120.0],
        "transport": [3.0, 28.0], "housing": [0.0, 0.0],
        "leisure": [8.0, 70.0], "education": [10.0, 60.0],
        "healthcare": [12.0, 90.0], "misc": [4.0, 22.0],
    },
}

# ---------------------------------------------------------------------------
# 2. KEYWORD TABLES
# ---------------------------------------------------------------------------

INCOME_KEYWORDS = [
    "工作", "上班", "加班", "开会", "办公", "通勤", "接单",
    "兼职", "经营", "摆摊", "授课", "学习", "复习", "训练",
]
SLEEP_KEYWORDS = ["睡", "就寝", "休息"]

EXPENSE_KEYWORDS = {
    "food":      ["吃", "饭", "餐", "做饭", "买菜", "外卖", "咖啡", "奶茶"],
    "clothing":  ["衣", "鞋", "穿搭", "服饰", "购物"],
    "transport": ["通勤", "出行", "地铁", "公交", "打车", "骑行", "步行", "开车"],
    "housing":   ["房租", "租房", "物业", "水电", "家务", "居住"],
    "leisure":   ["娱乐", "游戏", "电影", "逛街", "聚会", "旅行", "放松"],
    "education": ["学习", "课程", "培训", "阅读", "写作", "练习"],
    "healthcare":["医院", "看病", "药", "体检", "治疗", "康复", "健身"],
}

JOB_INCOME_BANDS = [
    (["医生", "律师", "金融", "证券", "架构", "总监", "管理"], 75.0, 150.0),
    (["工程", "研发", "程序", "算法", "产品", "设计", "教师", "会计"], 38.0, 90.0),
    (["销售", "客服", "运营", "行政", "司机", "物流", "店员", "服务"], 18.0, 55.0),
    (["学生", "失业", "待业", "退休", "无业"], 8.0, 22.0),
]

# Map job keywords to industry for macro conditions
JOB_INDUSTRY_MAP = {
    "tech":     ["程序", "算法", "研发", "工程", "架构", "产品", "设计"],
    "finance":  ["金融", "证券", "会计", "银行", "投资", "保险"],
    "medical":  ["医生", "护士", "医院", "医疗", "药", "康复"],
    "education":["教师", "教授", "培训", "授课", "学校"],
    "service":  ["销售", "客服", "运营", "行政", "司机", "物流", "店员", "服务"],
    "trade":    ["经营", "摆摊", "批发", "零售", "电商"],
}

# ---------------------------------------------------------------------------
# 3. UTILITY HELPERS
# ---------------------------------------------------------------------------

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


def _infer_industry(agent):
    """Map agent's job to an industry key for macro condition lookup."""
    job = str(agent.get("job", ""))
    for industry, keywords in JOB_INDUSTRY_MAP.items():
        if _contains_any(job, keywords):
            return industry
    return "default"


def _add_daily_log(context, agent, line):
    daily_logs = context.get("daily_logs")
    if isinstance(daily_logs, dict):
        agent_id = agent["id"]
        daily_logs[agent_id] = daily_logs.get(agent_id, "") + line
    _append_agent_log(context, agent["id"], line)


# ---------------------------------------------------------------------------
# 4. TAX & SOCIAL INSURANCE CALCULATOR
# ---------------------------------------------------------------------------

def calc_social_insurance(gross_monthly, cfg):
    """Calculate individual social insurance deductions.

    Returns (total_deduction, breakdown_dict, housing_fund_total).
    housing_fund_total includes both individual and employer contribution.
    """
    si_cfg = cfg.get("social_insurance", {})
    if not si_cfg.get("enabled", True):
        return 0.0, {}, 0.0

    base = _clip(gross_monthly,
                 _to_float(si_cfg.get("base_floor", 4462), 4462),
                 _to_float(si_cfg.get("base_cap", 36000), 36000))

    pension    = base * _to_float(si_cfg.get("pension_rate", 0.08), 0.08)
    medical    = base * _to_float(si_cfg.get("medical_rate", 0.02), 0.02)
    unemploy   = base * _to_float(si_cfg.get("unemployment_rate", 0.005), 0.005)
    hf_indiv   = base * _to_float(si_cfg.get("housing_fund_rate", 0.08), 0.08)
    hf_employer= base * _to_float(si_cfg.get("housing_fund_employer_rate", 0.08), 0.08)

    total = pension + medical + unemploy + hf_indiv
    breakdown = {
        "pension": round(pension, 2),
        "medical": round(medical, 2),
        "unemployment": round(unemploy, 2),
        "housing_fund_individual": round(hf_indiv, 2),
    }
    housing_fund_monthly = hf_indiv + hf_employer
    return round(total, 2), breakdown, round(housing_fund_monthly, 2)


def calc_income_tax(gross_monthly, si_deduction, cfg, special_deduction=None):
    """Calculate monthly personal income tax (个税).

    taxable = gross - si_deduction - exemption - special_deductions
    Then apply 7-bracket progressive rate.

    Returns tax_amount.
    """
    tax_cfg = cfg.get("tax", {})
    if not tax_cfg.get("enabled", True):
        return 0.0

    exemption = _to_float(tax_cfg.get("monthly_exemption", 5000), 5000)
    spec_ded  = _to_float(
        special_deduction if special_deduction is not None
        else tax_cfg.get("default_special_deduction", 1500),
        1500
    )
    taxable = gross_monthly - si_deduction - exemption - spec_ded
    if taxable <= 0:
        return 0.0

    brackets = tax_cfg.get("brackets", DEFAULT_ECONOMY_CONFIG["tax"]["brackets"])
    for upper, rate, quick_ded in brackets:
        if taxable <= upper:
            return max(0.0, round(taxable * rate - quick_ded, 2))
    # Should not reach here, but just in case
    last = brackets[-1]
    return max(0.0, round(taxable * last[1] - last[2], 2))


def calc_net_monthly_salary(gross_monthly, cfg, special_deduction=None):
    """Full pipeline: gross -> SI deduction -> tax -> net salary.

    Returns (net, tax, si_total, si_breakdown, housing_fund_monthly).
    """
    si_total, si_breakdown, hf_monthly = calc_social_insurance(gross_monthly, cfg)
    tax = calc_income_tax(gross_monthly, si_total, cfg, special_deduction)
    net = gross_monthly - si_total - tax
    return round(max(0.0, net), 2), round(tax, 2), si_total, si_breakdown, hf_monthly


# ---------------------------------------------------------------------------
# 5. ENGEL COEFFICIENT & SPENDING PROFILE
# ---------------------------------------------------------------------------

def _engel_params(net_monthly, cfg):
    """Look up Engel coefficient and savings rate from income curve."""
    spending_cfg = cfg.get("spending", {})
    curve = spending_cfg.get("engel_curve",
                             DEFAULT_ECONOMY_CONFIG["spending"]["engel_curve"])
    for threshold, engel, save_rate in curve:
        if net_monthly <= threshold:
            return engel, save_rate
    # Above highest bracket
    last = curve[-1]
    return last[1], last[2]


def _build_monthly_budget(net_monthly, engel_coeff, savings_rate, cfg):
    """Allocate monthly consumption budget across categories.

    total_consumption = net_monthly * (1 - savings_rate)
    Food share is set by Engel coefficient; other categories are scaled
    proportionally from the budget template, with income elasticity applied.
    """
    spending_cfg = cfg.get("spending", {})
    template = spending_cfg.get("budget_template",
                                DEFAULT_ECONOMY_CONFIG["spending"]["budget_template"])
    elasticity = spending_cfg.get("income_elasticity",
                                  DEFAULT_ECONOMY_CONFIG["spending"]["income_elasticity"])

    consumption = net_monthly * (1.0 - _clip(savings_rate, 0.0, 0.90))
    food_amount = consumption * _clip(engel_coeff, 0.05, 0.70)

    # Remaining budget for non-food categories
    remaining = consumption - food_amount
    if remaining <= 0:
        budget = {cat: 0.0 for cat in template}
        budget["food"] = round(food_amount, 2)
        return budget

    # Compute weighted shares for non-food categories
    # Use income elasticity: higher income -> more on luxury categories
    reference_income = 8000.0  # middle reference point
    income_ratio = max(0.3, net_monthly / reference_income)

    non_food_cats = {k: v for k, v in template.items() if k != "food"}
    raw_shares = {}
    for cat, base_share in non_food_cats.items():
        e = _to_float(elasticity.get(cat, 1.0), 1.0)
        # Elasticity adjustment: luxury goods grow faster with income
        adjusted = base_share * (income_ratio ** (e - 1.0))
        raw_shares[cat] = max(0.001, adjusted)

    total_raw = sum(raw_shares.values())
    budget = {"food": round(food_amount, 2)}
    for cat, raw in raw_shares.items():
        budget[cat] = round(remaining * (raw / total_raw), 2)

    return budget


# ---------------------------------------------------------------------------
# 6. INVESTMENT & SAVINGS
# ---------------------------------------------------------------------------

def _infer_portfolio_type(agent):
    """Map agent's risk_preference to a portfolio profile name."""
    state = agent.get("state", {}) if isinstance(agent, dict) else {}
    risk = _to_float(state.get("risk_preference", 0.5), 0.5)
    if risk < 0.35:
        return "conservative"
    elif risk < 0.65:
        return "moderate"
    else:
        return "aggressive"


def _get_portfolio_weights(agent, cfg):
    """Get portfolio allocation weights for the agent."""
    inv_cfg = cfg.get("investment", {})
    profiles = inv_cfg.get("portfolio_profiles",
                           DEFAULT_ECONOMY_CONFIG["investment"]["portfolio_profiles"])
    ptype = _infer_portfolio_type(agent)
    return profiles.get(ptype, profiles.get("moderate", {"deposits": 0.5, "funds": 0.3, "stocks": 0.2}))


def _simulate_monthly_investment_return(investment_balance, portfolio_weights, cfg, macro_state=None):
    """Simulate one month of investment returns.

    Returns (return_amount, per_asset_returns_dict).
    """
    inv_cfg = cfg.get("investment", {})
    if not inv_cfg.get("enabled", True) or investment_balance <= 0:
        return 0.0, {}

    asset_returns = inv_cfg.get("asset_returns",
                                DEFAULT_ECONOMY_CONFIG["investment"]["asset_returns"])

    # Macro environment affects returns
    macro_mult = 1.0
    if macro_state and isinstance(macro_state, dict):
        phase = macro_state.get("phase", "expansion")
        phase_effects = cfg.get("macro", {}).get("phase_effects", {})
        effects = phase_effects.get(phase, {})
        # Investment returns correlate with economic cycle
        macro_mult = _to_float(effects.get("income_mult", 1.0), 1.0)

    total_return = 0.0
    per_asset = {}
    for asset_class, weight in portfolio_weights.items():
        if weight <= 0:
            continue
        params = asset_returns.get(asset_class, (0.02, 0.01))
        annual_mean = _to_float(params[0], 0.02) * macro_mult
        annual_std  = _to_float(params[1], 0.01)
        # Convert annual to monthly
        monthly_mean = annual_mean / 12.0
        monthly_std  = annual_std / math.sqrt(12.0)
        monthly_return_rate = random.gauss(monthly_mean, monthly_std)
        allocated = investment_balance * weight
        ret = allocated * monthly_return_rate
        per_asset[asset_class] = round(ret, 2)
        total_return += ret

    return round(total_return, 2), per_asset


def _monthly_savings_transfer(econ, cfg):
    """Auto-transfer excess checking balance to savings/investment.

    Keep `checking_buffer_months` worth of monthly expenses in checking;
    move the rest according to savings_rate split.
    """
    inv_cfg = cfg.get("investment", {})
    if not inv_cfg.get("auto_save_enabled", True):
        return 0.0, 0.0  # (to_savings, to_investment)

    accounts = econ.get("accounts", {})
    checking = _to_float(accounts.get("checking", 0), 0)
    monthly_expense = _to_float(econ.get("monthly_expense_estimate", 0), 0)
    buffer_months = _to_float(inv_cfg.get("checking_buffer_months", 2.0), 2.0)
    buffer = monthly_expense * buffer_months

    excess = checking - buffer
    if excess <= 0:
        return 0.0, 0.0

    # Split: more conservative agents put more into savings
    risk = _to_float(econ.get("risk_tolerance", 0.5), 0.5)
    invest_ratio = _clip(0.2 + 0.5 * risk, 0.1, 0.7)
    to_invest = round(excess * invest_ratio, 2)
    to_savings = round(excess - to_invest, 2)

    accounts["checking"] = round(checking - to_savings - to_invest, 2)
    accounts["savings"]  = round(_to_float(accounts.get("savings", 0), 0) + to_savings, 2)
    accounts["investment"] = round(_to_float(accounts.get("investment", 0), 0) + to_invest, 2)

    return to_savings, to_invest


# ---------------------------------------------------------------------------
# 7. MACRO ECONOMIC CYCLE
# ---------------------------------------------------------------------------

def _init_macro_state(cfg):
    """Initialize macro economic state for the simulation."""
    macro_cfg = cfg.get("macro", {})
    if not macro_cfg.get("enabled", True):
        return {"enabled": False}

    dur_range = macro_cfg.get("cycle_phase_duration_days", (60, 180))
    return {
        "enabled": True,
        "phase": "expansion",
        "phase_day_counter": 0,
        "phase_duration": random.randint(
            int(_to_float(dur_range[0], 60)),
            int(_to_float(dur_range[1], 180))
        ),
        "inflation_rate": _to_float(macro_cfg.get("initial_inflation_rate", 0.025), 0.025),
        "unemployment_rate": _to_float(macro_cfg.get("initial_unemployment_rate", 0.052), 0.052),
        "industry_conditions": deepcopy(macro_cfg.get("industry_conditions",
                                                       DEFAULT_ECONOMY_CONFIG["macro"]["industry_conditions"])),
        "cumulative_inflation": 1.0,  # price level index (starts at 1.0)
    }


def _advance_macro_cycle(macro_state, cfg):
    """Advance macro cycle by one day; possibly transition phase."""
    if not macro_state.get("enabled", False):
        return

    macro_state["phase_day_counter"] = macro_state.get("phase_day_counter", 0) + 1
    duration = macro_state.get("phase_duration", 120)

    if macro_state["phase_day_counter"] >= duration:
        # Transition to next phase
        phases = cfg.get("macro", {}).get("phases",
                                          DEFAULT_ECONOMY_CONFIG["macro"]["phases"])
        current = macro_state.get("phase", "expansion")
        idx = phases.index(current) if current in phases else 0
        next_idx = (idx + 1) % len(phases)
        macro_state["phase"] = phases[next_idx]
        macro_state["phase_day_counter"] = 0
        dur_range = cfg.get("macro", {}).get("cycle_phase_duration_days", (60, 180))
        macro_state["phase_duration"] = random.randint(
            int(_to_float(dur_range[0], 60)),
            int(_to_float(dur_range[1], 180))
        )

        # Adjust inflation & unemployment based on new phase
        phase = macro_state["phase"]
        if phase == "expansion":
            macro_state["inflation_rate"] *= random.uniform(0.95, 1.05)
            macro_state["unemployment_rate"] *= random.uniform(0.92, 0.98)
        elif phase == "peak":
            macro_state["inflation_rate"] *= random.uniform(1.02, 1.10)
            macro_state["unemployment_rate"] *= random.uniform(0.95, 1.02)
        elif phase == "contraction":
            macro_state["inflation_rate"] *= random.uniform(0.90, 1.02)
            macro_state["unemployment_rate"] *= random.uniform(1.05, 1.15)
        elif phase == "trough":
            macro_state["inflation_rate"] *= random.uniform(0.85, 0.98)
            macro_state["unemployment_rate"] *= random.uniform(1.00, 1.08)

        macro_state["inflation_rate"] = _clip(macro_state["inflation_rate"], 0.001, 0.15)
        macro_state["unemployment_rate"] = _clip(macro_state["unemployment_rate"], 0.02, 0.20)

        # Shuffle industry conditions slightly
        for ind in macro_state.get("industry_conditions", {}):
            shift = random.uniform(-0.08, 0.08)
            macro_state["industry_conditions"][ind] = _clip(
                macro_state["industry_conditions"][ind] + shift, 0.5, 1.5)

    # Daily inflation accumulation
    daily_inflation = macro_state["inflation_rate"] / 365.0
    macro_state["cumulative_inflation"] = macro_state.get("cumulative_inflation", 1.0) * (1.0 + daily_inflation)


def _macro_income_multiplier(macro_state, industry, cfg):
    """Get income multiplier from macro state for a given industry."""
    if not macro_state or not macro_state.get("enabled", False):
        return 1.0
    phase = macro_state.get("phase", "expansion")
    phase_effects = cfg.get("macro", {}).get("phase_effects", {})
    effects = phase_effects.get(phase, {})
    base_mult = _to_float(effects.get("income_mult", 1.0), 1.0)
    industry_cond = _to_float(
        macro_state.get("industry_conditions", {}).get(industry, 1.0), 1.0)
    return base_mult * industry_cond


def _macro_expense_multiplier(macro_state, cfg):
    """Get expense multiplier from inflation and cycle phase."""
    if not macro_state or not macro_state.get("enabled", False):
        return 1.0
    phase = macro_state.get("phase", "expansion")
    phase_effects = cfg.get("macro", {}).get("phase_effects", {})
    effects = phase_effects.get(phase, {})
    return _to_float(effects.get("expense_mult", 1.0), 1.0)


# ---------------------------------------------------------------------------
# 8. SHOCK EVENTS
# ---------------------------------------------------------------------------

def _check_daily_shocks(agent, econ, cfg, macro_state):
    """Check and apply daily random economic shocks.

    Returns list of shock event dicts (may be empty).
    """
    shocks_cfg = cfg.get("shocks", {})
    if not shocks_cfg.get("enabled", True):
        return []

    events = []
    phase_effects = {}
    if macro_state and macro_state.get("enabled", False):
        phase = macro_state.get("phase", "expansion")
        phase_effects = cfg.get("macro", {}).get("phase_effects", {}).get(phase, {})

    # --- Layoff risk ---
    layoff_prob = _to_float(shocks_cfg.get("layoff_base_prob", 0.001), 0.001)
    layoff_prob += _to_float(phase_effects.get("layoff_risk", 0), 0)
    # Higher econ_security slightly reduces layoff impact
    state = agent.get("state", {}) if isinstance(agent, dict) else {}
    econ_sec = _to_float(state.get("econ_security", 0.5), 0.5)
    layoff_prob *= (1.2 - 0.4 * econ_sec)

    if random.random() < layoff_prob:
        # Layoff: income drops significantly for a period
        income_cut = random.uniform(0.5, 0.85)
        econ["base_hourly_income"] = max(
            _to_float(cfg.get("min_hourly_income", 8.0), 8.0),
            _to_float(econ.get("base_hourly_income", 0), 0) * (1.0 - income_cut)
        )
        econ["_layoff_days_remaining"] = random.randint(30, 90)
        events.append({
            "type": "layoff",
            "income_cut_pct": round(income_cut * 100, 1),
            "recovery_days": econ["_layoff_days_remaining"],
        })

    # --- Raise / promotion ---
    if not econ.get("_layoff_days_remaining", 0):
        raise_prob = _to_float(shocks_cfg.get("raise_base_prob", 0.008), 0.008)
        raise_prob += _to_float(phase_effects.get("raise_chance", 0), 0)
        raise_prob *= (0.7 + 0.6 * _to_float(econ.get("income_skill", 0.5), 0.5))
        if random.random() < raise_prob:
            raise_pct = random.uniform(0.05, 0.25)
            econ["base_hourly_income"] = _to_float(econ.get("base_hourly_income", 0), 0) * (1.0 + raise_pct)
            econ["gross_monthly_salary"] = _to_float(econ.get("gross_monthly_salary", 0), 0) * (1.0 + raise_pct)
            events.append({"type": "raise", "raise_pct": round(raise_pct * 100, 1)})

    # --- Medical emergency ---
    med_prob = _to_float(shocks_cfg.get("medical_emergency_prob", 0.0005), 0.0005)
    if random.random() < med_prob:
        cost_range = shocks_cfg.get("medical_cost_range", (2000.0, 50000.0))
        raw_cost = _rand_between(cost_range)
        # Medical insurance reimburses part of it
        si_cfg = cfg.get("social_insurance", {})
        reimbursement_rate = 0.0
        if si_cfg.get("enabled", True):
            reimbursement_rate = random.uniform(0.50, 0.85)
        out_of_pocket = raw_cost * (1.0 - reimbursement_rate)
        accounts = econ.get("accounts", {})
        accounts["checking"] = round(
            _to_float(accounts.get("checking", 0), 0) - out_of_pocket, 2)
        econ["daily_expense"] = _to_float(econ.get("daily_expense", 0), 0) + out_of_pocket
        cats = econ.get("daily_expense_by_category", {})
        cats["healthcare"] = _to_float(cats.get("healthcare", 0), 0) + out_of_pocket
        events.append({
            "type": "medical_emergency",
            "total_cost": round(raw_cost, 2),
            "reimbursed": round(raw_cost * reimbursement_rate, 2),
            "out_of_pocket": round(out_of_pocket, 2),
        })

    # --- Layoff recovery countdown ---
    remaining = econ.get("_layoff_days_remaining", 0)
    if remaining > 0:
        econ["_layoff_days_remaining"] = remaining - 1
        if remaining - 1 <= 0:
            # Recover: re-seek employment at slightly lower base
            econ.pop("_layoff_days_remaining", None)
            events.append({"type": "layoff_recovery"})

    return events


# ---------------------------------------------------------------------------
# 9. AGENT PROFILE INFERENCE (backward compat + enhanced)
# ---------------------------------------------------------------------------

def _infer_wealth_drive(agent):
    state = agent.get("state", {}) if isinstance(agent, dict) else {}
    base = 0.45
    base += 0.25 * _to_float(state.get("risk_preference", 0.5), 0.5)
    base += 0.15 * _to_float(state.get("stress", 0.5), 0.5)
    personality = " ".join(
        str(agent.get(key, "")) for key in ("personality", "values", "daily_life", "job")
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


def _age_inheritance_factor(age, low=30, high=55):
    years = int(_to_float(age, 30))
    peak_low = int(_to_float(low, 30))
    peak_high = int(_to_float(high, 55))
    if years < peak_low:
        return max(0.0, years / max(1.0, peak_low))
    if years <= peak_high:
        return 1.0
    decay = 1.0 - ((years - peak_high) / 45.0)
    return _clip(decay, 0.35, 1.0)


def _infer_inheritance_amount(agent, cfg, baseline_monthly_income):
    if not bool(cfg.get("inheritance_enabled", True)):
        return 0.0
    base_prob = _to_float(cfg.get("inheritance_base_probability", 0.28), 0.28)
    state = agent.get("state", {}) if isinstance(agent, dict) else {}
    risk_preference = _to_float(state.get("risk_preference", 0.5), 0.5)
    age = int(_to_float(agent.get("age", 30), 30))
    age_factor = _age_inheritance_factor(
        age, low=cfg.get("inheritance_age_peak_low", 30),
        high=cfg.get("inheritance_age_peak_high", 55))
    profile_blob = " ".join(
        str(agent.get(k, "")) for k in ("hukou", "residence", "living", "values", "daily_life")
    ).lower()
    hukou_bonus_cfg = cfg.get("inheritance_hukou_bonus", {})
    hukou_bonus = 0.0
    if isinstance(hukou_bonus_cfg, dict):
        for key, delta in hukou_bonus_cfg.items():
            if str(key).strip().lower() and str(key).strip().lower() in profile_blob:
                hukou_bonus += _to_float(delta, 0.0)
    prob = base_prob * (0.72 + 0.55 * age_factor) + 0.04 * (risk_preference - 0.5) + hukou_bonus
    prob = _clip(prob, 0.0, 0.92)
    if random.random() > prob:
        return 0.0
    ratio_min = _to_float(cfg.get("inheritance_ratio_min", 0.25), 0.25)
    ratio_max = _to_float(cfg.get("inheritance_ratio_max", 2.0), 2.0)
    if ratio_max < ratio_min:
        ratio_min, ratio_max = ratio_max, ratio_min
    return max(0.0, baseline_monthly_income * random.uniform(ratio_min, ratio_max))


# ---------------------------------------------------------------------------
# 10. EMPTY CATEGORY DICT
# ---------------------------------------------------------------------------

def _empty_daily_categories():
    return {
        "food": 0.0, "clothing": 0.0, "housing": 0.0,
        "transport": 0.0, "leisure": 0.0, "education": 0.0,
        "healthcare": 0.0, "misc": 0.0,
    }


# ---------------------------------------------------------------------------
# 11. RECORD HELPERS
# ---------------------------------------------------------------------------

def _record_income(econ, amount):
    value = max(0.0, _to_float(amount, 0.0))
    econ["daily_income"] += value
    econ["lifetime_income"] += value
    accounts = econ.get("accounts", {})
    accounts["checking"] = round(_to_float(accounts.get("checking", 0), 0) + value, 2)


def _record_expense(econ, category, amount):
    value = max(0.0, _to_float(amount, 0.0))
    econ["daily_expense"] += value
    econ["lifetime_expense"] += value
    accounts = econ.get("accounts", {})
    accounts["checking"] = round(_to_float(accounts.get("checking", 0), 0) - value, 2)
    if category not in econ["daily_expense_by_category"]:
        econ["daily_expense_by_category"][category] = 0.0
    econ["daily_expense_by_category"][category] += value


def _total_balance(econ):
    """Sum all liquid accounts (checking + savings + investment). Excludes housing fund."""
    accounts = econ.get("accounts", {})
    return round(
        _to_float(accounts.get("checking", 0), 0)
        + _to_float(accounts.get("savings", 0), 0)
        + _to_float(accounts.get("investment", 0), 0),
        2
    )


def _sync_balance(econ):
    """Keep the legacy 'balance' field in sync with accounts."""
    econ["balance"] = _total_balance(econ)


# ---------------------------------------------------------------------------
# 12. STATE PERSISTENCE
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 13. AGENT ECONOMY INITIALIZATION
# ---------------------------------------------------------------------------

def _init_agent_economy(agent, cfg, context):
    saved = _load_agent_economy(context, agent["id"], cfg)
    if saved:
        saved.setdefault("daily_expense_by_category", _empty_daily_categories())
        saved.setdefault("currency", cfg["currency"])
        saved.setdefault("accounts", {})
        agent["economy"] = saved
        return

    job = str(agent.get("job", ""))
    low, high = _job_income_band(job)
    income_skill = _infer_income_skill(agent)
    wealth_drive = _infer_wealth_drive(agent)
    state = agent.get("state", {}) if isinstance(agent, dict) else {}

    # Base hourly income
    base_hourly_income = random.uniform(low, high) * (0.75 + 0.55 * income_skill)
    base_hourly_income = max(_to_float(cfg.get("min_hourly_income", 8.0), 8.0), base_hourly_income)

    # Derive gross monthly salary from hourly
    work_hours = _to_float(cfg.get("work_hours_per_day", 8), 8)
    work_days  = _to_float(cfg.get("work_days_per_month", 22), 22)
    gross_monthly = base_hourly_income * work_hours * work_days

    # Calculate net salary with tax & social insurance
    net_monthly, tax, si_total, si_breakdown, hf_monthly = calc_net_monthly_salary(gross_monthly, cfg)

    # Engel coefficient & spending profile
    engel_coeff, savings_rate = _engel_params(net_monthly, cfg)
    monthly_budget = _build_monthly_budget(net_monthly, engel_coeff, savings_rate, cfg)

    # Monthly rent based on housing budget (or fallback to ratio)
    housing_budget = _to_float(monthly_budget.get("housing", 0), 0)
    if housing_budget > 600:
        monthly_rent = housing_budget * random.uniform(0.85, 1.15)
    else:
        monthly_rent = gross_monthly * _to_float(cfg.get("rent_income_ratio", 0.22), 0.22) * random.uniform(0.85, 1.15)
    monthly_rent = max(600.0, monthly_rent)

    # Initial assets
    init_months = random.uniform(
        _to_float(cfg.get("initial_savings_months_min", 1.0), 1.0),
        _to_float(cfg.get("initial_savings_months_max", 6.0), 6.0))
    labor_savings = net_monthly * init_months * (0.7 + 0.6 * _to_float(state.get("econ_security", 0.5), 0.5))
    inheritance_assets = _infer_inheritance_amount(agent, cfg, baseline_monthly_income=gross_monthly)
    init_balance = labor_savings + inheritance_assets

    # Distribute initial balance across accounts
    risk_tolerance = _to_float(state.get("risk_preference", 0.5), 0.5)
    checking_share = _clip(0.3 - 0.15 * risk_tolerance, 0.10, 0.40)
    invest_share   = _clip(0.1 + 0.30 * risk_tolerance, 0.05, 0.40)
    savings_share  = 1.0 - checking_share - invest_share

    # Housing fund: accumulated from prior employment
    age = int(_to_float(agent.get("age", 30), 30))
    work_years = max(0, age - 22)
    housing_fund_balance = hf_monthly * 12 * min(work_years, 15) * random.uniform(0.3, 0.7)

    # Income target
    income_target_daily = max(40.0, base_hourly_income * _to_float(cfg.get("target_work_hours_per_day", 7.0), 7.0))

    # Portfolio weights
    portfolio_weights = _get_portfolio_weights(agent, cfg)

    # Monthly expense estimate (for buffer calculations)
    monthly_expense_est = net_monthly * (1.0 - savings_rate)

    agent["economy"] = {
        "currency": cfg["currency"],
        "wealth_drive": round(_clip(wealth_drive, 0.0, 1.0), 4),
        "income_skill": round(_clip(income_skill, 0.0, 1.0), 4),
        "risk_tolerance": round(risk_tolerance, 4),
        "industry": _infer_industry(agent),

        # --- Salary ---
        "gross_monthly_salary": round(gross_monthly, 2),
        "net_monthly_salary": round(net_monthly, 2),
        "base_hourly_income": round(base_hourly_income, 2),
        "hourly_income": round(base_hourly_income, 2),
        "income_volatility": max(0.0, _to_float(cfg.get("income_volatility", 0.25), 0.25)),
        "income_target_daily": round(income_target_daily, 2),

        # --- Tax & social insurance (monthly) ---
        "monthly_tax": round(tax, 2),
        "monthly_si_total": round(si_total, 2),
        "monthly_si_breakdown": si_breakdown,
        "monthly_housing_fund": round(hf_monthly, 2),

        # --- Spending profile ---
        "engel_coefficient": round(engel_coeff, 4),
        "savings_rate": round(savings_rate, 4),
        "monthly_budget": monthly_budget,
        "monthly_expense_estimate": round(monthly_expense_est, 2),
        "monthly_rent": round(monthly_rent, 2),

        # --- Multi-account system ---
        "accounts": {
            "checking":     round(max(0.0, init_balance * checking_share), 2),
            "savings":      round(max(0.0, init_balance * savings_share), 2),
            "investment":   round(max(0.0, init_balance * invest_share), 2),
            "housing_fund": round(max(0.0, housing_fund_balance), 2),
        },
        "balance": round(max(0.0, init_balance), 2),  # backward compat (liquid total)

        # --- Investment ---
        "portfolio_type": _infer_portfolio_type(agent),
        "portfolio_weights": portfolio_weights,
        "investment_return_ytd": 0.0,

        # --- Initial assets record ---
        "initial_assets": {
            "labor_savings": round(max(0.0, labor_savings), 2),
            "inheritance": round(max(0.0, inheritance_assets), 2),
            "total": round(max(0.0, init_balance), 2),
        },

        # --- Daily tracking ---
        "daily_income": 0.0,
        "daily_expense": 0.0,
        "daily_expense_by_category": _empty_daily_categories(),
        "lifetime_income": 0.0,
        "lifetime_expense": 0.0,
        "last_location": "",

        # --- Shock tracking ---
        "shock_log": [],
    }
    _sync_balance(agent["economy"])
    _save_agent_economy(context, agent, cfg)


# ---------------------------------------------------------------------------
# 14. STEP HELPERS
# ---------------------------------------------------------------------------

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


def _estimate_behavior_expenses(agent, activity, action, location, hours, cfg, macro_state=None):
    """Estimate expenses for a single time step based on activity & spending profile."""
    econ = agent.get("economy", {})
    if not isinstance(econ, dict):
        return {}

    # Use monthly budget to derive daily allocation, then scale by hours
    monthly_budget = econ.get("monthly_budget", {})
    monthly_expense = _to_float(econ.get("monthly_expense_estimate", 0), 0)
    if monthly_expense <= 0:
        monthly_expense = 4000.0  # fallback

    # Macro expense multiplier (inflation + cycle)
    expense_mult = _macro_expense_multiplier(macro_state, cfg)

    spending_cfg = cfg.get("spending", {})
    variance = _to_float(spending_cfg.get("daily_variance", 0.25), 0.25)

    # Base hourly living cost from budget
    daily_budget_total = monthly_expense / 30.0
    hourly_cost = (daily_budget_total / 16.0) * max(hours, 0.1)  # ~16 waking hours
    hourly_cost *= expense_mult
    hourly_cost *= random.uniform(1.0 - variance, 1.0 + variance)

    result = {"misc": max(0.5, hourly_cost * 0.15)}

    # Activity-based expense allocation
    text = " ".join([str(activity or ""), str(action or ""), str(location or "")])
    for category, keywords in EXPENSE_KEYWORDS.items():
        if _contains_any(text, keywords):
            # Use budget proportion for this category
            cat_monthly = _to_float(monthly_budget.get(category, 0), 0)
            if cat_monthly > 0:
                daily_cat = (cat_monthly / 30.0) * random.uniform(0.5, 1.8) * expense_mult
                # Scale to step hours (assume most spending in ~4-5 activity hours per day)
                step_cat = daily_cat * (hours / 5.0)
                result[category] = result.get(category, 0.0) + max(1.0, step_cat)
                result["misc"] = max(0.0, result["misc"] - step_cat * 0.1)
            else:
                # Fallback to old range-based method
                amount = _rand_between(cfg.get("expense_ranges", {}).get(category, [0.0, 0.0]))
                if amount > 0:
                    result[category] = result.get(category, 0.0) + amount * expense_mult

    # Transport cost on location change — prefer real fare from travel plan
    if location and econ.get("last_location") and location != econ.get("last_location"):
        real_cost = _to_float(
            agent.get("locations", {}).get("travel_cost", 0), 0)
        if real_cost > 0:
            # Use the actual fare computed by city_map_system.calc_transport_cost
            move_cost = real_cost
        else:
            # Fallback: budget-based estimate
            transport_budget = _to_float(monthly_budget.get("transport", 0), 0)
            if transport_budget > 0:
                move_cost = (transport_budget / 30.0) * random.uniform(0.3, 1.2)
            else:
                move_cost = _rand_between(
                    cfg.get("expense_ranges", {}).get("transport", [3.0, 12.0]))
        result["transport"] = result.get("transport", 0.0) + move_cost * expense_mult
    econ["last_location"] = str(location or econ.get("last_location", ""))

    return result


def _update_econ_security(agent):
    econ = agent.get("economy", {})
    state = agent.get("state", {})
    if not isinstance(econ, dict) or not isinstance(state, dict):
        return
    # Use total balance across accounts for security assessment
    total = _total_balance(econ)
    hf = _to_float(econ.get("accounts", {}).get("housing_fund", 0), 0)
    effective_assets = total + hf * 0.3  # housing fund is partially accessible

    target = max(1.0, _to_float(econ.get("monthly_expense_estimate", 80.0 * 22), 1760) * 3.0)
    asset_score = _clip(effective_assets / target, 0.0, 3.0) / 3.0
    prev = _to_float(state.get("econ_security", 0.5), 0.5)
    state["econ_security"] = round(_clip(prev * 0.85 + (0.30 + 0.70 * asset_score) * 0.15, 0.0, 1.0), 4)


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
    # Laid-off agents always seek income
    if econ.get("_layoff_days_remaining", 0) > 0:
        return True
    drive = _to_float(econ.get("wealth_drive", 0.5), 0.5)
    target = max(1.0, _to_float(econ.get("income_target_daily", 80.0), 80.0))
    gap = max(0.0, target - _to_float(econ.get("daily_income", 0.0), 0.0)) / target
    safety_days = max(1.0, _to_float(cfg.get("asset_safety_days", 18.0), 18.0))
    daily_floor = max(1.0, _to_float(econ.get("daily_expense", 0.0), 0.0) + target * 0.4)
    safety_balance = daily_floor * safety_days
    balance = _total_balance(econ)
    asset_pressure = max(0.0, safety_balance - balance) / max(1.0, safety_balance)
    motive = drive * 0.55 + gap * 0.30 + asset_pressure * 0.25
    threshold = _to_float(cfg.get("income_seek_threshold", 0.56), 0.56)
    if motive < threshold:
        return False
    probability = _clip(motive * _to_float(cfg.get("income_seek_probability_scale", 0.9), 0.9), 0.0, 0.95)
    return random.random() < probability


# ---------------------------------------------------------------------------
# 15. HOOK: on_simulation_start
# ---------------------------------------------------------------------------

def on_simulation_start(context):
    cfg = _get_cfg(context)
    runtime = _economy_state(context)
    runtime["enabled"] = bool(cfg.get("enabled", True))
    if not runtime["enabled"]:
        return
    os.makedirs(cfg.get("output_dir", "output/economy"), exist_ok=True)
    _step_hours(context, cfg)

    # Initialize macro economic state
    runtime["macro"] = _init_macro_state(cfg)
    runtime["sim_month_counter"] = 0
    runtime["sim_day_counter"] = 0

    for agent in context.get("agents", []):
        if not isinstance(agent, dict) or "id" not in agent:
            continue
        _init_agent_economy(agent, cfg, context)
        econ = agent.get("economy", {})
        init_assets = econ.get("initial_assets", {}) if isinstance(econ.get("initial_assets"), dict) else {}
        accounts = econ.get("accounts", {})
        init_line = (
            f"[EconomyInit] gross_salary={econ.get('gross_monthly_salary', 0):.0f} "
            f"net_salary={econ.get('net_monthly_salary', 0):.0f} "
            f"tax={econ.get('monthly_tax', 0):.0f} si={econ.get('monthly_si_total', 0):.0f} "
            f"engel={econ.get('engel_coefficient', 0):.2f} "
            f"save_rate={econ.get('savings_rate', 0):.2f} "
            f"balance={econ.get('balance', 0):.0f} "
            f"(checking={accounts.get('checking', 0):.0f} "
            f"savings={accounts.get('savings', 0):.0f} "
            f"invest={accounts.get('investment', 0):.0f} "
            f"hf={accounts.get('housing_fund', 0):.0f}) "
            f"inheritance={_to_float(init_assets.get('inheritance', 0), 0):.0f}"
        )
        _append_agent_log(context, agent["id"], init_line)


# ---------------------------------------------------------------------------
# 16. HOOK: on_day_start
# ---------------------------------------------------------------------------

def on_day_start(context):
    cfg = _get_cfg(context)
    runtime = _economy_state(context)
    if not runtime.get("enabled", False):
        return

    # Advance macro cycle
    macro_state = runtime.get("macro", {})
    _advance_macro_cycle(macro_state, cfg)
    runtime["sim_day_counter"] = runtime.get("sim_day_counter", 0) + 1

    for agent in context.get("agents", []):
        econ = agent.get("economy", {})
        if not isinstance(econ, dict):
            continue

        # Reset daily counters
        econ["daily_income"] = 0.0
        econ["daily_expense"] = 0.0
        econ["daily_expense_by_category"] = _empty_daily_categories()

        # Daily income volatility
        base_hour = max(
            _to_float(cfg.get("min_hourly_income", 8.0), 8.0),
            _to_float(econ.get("base_hourly_income", 8.0), 8.0))
        volatility = _to_float(econ.get("income_volatility", cfg.get("income_volatility", 0.25)), 0.25)
        daily_shift = 1.0 + random.uniform(-volatility, volatility) * (1.0 - 0.35 * _to_float(econ.get("income_skill", 0.5), 0.5))

        # Apply macro income multiplier
        industry = econ.get("industry", "default")
        income_mult = _macro_income_multiplier(macro_state, industry, cfg)
        econ["hourly_income"] = round(max(
            _to_float(cfg.get("min_hourly_income", 8.0), 8.0),
            base_hour * daily_shift * income_mult
        ), 2)

        # Fixed daily expenses: rent + utilities (from monthly budget)
        housing = max(0.0, _to_float(econ.get("monthly_rent", 0.0), 0.0) / 30.0)
        utilities = max(0.0, _to_float(cfg.get("daily_utilities_cost", 12.0), 12.0))
        expense_mult = _macro_expense_multiplier(macro_state, cfg)
        if housing > 0:
            _record_expense(econ, "housing", housing * expense_mult)
        if utilities > 0:
            _record_expense(econ, "housing", utilities * expense_mult)

        # Check shock events
        shocks = _check_daily_shocks(agent, econ, cfg, macro_state)
        if shocks:
            econ.setdefault("shock_log", []).extend(shocks)

        _update_econ_security(agent)
        _sync_balance(econ)

        shock_str = ""
        if shocks:
            shock_str = " SHOCKS=" + ",".join(s["type"] for s in shocks)

        line = (
            f"[EconomyDayStart D{context.get('day', '')}] "
            f"phase={macro_state.get('phase', '?')} "
            f"fixed={housing + utilities:.1f} "
            f"hourly={econ.get('hourly_income', 0):.1f} "
            f"balance={econ.get('balance', 0):.0f}"
            f"{shock_str}\n"
        )
        _add_daily_log(context, agent, line)


# ---------------------------------------------------------------------------
# 17. HOOK: on_agent_pre_step
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 18. HOOK: on_agent_post_step
# ---------------------------------------------------------------------------

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
    macro_state = runtime.get("macro", {})

    # --- Income ---
    income = 0.0
    if _is_income_activity(activity, action) or bool(step.get("economy_forced_income", False)):
        effort = 1.0 + 0.45 * _to_float(econ.get("wealth_drive", 0.5), 0.5) + 0.25 * _to_float(econ.get("income_skill", 0.5), 0.5)
        vol = _to_float(econ.get("income_volatility", 0.25), 0.25)
        volatility = random.uniform(-vol, vol)
        income = max(0.0, _to_float(econ.get("hourly_income", 0.0), 0.0) * hours * effort * (1.0 + volatility))
        # Occasional bonus
        if random.random() < 0.10 + 0.20 * _to_float(econ.get("wealth_drive", 0.5), 0.5):
            income += _to_float(econ.get("hourly_income", 0.0), 0.0) * 0.5
    if income > 0:
        _record_income(econ, income)

    # --- Expenses ---
    expense_map = _estimate_behavior_expenses(agent, activity, action, location, hours, cfg, macro_state)
    for category, amount in expense_map.items():
        _record_expense(econ, category, amount)

    _update_econ_security(agent)
    _sync_balance(econ)

    net = _to_float(econ.get("daily_income", 0), 0) - _to_float(econ.get("daily_expense", 0), 0)
    line = (
        f"[EconomyStep D{context.get('day', '')} {context.get('time_str', '')}] "
        f"income={income:.1f} expense={sum(expense_map.values()):.1f} net_today={net:.1f} "
        f"balance={econ.get('balance', 0):.0f}\n"
    )
    _add_daily_log(context, agent, line)


# ---------------------------------------------------------------------------
# 19. HOOK: on_day_end
# ---------------------------------------------------------------------------

def on_day_end(context):
    cfg = _get_cfg(context)
    runtime = _economy_state(context)
    if not runtime.get("enabled", False):
        return

    day = int(_to_float(context.get("day", 0), 0))
    sim_day = runtime.get("sim_day_counter", 0)
    macro_state = runtime.get("macro", {})

    # Monthly settlement (every 30 sim days)
    is_month_end = (sim_day > 0 and sim_day % 30 == 0)
    if is_month_end:
        runtime["sim_month_counter"] = runtime.get("sim_month_counter", 0) + 1

    for agent in context.get("agents", []):
        if not isinstance(agent, dict):
            continue
        econ = agent.get("economy", {})
        if not isinstance(econ, dict):
            continue

        daily_income = _to_float(econ.get("daily_income", 0), 0)
        daily_expense = _to_float(econ.get("daily_expense", 0), 0)
        net = daily_income - daily_expense
        drive = _to_float(econ.get("wealth_drive", 0.5), 0.5)

        # Income growth on deficit (backward compat)
        if net < 0 and drive >= _to_float(cfg.get("wealth_drive_seek_threshold", 0.65), 0.65):
            scale = abs(net) / max(1.0, _to_float(econ.get("income_target_daily", 80.0), 80.0))
            growth = _clip(scale * _to_float(cfg.get("income_growth_when_deficit", 0.08), 0.08) * drive, 0.0, 0.20)
            econ["base_hourly_income"] = round(_to_float(econ.get("base_hourly_income", 10.0), 10.0) * (1.0 + growth), 2)
            econ["income_skill"] = round(_clip(_to_float(econ.get("income_skill", 0.5), 0.5) + 0.02 * drive, 0.0, 1.0), 4)

        # Update income target
        econ["income_target_daily"] = round(max(
            40.0,
            _to_float(econ.get("base_hourly_income", 8.0), 8.0)
            * _to_float(cfg.get("target_work_hours_per_day", 7.0), 7.0)
            * (0.90 + 0.35 * drive)
        ), 2)

        # --- Monthly settlement ---
        if is_month_end:
            # Recalculate tax & social insurance based on current gross salary
            gross = _to_float(econ.get("gross_monthly_salary", 0), 0)
            if gross > 0:
                net_sal, tax, si_total, si_bd, hf_monthly = calc_net_monthly_salary(gross, cfg)
                econ["net_monthly_salary"] = net_sal
                econ["monthly_tax"] = tax
                econ["monthly_si_total"] = si_total
                econ["monthly_si_breakdown"] = si_bd
                econ["monthly_housing_fund"] = hf_monthly

                # Housing fund accumulation
                accounts = econ.get("accounts", {})
                accounts["housing_fund"] = round(
                    _to_float(accounts.get("housing_fund", 0), 0) + hf_monthly, 2)

                # Recalculate spending profile
                engel, save_rate = _engel_params(net_sal, cfg)
                econ["engel_coefficient"] = round(engel, 4)
                econ["savings_rate"] = round(save_rate, 4)
                econ["monthly_budget"] = _build_monthly_budget(net_sal, engel, save_rate, cfg)
                econ["monthly_expense_estimate"] = round(net_sal * (1.0 - save_rate), 2)

            # Auto-transfer to savings/investment
            to_sav, to_inv = _monthly_savings_transfer(econ, cfg)

            # Investment returns
            inv_balance = _to_float(econ.get("accounts", {}).get("investment", 0), 0)
            portfolio = econ.get("portfolio_weights", {"deposits": 0.5, "funds": 0.3, "stocks": 0.2})
            inv_return, per_asset = _simulate_monthly_investment_return(
                inv_balance, portfolio, cfg, macro_state)
            if inv_return != 0:
                econ["accounts"]["investment"] = round(
                    _to_float(econ["accounts"].get("investment", 0), 0) + inv_return, 2)
                econ["investment_return_ytd"] = round(
                    _to_float(econ.get("investment_return_ytd", 0), 0) + inv_return, 2)

            # Year-end bonus (every 12 months)
            month_count = runtime.get("sim_month_counter", 0)
            shocks_cfg = cfg.get("shocks", {})
            if shocks_cfg.get("year_end_bonus_enabled", True) and month_count > 0 and month_count % 12 == 0:
                bonus_months = _to_float(shocks_cfg.get("year_end_bonus_months", 1.0), 1.0)
                bonus_gross = gross * bonus_months
                # Bonus tax (simplified: taxed as regular income)
                bonus_net = bonus_gross * 0.85  # approximate after-tax
                _record_income(econ, bonus_net)
                econ.setdefault("shock_log", []).append({
                    "type": "year_end_bonus",
                    "gross": round(bonus_gross, 2),
                    "net": round(bonus_net, 2),
                })

            month_line = (
                f"[EconomyMonth M{month_count}] "
                f"gross={gross:.0f} net={econ.get('net_monthly_salary', 0):.0f} "
                f"tax={econ.get('monthly_tax', 0):.0f} si={econ.get('monthly_si_total', 0):.0f} "
                f"hf_bal={econ.get('accounts', {}).get('housing_fund', 0):.0f} "
                f"inv_return={inv_return:.0f} "
                f"savings_xfer={to_sav:.0f} invest_xfer={to_inv:.0f}\n"
            )
            _add_daily_log(context, agent, month_line)

        _update_econ_security(agent)
        _sync_balance(econ)
        _save_agent_economy(context, agent, cfg)

        runtime["day_rows"].append({
            "day": day,
            "agent_id": agent.get("id"),
            "income": round(daily_income, 4),
            "expense": round(daily_expense, 4),
            "net": round(net, 4),
            "balance": round(_to_float(econ.get("balance", 0), 0), 4),
            "checking": round(_to_float(econ.get("accounts", {}).get("checking", 0), 0), 4),
            "savings": round(_to_float(econ.get("accounts", {}).get("savings", 0), 0), 4),
            "investment": round(_to_float(econ.get("accounts", {}).get("investment", 0), 0), 4),
            "housing_fund": round(_to_float(econ.get("accounts", {}).get("housing_fund", 0), 0), 4),
            "wealth_drive": round(drive, 4),
            "hourly_income": round(_to_float(econ.get("hourly_income", 0), 0), 4),
            "econ_security": round(_to_float(agent.get("state", {}).get("econ_security", 0.5), 0.5), 4),
            "engel_coefficient": round(_to_float(econ.get("engel_coefficient", 0), 0), 4),
            "macro_phase": macro_state.get("phase", "") if macro_state else "",
        })

        summary = (
            f"[EconomyDayEnd D{day}] income={daily_income:.1f} expense={daily_expense:.1f} "
            f"net={net:.1f} balance={econ.get('balance', 0):.0f} "
            f"drive={drive:.2f} engel={econ.get('engel_coefficient', 0):.2f}\n"
        )
        _add_daily_log(context, agent, summary)


# ---------------------------------------------------------------------------
# 20. HOOK: on_simulation_end
# ---------------------------------------------------------------------------

def on_simulation_end(context):
    cfg = _get_cfg(context)
    runtime = _economy_state(context)
    if not runtime.get("enabled", False):
        return
    output_dir = cfg.get("output_dir", "output/economy")
    os.makedirs(output_dir, exist_ok=True)

    day_rows = runtime.get("day_rows", [])
    day_fields = [
        "day", "agent_id", "income", "expense", "net", "balance",
        "checking", "savings", "investment", "housing_fund",
        "wealth_drive", "hourly_income", "econ_security",
        "engel_coefficient", "macro_phase",
    ]

    if day_rows:
        daily_path = os.path.join(output_dir, "daily_ledger.csv")
        with open(daily_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=day_fields)
            writer.writeheader()
            writer.writerows(day_rows)

        per_agent_rows = defaultdict(list)
        for row in day_rows:
            aid = row.get("agent_id")
            if aid is None:
                continue
            per_agent_rows[int(aid)].append(row)
        agents_dir = os.path.join(output_dir, "agents")
        os.makedirs(agents_dir, exist_ok=True)
        for aid, rows in per_agent_rows.items():
            path = os.path.join(agents_dir, f"agent_{aid}_ledger.csv")
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=day_fields)
                writer.writeheader()
                writer.writerows(rows)

    snapshot_path = os.path.join(output_dir, "wealth_snapshot.csv")
    snapshot_json_dir = os.path.join(output_dir, "agents")
    os.makedirs(snapshot_json_dir, exist_ok=True)
    snap_fields = [
        "agent_id", "currency", "balance",
        "checking", "savings", "investment", "housing_fund",
        "gross_monthly_salary", "net_monthly_salary",
        "monthly_tax", "monthly_si_total",
        "engel_coefficient", "savings_rate",
        "lifetime_income", "lifetime_expense",
        "wealth_drive", "base_hourly_income", "hourly_income",
        "income_target_daily", "portfolio_type",
        "investment_return_ytd",
        "initial_labor_savings", "initial_inheritance", "initial_assets_total",
    ]
    with open(snapshot_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=snap_fields)
        writer.writeheader()
        for agent in context.get("agents", []):
            econ = agent.get("economy", {})
            if not isinstance(econ, dict):
                continue
            init_assets = econ.get("initial_assets", {}) if isinstance(econ.get("initial_assets"), dict) else {}
            accounts = econ.get("accounts", {})
            agent_row = {
                "agent_id": agent.get("id"),
                "currency": econ.get("currency", cfg.get("currency", "CNY")),
                "balance": round(_to_float(econ.get("balance", 0), 0), 2),
                "checking": round(_to_float(accounts.get("checking", 0), 0), 2),
                "savings": round(_to_float(accounts.get("savings", 0), 0), 2),
                "investment": round(_to_float(accounts.get("investment", 0), 0), 2),
                "housing_fund": round(_to_float(accounts.get("housing_fund", 0), 0), 2),
                "gross_monthly_salary": round(_to_float(econ.get("gross_monthly_salary", 0), 0), 2),
                "net_monthly_salary": round(_to_float(econ.get("net_monthly_salary", 0), 0), 2),
                "monthly_tax": round(_to_float(econ.get("monthly_tax", 0), 0), 2),
                "monthly_si_total": round(_to_float(econ.get("monthly_si_total", 0), 0), 2),
                "engel_coefficient": round(_to_float(econ.get("engel_coefficient", 0), 0), 4),
                "savings_rate": round(_to_float(econ.get("savings_rate", 0), 0), 4),
                "lifetime_income": round(_to_float(econ.get("lifetime_income", 0), 0), 2),
                "lifetime_expense": round(_to_float(econ.get("lifetime_expense", 0), 0), 2),
                "wealth_drive": round(_to_float(econ.get("wealth_drive", 0), 0), 4),
                "base_hourly_income": round(_to_float(econ.get("base_hourly_income", 0), 0), 2),
                "hourly_income": round(_to_float(econ.get("hourly_income", 0), 0), 2),
                "income_target_daily": round(_to_float(econ.get("income_target_daily", 0), 0), 2),
                "portfolio_type": econ.get("portfolio_type", ""),
                "investment_return_ytd": round(_to_float(econ.get("investment_return_ytd", 0), 0), 2),
                "initial_labor_savings": round(_to_float(init_assets.get("labor_savings", 0), 0), 2),
                "initial_inheritance": round(_to_float(init_assets.get("inheritance", 0), 0), 2),
                "initial_assets_total": round(_to_float(init_assets.get("total", 0), 0), 2),
            }
            writer.writerow(agent_row)
            aid = agent_row["agent_id"]
            if aid is None:
                continue
            json_path = os.path.join(snapshot_json_dir, f"agent_{aid}_snapshot.json")
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump({
                    "agent_id": aid,
                    "name": agent.get("name", ""),
                    "economy": econ,
                }, jf, ensure_ascii=False, indent=2)

    # Save macro state summary
    macro_state = runtime.get("macro", {})
    if macro_state:
        macro_path = os.path.join(output_dir, "macro_state.json")
        with open(macro_path, "w", encoding="utf-8") as f:
            json.dump(macro_state, f, ensure_ascii=False, indent=2)
