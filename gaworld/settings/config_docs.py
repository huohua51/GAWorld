"""Per-key documentation for the CONFIG tree, for the dashboard 配置 panel.

The config tree has ~600 leaves spread across the fragments in this package.
A hand-written catalogue for all of them would be longer than the settings
modules themselves and would go stale the first time someone adds a knob, so
the help text comes from two sources merged at read time:

* **The comments already sitting above each key in ``gaworld/settings/*.py``.**
  Those comments *are* this project's config documentation — extracting them
  costs one AST walk and can never drift from the code it describes. A key
  gets the comment block immediately above it, or its trailing inline comment.
* **A curated override table** (:data:`MANUAL_HELP`) for the knobs an operator
  actually reaches for, where the source comment is missing, English-only, or
  written for a maintainer rather than for the person turning the dial.

Manual text wins over extracted text. Following the convention already set by
``site/dashboard/external.js``: a help string says *what changes if you change
this*, not what the key is named. "仿真天数：仿真的天数" is worth nothing.

Labels are resolved full-path-first, then by last segment, because the same
leaf name means different things in different subtrees (``timeout`` under a
provider is an HTTP timeout; ``enabled`` is everywhere).
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from functools import lru_cache
from pathlib import Path
from typing import Any

from .behavior import human_realism_settings, intervention_settings, news_settings
from .economy import economy_settings
from .environment import environment_settings
from .integrations import integration_settings
from .llm import llm_settings
from .runtime import simulation_settings

_SETTINGS_DIR = Path(__file__).resolve().parent

#: Longest help string served to the browser. Some source comments are
#: multi-paragraph design notes; a tooltip that fills the viewport is worse
#: than a truncated one.
_MAX_HELP_CHARS = 420


# ---------------------------------------------------------------------------
# Sections — one per config fragment, so the grouping cannot drift from the
# code. ``build_default_config`` composes exactly these, in this order.
# ---------------------------------------------------------------------------

#: ``(id, module, factory, title, help)``. ``factory`` is called to learn which
#: top-level CONFIG keys belong to the section.
SECTIONS: tuple[tuple[str, str, Any, str, str], ...] = (
    (
        "simulation",
        "runtime",
        simulation_settings,
        "仿真运行",
        "一次运行的骨架：跑几天、跑哪些居民、时间怎么推进、记忆存哪、日程有多大概率被打乱。"
        "改这里等于换一次实验的设定，不影响正在跑的那一轮。",
    ),
    (
        "llm",
        "llm",
        llm_settings,
        "语言模型",
        "智能体用哪个大模型思考。providers 是可选的后端清单，routing 决定实际派给谁；"
        "密钥不在这里，在下面的「环境变量」里。",
    ),
    (
        "environment",
        "environment",
        environment_settings,
        "环境与感知",
        "居民能感知到的世界：所在地点挤不挤、异常事件算不算异常、外部环境服务从哪拿天气"
        "和新闻、多机之间怎么中继。",
    ),
    (
        "news",
        "behavior",
        news_settings,
        "新闻与主动检索",
        "居民从外界读到什么：刷新闻的概率、主动上网搜索的频率和搜索引擎、抓回来的正文"
        "有多少会写进记忆。",
    ),
    (
        "intervention",
        "behavior",
        intervention_settings,
        "推荐与干预评估",
        "信息流实验用的一层：推荐条数、毒性/不实内容的抑制阈值、立场更新速度。全部是"
        "确定性计算，不额外调模型。",
    ),
    (
        "human_realism",
        "behavior",
        human_realism_settings,
        "人的真实性",
        "让居民像人：兴趣会成长也会遗忘、目标分三层并定期复盘、习惯靠重复养成、"
        "疲劳饥饿会打断计划。",
    ),
    (
        "economy",
        "economy",
        economy_settings,
        "经济系统",
        "钱的规则：个税、社保、消费结构、投资收益、信贷、宏观周期。改的是下一次运行的"
        "规则；要动正在跑的那一轮，去「外部系统 → 货币系统」排干预。",
    ),
    (
        "integrations",
        "integrations",
        integration_settings,
        "扩展与真实工作",
        "仿真往外接的部分：自定义扩展钩子、多人协作会话、以及把「工作」类活动派给本地"
        "适配器真的产出文件的 real_work 子系统。",
    ),
)

#: Top-level CONFIG keys that exist only because ``data/environment_config.json``
#: injects them — no Python fragment declares them, so :func:`section_index`
#: cannot place them. They are the weather/news generator settings, and users
#: look for those under 环境, not in a catch-all bucket.
SECTION_EXTRA_KEYS: dict[str, tuple[str, ...]] = {
    "environment": (
        "external_environment",
        "external_environment_service",
        "environment",
    ),
}


# ---------------------------------------------------------------------------
# Curated overrides
# ---------------------------------------------------------------------------

#: Full dotted path -> help text. Wins over the extracted source comment.
MANUAL_HELP: dict[str, str] = {
    # ---- 仿真运行 ----
    "agent_ids": "参与本次仿真的居民编号。留一个数字 N 表示取前 N 位居民；写成列表就是精确指定这几位。人越多，一天的 LLM 调用越多。",
    "sim_days": "跑几个仿真日。天数直接决定总成本和总时长。",
    "seconds_per_day": "一个仿真日折算成多少真实秒。只在「实时等待」打开时才真的等；关掉时它只影响回放动画的节奏。",
    "simulate_realtime": "打开后仿真会按真实时间等待，像看直播；关掉则以 CPU/模型能跑多快就跑多快。做实验一般关掉。",
    "print_agent_profile": "开跑前把每位居民的人物设定打印到终端。调试用，日志会很长。",
    "time_step_minutes": "日内推进的时间粒度。留空表示只在日程写明的时刻推进；填 60 就是每小时一步——步长越小，一天的 LLM 调用越多。",
    "time_grid_snap": "把所有人的日程都对齐到上面的时间格。不开时，总时刻数是「网格 ∪ 每个人自己的时间点」，人一多刻数就爆炸；开了就固定在 1440/步长，这是 100 人以上跑得起的前提。代价是日内时间会被挪动。",
    "long_run": "长时段快进：一天压缩成一条「日简报」（每人每天一次调用），跳过日内循环。60/600 天这种尺度必须开，代价是日内细节全部消失。",
    "long_run.enabled": "打开快进模式。跑 60 天以上时不开基本跑不完。",
    "long_run.brief_llm": "日简报用模型写（贵、有细节）还是按规则拼（零调用、干巴）。",
    "long_run.max_state_delta": "快进时单日状态最多变化多少。防止一天之内情绪从 0.2 跳到 0.9。",
    "long_run.randomness": "快进期间的随机程度：越高，突发事件越频繁、日间状态波动越大。0 = 完全确定，同种子必然复现。",
    "long_run.brief_max_chars": "每条日简报的字数上限，超了会被截断。",
    "calendar": "仿真日历：从哪天开始、开局是周几、哪几天算周末。周末会改变日程模板和外出概率。",
    "calendar.start_date": "开局日期。填 today 表示用今天的真实日期。",
    "calendar.start_weekday": "第 1 天是周几。会连带决定后面哪些天落在周末。",
    "calendar.weekend_days": "哪几天算周末。周末的日程模板和活动权重与工作日不同。",
    "external_rag": "把外部资料喂给居民的通道：开局灌一批背景信息，运行中还可以持续吸收。",
    "external_rag.top_k": "每次回忆时最多召回几条外部资料。调大会挤占提示词里留给个人记忆的位置。",
    "external_rag.bootstrap": "开跑前给每位居民灌一批背景资料，避免第一天所有人都像刚出生。",
    "external_rag.runtime_absorb": "运行中每到日界再抓一小批与当前成长目标相关的新资料。默认关，开了会增加联网请求。",
    "background": "整个世界的时代背景，会进入每一次思考的提示词。改它等于换一个社会环境设定。",
    "csv_path": "居民初始状态表（九个 0–1 变量）。改路径等于换一批人。",
    "md_path": "居民人物设定文档。Agent Studio 编辑的就是这个文件。",
    "map_path": "虚拟地图定义文件，仅在 map_mode = virtual 时使用。",
    "map_mode": "用程序生成的网格地图（virtual），还是真实杭州的 OSM 路网（real）。real 更真实，但需要先跑脚本把地图数据抓下来。",
    "real_map_path": "真实地图数据包路径，仅在 map_mode = real 时使用。缺文件会退回虚拟地图。",
    "stateful": "跨轮次保留记忆。关掉后每次运行都从空白记忆开始，适合做干净的对照实验。",
    "memory_dir": "记忆与向量库的落盘目录。换目录等于换一套记忆，旧的还在。",
    "log_dir": "运行日志目录。",
    "diary_output_dir": "每位居民每天的日记输出目录。",
    "environment_output_dir": "环境事件的输出目录。",
    "visualization": "轨迹可视化：是否记录每帧位置、写到哪、多久刷一次盘。",
    "visualization.flush_every_frames": "攒够多少帧才写一次文件。调小更实时但磁盘写得更频繁。",
    "environment_config_path": "环境配置文件的位置。注意：这个文件会在最后再覆盖一次 CONFIG，所以它里面写了的项，改上面的没用。",
    "memory_model_version": "记忆格式版本号。它一变就说明旧记忆不兼容，需要先 reset 一次。",
    "require_clean_reset_on_memory_model_change": "记忆格式变了却没重置时直接报错，而不是拿旧记忆硬跑出一堆诡异结果。",
    "vector_db_path": "记忆向量库文件。删掉它等于清空全部长期记忆。",
    "vector_db_dim": "向量维度。改了之后旧库不可用，必须重建。",
    "vector_db_top_k": "每次检索返回几条记忆。调大提示词更长、更贵。",
    "vector_db_max_chars": "单条记忆入库时的字数上限。",
    "vector_db_embedding_provider": "怎么把文字变成向量：hash 是零依赖但很粗糙的哈希词袋；llm 调用模型的 embedding 接口，检索质量高但每条都要花钱。",
    "memory": "记忆机制：回忆时怎么打分、多久整理一次、什么时候开始遗忘。",
    "memory.salience_weight": "回忆打分时把「这件事有多重要」和「过去多久」算进去，而不是只看文字相似度。关掉即退回纯相似度。",
    "memory.decay_halflife_days": "记忆权重的半衰期（天）。越小，越容易只想起最近的事。",
    "memory.growth_boost": "和当前成长目标相关的记忆会被排到更前面。",
    "memory.consolidation": "定期把最近的零散经历总结成一条长期记忆，模拟「睡一觉整理一下」。",
    "memory.decay": "定期把很久没想起、又不重要的记忆删掉，防止记忆库无限膨胀。",
    "memory.skill_consolidation": "定期把反复做成的事沉淀成一条私人技能。",
    "skills": "技能库：公共技能从哪读，要不要塞进思考和工作提示词，一次最多塞几条。",
    "policy_events": "预先排好的政策事件。到点自动触发，用来做「有政策 / 无政策」对照实验。",
    "life_events": "针对个人的生活事件队列。仿真跑着的时候也能从面板往里加，下一个 tick 就会被消费。",
    "life_events.severity_state_amplify": "事件严重度对状态冲击的放大系数。0 = 不论多严重，状态影响都一样。",
    "life_events.reshape": "严重事件当天直接改写后面的日程，而不是只掷一次「要不要改计划」的骰子——不然一个高承诺度的活动总会赢，出了大事人还在照常上班。",
    "life_events.aftermath": "严重事件的余波会延续好几天并逐日衰减，作为「你还没缓过来」写进后面几天的计划约束。",
    "routine_change": "居民有多大概率临时偏离既定日程。",
    "routine_change.enabled": "关掉后所有人严格照日程执行，像上了发条。",
    "routine_change.base_chance": "没有任何事发生时，每个时刻临时改计划的基础概率。",
    "routine_change.event_boost": "身边发生事件时，改计划概率往上加多少。",
    "routine_change.policy_boost": "有政策事件时，改计划概率往上加多少。",
    "routine_change.max_chance": "改计划概率的上限，防止叠加到「几乎必然乱套」。",
    "routine_change.randomness": "总的「日程有多松」旋钮，0–1。越高越随性：高承诺活动更容易被放弃、无端的躁动更多。0 = 严格按调好的默认值走。睡觉时段不受影响。",
    "routine_change.severity_pivot": "事件严重度超过这个值才开始推动改计划。低于它的小事按 0 计。",
    "daily_planning": "每天早上怎么排当天的日程。",
    "daily_planning.autoregressive": "以昨天的实际安排为底稿排今天，变化会一天天累积；关掉则每天回到固定模板，等于每天重置人生。",
    "daily_planning.flexible.min_anchor_match": "新排的日程至少要有多大比例贴着基准锚点才被接受，否则打回基准。调低 = 日子更自由但也更飘。",
    "spontaneity": "自发性：会不会突然冒出念头、临时起意做点别的。压力、疲劳、饥饿都会把这些概率往上推。",
    "concurrency": "并行度。默认串行以保证同种子可复现；开并行会快，但日内顺序不再严格一致。",
    "concurrency.day_routine_workers": "每日日程生成阶段的并发线程数。受限于模型服务端的并发能力。",
    # ---- 语言模型 ----
    "llm": "多后端模型配置：providers 是可用后端清单，routing 决定哪个任务派给谁。",
    "llm.providers": "可用的模型后端清单。密钥通过环境变量注入，不写在这里。",
    "llm.routing": "任务怎么派给模型。",
    "llm.routing.default": "没有单独指定的任务都用这个后端。它决定了绝大部分成本。",
    "llm.routing.tasks": "给个别任务单独指定后端，比如把排日程这种量大又不需要聪明的活派给便宜的本地模型。",
    "model_name": "旧版单模型字段，只在没走 llm.routing 的老代码路径上生效。",
    "ollama_url": "旧版 Ollama 地址，只在没走 llm.routing 的老代码路径上生效。",
    "llm_timeout": "旧版全局超时（秒）。新代码用各 provider 自己的 timeout。",
    # ---- 环境 ----
    "local_physical": "居民对当前所在地点的感知：挤不挤、开没开门。关掉后人对周围环境一无所知。",
    "anomaly": "什么才算「异常」。普通的下雨和小幅行情波动不算；极端天气、突发事故、高严重度事件才算。这里只调「怎么判定异常」，判定之后反应有多大是写死在行为代码里的。",
    "distributed": "多机联跑：本机负责哪些居民、对端有哪些、消息怎么中继。单机跑用不到。",
    # ---- 新闻 ----
    "news.enabled": "关掉后居民完全不看新闻，外部世界对他们不可见。",
    "news.use_cache_first": "优先用缓存的新闻而不是每次真的联网。省时间省配额，代价是内容不新。",
    "news.daily_chance": "每位居民每天看新闻的概率。",
    "news.max_reads_per_day": "每人每天最多读几条，防止一个人刷一整天。",
    "news.info_seek": "主动检索：不只是被动刷到，还会自己去搜。这是联网请求的大头。",
    "news.info_seek.engines": "按顺序尝试的搜索引擎。x 需要配 Token，没配会被静默跳过。",
    # ---- 干预 ----
    "intervention.enabled": "关掉后推荐与干预这一层完全不参与，信息流按原样呈现。",
    "intervention.exposure_control": "把毒性/不实内容的曝光压下去。阈值越低压得越狠。",
    "intervention.stance.alpha": "立场更新的惯性：越接近 1 越不容易被单条内容说服。",
    # ---- 人的真实性 ----
    "interests": "兴趣与技能成长：会新增、会练熟，也会因为长期不碰而退步。",
    "interests.decay": "长期不练的兴趣会掉级。grace_days 是宽限期，练得越多越不容易忘。",
    "interests.evolution": "兴趣本身会换：老的退役，新的从朋友那里「传染」过来。",
    "goals": "三层目标（人生 / 长期 / 短期），它是每日日程的上游——日程排什么，取决于当前目标是什么。",
    "goals.review_interval_days": "隔多少天做一次目标复盘。复盘会调用模型，间隔越短越贵。",
    "goals.event_review_severity": "严重度超过这个值的事件会立刻触发一次计划外复盘，不等到下个周期。",
    "goals.max_reviews_per_day": "每个仿真日最多做几次周期性复盘（事件触发的不受限）。超出的人排到第二天，防止大规模人口在同一天集体烧钱。",
    "human_realism": "经验积累与习惯/需求动力学的总开关及其参数。",
    "human_realism.llm.max_extra_calls_per_agent_day": "为了「更真实」每人每天最多额外调用几次模型。这是成本闸门。",
    "human_realism.memory.recall": "各个环节（计划、行动、反思、采访）各召回几条记忆。全都调大 = 提示词全面变长。",
    "human_realism.behavior.habit_learning_rate": "习惯养成的速度。越大，重复几次就固化成习惯。",
    "human_realism.behavior.habit_min_occurrences": "同一情境重复几次才算习惯。设成 1 的话，一次意外也会被当成习惯。",
    "human_realism.behavior.inertia_weight": "惯性权重：越大越倾向于继续做正在做的事。",
    "human_realism.behavior.decision_noise": "决策噪声：越大越不可预测，也越不像有稳定人格。",
    "human_realism.behavior.commitment_weights": "高/中/低承诺度的活动各有多难被打断。",
    "human_realism.behavior.need_weights": "精力、饥饿、社交需求三者谁更容易打断当前活动。",
    "dynamic_behavior": "自发冲动、偶遇、需求打断、环境触发的临时改变——关掉后人会显得很按部就班。",
    # ---- 集成 ----
    "extensions": "自定义扩展钩子，写成 \"模块:函数\"。strict 打开时钩子加载失败会直接终止，而不是静默跳过。",
    "collaboration": "多人协作会话（讨论、合作任务）的并发数、上下文长度和重试次数。",
    "collaboration.max_concurrent_sessions": "同时进行的协作会话数。每个会话都在烧模型调用，这是成本闸门。",
    "collaboration.discussion.default_rounds": "一场讨论默认几轮。轮数直接乘上参与人数等于总调用数。",
    "real_work": "真实工作执行：把「工作」类活动派给本地适配器，真的产出代码/文案/设计文件到 artifacts_dir。",
    "real_work.enabled": "关掉后「工作」只是日程上的一个词，不会产出任何文件。",
    "real_work.max_concurrent_tasks": "同时执行的真实任务数。",
    "real_work.task_timeout_seconds": "单个任务的超时。卡住的任务会在这之后被放弃。",
    "real_work.market": "模拟的接活市场：居民可以去浏览并接任务。",
    "real_work.external_hooks": "把任务转发到外部 webhook 或 MCP 服务。留空表示只在本地跑。",
    # ---- 经济 ----
    "economy": "钱的全套规则。这里改的是下一次运行的初始条件；要动正在跑的那一轮，去「外部系统 → 货币系统」排一次干预。",
    "economy.enabled": "关掉后居民没有账户、不发工资也不花钱，经济这一层完全不参与。",
    "economy.hours_per_step": "一个仿真步折算多少工时。它同时决定挣多少和花多少，改动会等比放大整个经济的节奏。",
    "economy.initial_savings_months_min": "开局存款下限，按「几个月的支出」算。和上限一起决定了开局的贫富起点。",
    "economy.initial_savings_months_max": "开局存款上限，按「几个月的支出」算。",
    "economy.inheritance_enabled": "让一部分人开局就有家底。关掉后所有人从同一条起跑线出发，贫富差距只能靠仿真过程拉开。",
    "economy.tax": "个人所得税。brackets 是税率表，每行 [本级上限, 税率, 速算扣除数]，最后一行的上限是无穷大。",
    "economy.tax.monthly_exemption": "每月起征点，收入减掉它之后才计税。",
    "economy.social_insurance": "五险一金的个人缴纳比例。它直接从工资里扣，是「税前工资」和「到手工资」的主要差额。",
    "economy.spending": "怎么花钱。engel_curve 是收入越高、食品占比越低的经验曲线，每行 [收入, 食品占比, 储蓄率]。",
    "economy.investment": "投资收益模型：各类资产的均值/波动，以及保守/稳健/激进三种组合画像。",
    "economy.credit": "信贷：能借多少（按月收入的倍数）、年利率多少。利率越高，欠债的人越难翻身。",
    "economy.macro": "宏观周期：扩张 → 顶峰 → 收缩 → 谷底循环。不同阶段的涨薪和裁员概率不一样。",
    "economy.macro.initial_inflation_rate": "年通胀率。注意它只作用在支出侧——工资不跟涨，所以长期跑下来居民会越来越买不起东西。",
    "economy.macro.initial_unemployment_rate": "一个景气指标，本身不会让谁丢工作；真正决定裁员的是各阶段的 layoff_risk。",
    "economy.shocks": "个体层面的意外：裁员、涨薪、医疗急症。概率是每人每期的。",
    "economy.routing": "居民花出去的钱流向谁：商户的劳动分成进企业池，房租进房东，其余按规则分配。",
    "economy.friend_loans": "熟人之间借钱的规则：最多欠几个月、出借方要留多少缓冲、有多大意愿借。",
    "economy.sectors": "企业池 / 政府池 / 银行池的初始余额。这三个池子加上所有居民账户构成系统总货币，正常情况下总量守恒。",
    "economy.rent_income_ratio": "房租占收入的比例，是大多数居民最大的一笔固定支出。",
    "economy.income_seek_threshold": "资产低到什么程度就开始主动找钱。越高，居民越早为钱发愁。",
    # ---- 外部环境生成器（来自 environment_config.json）----
    "external_environment": "每天生成天气、行情、政策、科技新闻的那台机器。这些事件会进入每位居民当天的情境。注意：这一整棵子树由 data/environment_config.json 提供，它在最后覆盖 CONFIG——在这里改会被它盖掉。",
    "external_environment.generator.mode": "用 LLM 编事件（更多样、要花钱）还是按规则从事件池里抽（免费、重复度高）。",
    "external_environment.natural": "天气与极端天气。极端天气会被判定为异常，可能直接打乱当天日程。",
    "external_environment.economic": "行情波动与宏观新闻。波动超过阈值才会被播报成一条新闻。",
    "external_environment.political": "政策事件。政策会提高全员改变日程的概率。",
    "external_environment.intraday": "日内突发：不在早上一次性生成，而是白天随机插进来，最容易打断正在进行的活动。",
    "external_environment_service": "从外部服务拿环境事件，而不是本机生成。多机联跑时让所有节点看到同一个世界。",
    "external_environment_service.fallback_to_empty": "服务不通时当作「今天没事发生」继续跑，而不是让整轮仿真失败。",
    "environment": "旧版环境事件（保留兼容）。新逻辑在 external_environment 里；两边都开会同时产生事件。",
}

#: Full dotted path (or bare last segment) -> Chinese label. Full path wins.
LABELS: dict[str, str] = {
    # 通用
    "enabled": "启用", "output_dir": "输出目录", "cache_path": "缓存文件", "timeout": "超时(秒)",
    "url": "地址", "base_url": "地址", "host": "监听地址", "port": "端口", "seed": "随机种子",
    "mode": "模式", "model": "模型", "type": "类型", "api_key": "密钥（明文）",
    "api_key_env": "密钥环境变量", "api_key_envs": "密钥环境变量候选", "max_tokens": "最大 token",
    "temperature": "温度", "stream": "流式输出", "max_chars": "最大字数", "top_k": "召回条数",
    "randomness": "随机性", "max_items": "条目上限", "state_path": "状态文件", "description": "说明",
    "every_days": "间隔天数", "lookback_days": "回看天数", "min_age_days": "最小年龄(天)",
    "max_outputs": "产出上限", "min_episodes": "最少经历数", "floor": "下限", "daily_rate": "每日速率",
    "grace_days": "宽限天数", "adopt_chance": "采纳概率", "retire_after_days": "闲置退役天数",
    "max_new_per_day": "每日新增上限", "salience_floor": "重要度下限", "interval_minutes": "间隔(分钟)",
    "max_per_day": "每日上限", "trigger_salience": "触发重要度", "hint_chars": "提示长度",
    # 仿真
    "agent_ids": "参与居民", "sim_days": "仿真天数", "seconds_per_day": "每天秒数",
    "simulate_realtime": "实时等待", "print_agent_profile": "打印人物设定",
    "time_step_minutes": "时间步长(分钟)", "time_grid_snap": "对齐时间格",
    "long_run": "长时段快进", "brief_llm": "日简报用 LLM", "max_state_delta": "单日状态变化上限",
    "brief_max_chars": "日简报字数上限",
    "calendar": "日历", "start_date": "开局日期", "start_weekday": "开局星期", "weekend_days": "周末",
    "background": "时代背景", "csv_path": "居民状态表", "md_path": "人物设定文档",
    "map_path": "虚拟地图", "map_mode": "地图模式", "real_map_path": "真实地图数据",
    "stateful": "跨轮保留记忆", "memory_dir": "记忆目录", "log_dir": "日志目录",
    "diary_output_dir": "日记目录", "environment_output_dir": "环境输出目录",
    "visualization": "轨迹可视化", "site_path": "页面路径", "flush_every_frames": "刷盘帧间隔",
    "environment_config_path": "环境配置文件", "memory_model_version": "记忆格式版本",
    "require_clean_reset_on_memory_model_change": "格式变更强制重置",
    "vector_db_path": "向量库文件", "vector_db_dim": "向量维度", "vector_db_top_k": "向量召回条数",
    "vector_db_max_chars": "单条入库字数上限", "vector_db_embedding_provider": "向量化方式",
    "memory": "记忆机制", "salience_weight": "重要度加权", "decay_halflife_days": "衰减半衰期(天)",
    "growth_boost": "成长相关加权", "growth_boost_strength": "成长加权强度",
    "consolidation": "记忆整理", "decay": "遗忘", "skill_consolidation": "技能沉淀",
    "skills": "技能库", "global_dir": "公共技能目录", "inject_into_cognition": "注入思考提示词",
    "inject_into_work_brief": "注入工作简报", "max_per_prompt": "每次提示词最多注入",
    "policy_events": "预设政策事件", "life_events": "生活事件队列", "event_dir": "事件目录",
    "events_file": "事件文件", "severity_state_amplify": "严重度放大系数",
    "reshape": "当天日程改写", "severity_threshold": "严重度阈值", "window_minutes": "影响窗口(分钟)",
    "aftermath": "事件余波", "min_severity": "最小严重度", "decay_per_day": "每日衰减",
    "min_residual": "残留下限", "max_age_days": "最长持续(天)", "state_pressure_scale": "状态压力系数",
    "routine_change": "日程偏离", "base_chance": "基础概率", "event_boost": "事件加成",
    "policy_boost": "政策加成", "max_chance": "概率上限", "severity_pivot": "严重度支点",
    "event_trigger_scale": "事件触发系数", "event_trigger_cap": "事件触发上限",
    "daily_planning": "每日排程", "anchor_minutes": "锚点粒度(分钟)",
    "random_delay_max_minutes": "随机延迟上限(分钟)", "autoregressive": "以昨天为底稿",
    "flexible": "弹性日程", "min_items": "最少条目", "max_items_": "最多条目",
    "max_time_shift_minutes": "最大挪动(分钟)", "min_gap_minutes": "最小间隔(分钟)",
    "allow_insertions": "允许插入新活动", "min_anchor_match": "锚点贴合下限",
    "spontaneity": "自发性", "base_thought_chance": "冒念头基础概率",
    "max_thought_chance": "冒念头概率上限", "social_boost": "社交加成",
    "low_self_control_boost": "自控力低加成", "stress_boost": "压力加成",
    "fatigue_boost": "疲劳加成", "hunger_boost": "饥饿加成",
    "impulse_activity_chance": "冲动行为概率", "random_action_chance": "随机行为概率",
    "max_override_bonus": "覆盖加成上限",
    "concurrency": "并行度", "day_routine_workers": "日程生成并发数",
    "external_rag": "外部信息注入", "bootstrap": "冷启动注入", "use_seed_script": "使用种子脚本",
    "only_when_empty": "仅在为空时", "profile_items": "画像条数", "web_items": "网络条数",
    "use_web_search": "使用联网搜索", "prefer_cached_news": "优先用缓存新闻",
    "max_chars_per_item": "单条最大字数", "runtime_absorb": "运行中持续吸收",
    "daily_quota_per_agent": "每人每日配额",
    # 环境 / 感知
    "local_physical": "本地环境感知", "crowd_busy_ratio": "拥挤阈值", "crowd_packed_ratio": "爆满阈值",
    "inject_into_perception": "注入感知上下文", "crowd_anomaly_ratio": "异常拥挤阈值",
    "crowd_anomaly_jump": "拥挤突增阈值",
    "anomaly": "异常判定", "intraday_threshold": "日内突发阈值",
    "distributed": "分布式中继", "cluster": "集群名", "node_id": "节点 ID",
    "local_agent_ids": "本地居民", "peer_agent_ids": "对端居民", "send_probability": "发送概率",
    "max_outbound_per_step": "每步最多外发", "max_inbound_per_step": "每步最多接收",
    "message_max_chars": "消息最大字数", "fail_fast": "失败即停", "relay": "中继客户端",
    "server": "中继服务端", "max_messages": "消息上限", "use_llm": "使用 LLM 生成",
    # 新闻
    "news": "新闻与检索", "sources_path": "源清单", "use_cache_first": "优先用缓存",
    "daily_chance": "每日阅读概率", "max_reads_per_day": "每日最多阅读",
    "memory_excerpt_chars": "写入记忆的摘录长度", "user_agent": "User-Agent",
    "info_seek": "主动检索", "base_daily_chance": "每日基准概率", "max_seeks_per_day": "每日最多检索",
    "preferred_sites_per_agent": "每人偏好站点数", "prefer_source_visit_ratio": "直访源站比例",
    "engines": "搜索引擎", "max_results": "结果条数", "content_timeout": "正文超时",
    "content_max_chars": "正文最大字数", "x_mcp": "X / MCP", "bearer_token_env": "Token 环境变量",
    "min_interval_seconds": "最小间隔(秒)", "cooldown_on_429_seconds": "429 冷却(秒)",
    "cache_ttl_seconds": "缓存 TTL(秒)", "contextual_keywords": "上下文关键词",
    "contextual_max_keywords": "关键词上限", "event_driven": "事件驱动检索",
    "max_extra_seeks_per_day": "每日额外检索上限", "stress_threshold": "压力阈值",
    "curiosity_threshold": "好奇阈值", "trigger_chance_on_event": "触发概率",
    # 干预
    "intervention": "推荐与干预", "recommendation": "推荐", "source_weights": "来源权重",
    "relational": "熟人来源", "personalized": "个性化来源", "headline": "头条来源",
    "exposure_control": "曝光抑制", "toxicity_threshold": "毒性阈值",
    "misinformation_threshold": "不实内容阈值", "suppression_factor": "抑制强度",
    "stance": "立场更新", "alpha": "惯性系数", "positive_keywords": "正面词",
    "negative_keywords": "负面词", "toxicity_keywords": "毒性词",
    "misinformation_keywords": "不实内容词", "objectives": "目标权重",
    "cross_viewpoint_weight": "跨观点权重", "engagement_weight": "互动权重",
    "toxicity_penalty_weight": "毒性惩罚权重", "misinformation_penalty_weight": "不实惩罚权重",
    # 人的真实性
    "interests": "兴趣与成长", "daily_insert_chance": "每日新增概率", "weekend_boost": "周末加成",
    "progress_minutes_per_step": "每步进度(分钟)", "evolution": "兴趣更替",
    "goals": "目标体系", "review_interval_days": "复盘间隔(天)",
    "event_review_severity": "事件触发复盘阈值", "max_life_goals": "人生目标上限",
    "max_long_term": "长期目标上限", "max_short_term": "短期目标上限",
    "max_daily_progress_delta": "单日进度上限", "review_log_keep": "复盘记录保留条数",
    "relevance_floor": "相关度下限", "relevance_cap": "相关度上限",
    "max_reviews_per_day": "每日复盘上限",
    "human_realism": "人的真实性", "max_extra_calls_per_agent_day": "每人每日额外调用上限",
    "max_episodes_per_agent": "每人经历上限", "daily_consolidation_top_k": "每日整理条数",
    "salience_threshold": "重要度阈值", "decay_half_life_days": "衰减半衰期(天)",
    "recall": "回忆", "base_top_k": "基础召回", "max_top_k": "召回上限",
    "planning_top_k": "计划时召回", "action_top_k": "行动时召回",
    "reflection_top_k": "反思时召回", "interview_top_k": "采访时召回",
    "surface_min_score": "浮现最低分", "effect_scale": "影响系数", "review": "回顾",
    "behavior": "行为动力学", "habit_learning_rate": "习惯养成速度",
    "habit_min_occurrences": "成为习惯的最少次数", "inertia_weight": "惯性权重",
    "decision_noise": "决策噪声", "fatigue_work_gain": "工作疲劳增速",
    "fatigue_sleep_recovery": "睡眠恢复", "self_control_recovery": "自控力恢复",
    "time_pressure_decay": "时间压力衰减", "commitment_weights": "承诺度权重",
    "high": "高", "medium": "中", "low": "低", "avoidance_bonus_scale": "回避加成系数",
    "need_weights": "需求权重", "energy": "精力", "hunger": "饥饿", "social_need": "社交",
    "dynamic_behavior": "动态行为",
    # 集成
    "extensions": "扩展钩子", "strict": "严格模式", "hooks": "钩子表",
    "collaboration": "协作会话", "sessions_dir": "会话目录",
    "max_concurrent_sessions": "并发会话上限", "max_context_events": "上下文事件上限",
    "step_retries": "步骤重试次数", "discussion": "讨论", "default_rounds": "默认轮数",
    "min_rounds": "最少轮数", "max_rounds": "最多轮数",
    "real_work": "真实工作执行", "queue_path": "任务队列", "artifacts_dir": "产物目录",
    "capabilities_cache": "能力缓存", "max_concurrent_tasks": "并发任务上限",
    "task_timeout_seconds": "任务超时(秒)", "tick_ingest_limit": "每 tick 摄入上限",
    "adapters": "适配器", "web_design": "网页设计", "code": "编码",
    "write_pytest": "同时写测试", "content": "文案", "teaching": "教学",
    "market": "接活市场", "seed_path": "种子文件", "store_path": "存储文件",
    "browse_top_k": "浏览条数", "max_taken_per_agent_per_day": "每人每日接单上限",
    "browse_probability_base": "浏览基础概率", "expire_after_sim_days": "过期天数",
    "auto_replenish": "自动补货", "replenish_threshold": "补货阈值",
    "external_hooks": "外部钩子", "webhook_url": "Webhook 地址", "mcp_server": "MCP 服务",
    # LLM
    "llm": "语言模型", "providers": "可用后端", "routing": "任务路由",
    "default": "默认后端", "tasks": "按任务指定", "model_name": "旧版模型名",
    "ollama_url": "旧版 Ollama 地址", "llm_timeout": "旧版超时(秒)",
    "authorization_scheme": "鉴权方式", "authorization_retry_schemes": "鉴权重试方式",
    "include_x_api_key": "附带 x-api-key",
    # 经济（与 site/dashboard/external.js 的标签表保持一致）
    "economy": "经济 / 货币系统", "currency": "币种",
    "tax": "个人所得税", "monthly_exemption": "月起征点",
    "default_special_deduction": "专项附加扣除", "brackets": "税率表 [上限, 税率, 速算扣除]",
    "social_insurance": "社会保险（个人缴纳比例）", "pension_rate": "养老", "medical_rate": "医疗",
    "unemployment_rate": "失业", "work_injury_rate": "工伤", "maternity_rate": "生育",
    "housing_fund_rate": "公积金（个人）", "housing_fund_employer_rate": "公积金（单位）",
    "base_cap": "缴费基数上限", "base_floor": "缴费基数下限",
    "spending": "消费", "engel_curve": "恩格尔曲线 [收入, 食品占比, 储蓄率]",
    "budget_template": "预算分配模板", "income_elasticity": "收入弹性", "daily_variance": "日波动",
    "investment": "投资", "asset_returns": "资产收益 [均值, 波动]", "portfolio_profiles": "组合画像",
    "auto_save_enabled": "自动储蓄", "checking_buffer_months": "活期缓冲月数",
    "market_correlation": "市场共同因子相关度",
    "credit": "信贷", "credit_limit_months": "授信月数", "annual_interest_rate": "年利率",
    "hardship_liquidity_months": "困难期流动性月数", "min_spend_factor": "最低消费系数",
    "macro": "宏观周期", "initial_inflation_rate": "初始通胀率",
    "initial_unemployment_rate": "初始失业率", "cycle_phase_duration_days": "阶段时长区间（天）",
    "phases": "阶段顺序", "phase_effects": "各阶段效应", "income_mult": "收入乘数",
    "expense_mult": "支出乘数", "layoff_risk": "裁员概率", "raise_chance": "涨薪概率",
    "industry_conditions": "行业景气度", "expansion": "扩张期", "peak": "顶峰期",
    "contraction": "收缩期", "trough": "谷底期",
    "conservative": "保守型", "moderate": "稳健型", "aggressive": "激进型",
    "shocks": "冲击事件", "layoff_base_prob": "裁员基准概率", "raise_base_prob": "涨薪基准概率",
    "medical_emergency_prob": "医疗急症概率", "medical_cost_range": "医疗支出区间",
    "year_end_bonus_enabled": "年终奖", "year_end_bonus_months": "年终奖月数",
    "economy.routing": "支付路由", "merchant_labor_share": "商户劳动分成",
    "landlord_share": "房东分成", "landlord_keywords": "房东关键词",
    "friend_loans": "熟人借贷", "max_outstanding_months": "最大未偿月数",
    "lender_buffer_months": "出借方缓冲月数", "willingness_factor": "出借意愿系数",
    "sectors": "部门池初始余额", "initial_firms_balance": "企业池",
    "initial_government_balance": "政府池", "initial_bank_balance": "银行池",
    "initial_savings_months_min": "初始存款下限（月）",
    "initial_savings_months_max": "初始存款上限（月）",
    "inheritance_enabled": "启用继承/家庭资产", "inheritance_base_probability": "继承基准概率",
    "inheritance_age_peak_low": "继承年龄峰值下限", "inheritance_age_peak_high": "继承年龄峰值上限",
    "inheritance_ratio_min": "继承倍数下限", "inheritance_ratio_max": "继承倍数上限",
    "inheritance_hukou_bonus": "户籍加成", "hours_per_step": "每步小时数",
    "work_days_per_month": "月工作日", "work_hours_per_day": "日工作小时",
    "rent_income_ratio": "房租收入比", "daily_utilities_cost": "日水电",
    "base_living_cost_per_hour": "基础生活成本/小时", "min_hourly_income": "最低时薪",
    "income_volatility": "收入波动", "target_work_hours_per_day": "目标工时",
    "asset_safety_days": "资产安全天数", "income_seek_threshold": "求财阈值",
    "income_seek_probability_scale": "求财概率系数", "income_seek_activities": "求财行为词",
    "expense_ranges": "各类支出区间",
    # 外部环境生成器
    "external_environment": "外部环境生成器", "max_events_per_tick": "每 tick 最多事件数",
    "generator": "生成方式", "history_days": "回看天数",
    "natural": "自然事件", "daily_weather_chance": "每日天气概率",
    "extreme_chance": "极端天气概率", "weather_states": "天气状态与权重",
    "extreme_events": "极端事件池", "economic": "经济事件",
    "daily_market_volatility": "市场日波动", "daily_market_drift": "市场日漂移",
    "market_news_threshold_pct": "行情播报阈值(%)", "macro_event_chance": "宏观事件概率",
    "macro_events": "宏观事件池", "political": "政策事件",
    "daily_policy_chance": "每日政策概率", "technology": "科技事件",
    "daily_tech_chance": "每日科技概率", "tech_events": "科技事件池",
    "intraday": "日内突发", "natural_shock_chance": "自然突发概率",
    "economic_shock_chance": "经济突发概率", "political_shock_chance": "政策突发概率",
    "technology_shock_chance": "科技突发概率",
    "environment": "旧版环境事件（兼容）", "event_chance": "事件概率",
    "natural_events": "自然事件池", "social_events": "社会事件池",
    "external_environment_service": "外部环境服务（客户端）",
    "fallback_to_empty": "不可用时降级为空",
    "environment_server": "外部环境服务（本机服务端）",
}


# ---------------------------------------------------------------------------
# Source-comment extraction
# ---------------------------------------------------------------------------


def _comment_maps(source: str) -> tuple[dict[int, str], dict[int, str]]:
    """Split a module's comments into standalone-line and trailing-inline maps."""
    standalone: dict[int, str] = {}
    inline: dict[int, str] = {}
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type != tokenize.COMMENT:
                continue
            text = tok.string.lstrip("#").strip()
            if not text:
                continue
            target = standalone if tok.line.lstrip().startswith("#") else inline
            target[tok.start[0]] = text
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return {}, {}
    return standalone, inline


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # Section banners like "---- Tax ----" head a group; they read as noise in
    # a tooltip attached to one key.
    text = re.sub(r"^-{2,}\s*|\s*-{2,}$", "", text).strip()
    if len(text) > _MAX_HELP_CHARS:
        text = text[: _MAX_HELP_CHARS - 1].rstrip() + "…"
    return text


def _comment_for(lineno: int, standalone: dict[int, str], inline: dict[int, str]) -> str:
    """The comment block directly above ``lineno``, else its inline comment."""
    block: list[str] = []
    cursor = lineno - 1
    while cursor in standalone:
        block.append(standalone[cursor])
        cursor -= 1
    if block:
        return _clean(" ".join(reversed(block)))
    return _clean(inline.get(lineno, ""))


def _walk_dict(
    node: ast.Dict,
    prefix: str,
    out: dict[str, str],
    standalone: dict[int, str],
    inline: dict[int, str],
) -> None:
    for key_node, value_node in zip(node.keys, node.values):
        if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            continue
        path = f"{prefix}.{key_node.value}" if prefix else key_node.value
        text = _comment_for(key_node.lineno, standalone, inline)
        if text and path not in out:
            out[path] = text
        if isinstance(value_node, ast.Dict):
            _walk_dict(value_node, path, out, standalone, inline)


@lru_cache(maxsize=1)
def source_help() -> dict[str, str]:
    """Extract ``path -> comment`` for every key literal in the settings fragments.

    Silently yields whatever it can: a parse failure in one module must not take
    down the whole 配置 panel, since the help text is a nicety and the values are
    not.
    """
    out: dict[str, str] = {}
    for _id, module, factory, _title, _help in SECTIONS:
        path = _SETTINGS_DIR / f"{module}.py"
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        standalone, inline = _comment_maps(source)
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name != factory.__name__:
                continue
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Dict):
                    _walk_dict(stmt.value, "", out, standalone, inline)
    return out


# ---------------------------------------------------------------------------
# Public resolution
# ---------------------------------------------------------------------------


def help_for(path: str) -> str:
    """Help text for a dotted config path. Manual text wins over source comments."""
    if path in MANUAL_HELP:
        return MANUAL_HELP[path]
    return source_help().get(path, "")


def label_for(path: str) -> str:
    """Chinese label for a dotted config path, falling back to the raw key."""
    if path in LABELS:
        return LABELS[path]
    last = path.rsplit(".", 1)[-1]
    return LABELS.get(last, last)


def section_index() -> dict[str, str]:
    """Map every top-level CONFIG key to the section id that owns it."""
    index: dict[str, str] = {}
    for section_id, _module, factory, _title, _help in SECTIONS:
        for key in factory():
            index.setdefault(key, section_id)
    for section_id, keys in SECTION_EXTRA_KEYS.items():
        for key in keys:
            index.setdefault(key, section_id)
    return index


def section_meta() -> list[dict[str, str]]:
    """Ordered section descriptors for the panel's navigation."""
    return [
        {"id": section_id, "title": title, "help": help_text}
        for section_id, _module, _factory, title, help_text in SECTIONS
    ]


__all__ = [
    "LABELS",
    "MANUAL_HELP",
    "SECTIONS",
    "help_for",
    "label_for",
    "section_index",
    "section_meta",
    "source_help",
]
