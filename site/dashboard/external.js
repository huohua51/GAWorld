/* 外部系统观测台 —— 看住世界本身：货币系统 / 外部环境 / 对外服务。
 *
 * 三个刻意的设计：
 *
 * - **配置表单是从配置本身长出来的**，不是手写的。economy 一棵子树就有上百个叶子，
 *   手写表单既写不完也会在加旋钮的当天过期。这里按 JSON 形状渲染控件，后端再按
 *   现有配置的类型把补丁强制成形（见 external_systems_api._coerce_like）。
 * - **"改运行时状态"走干预队列，不是直接改 macro_state.json**。那个文件是 run 的
 *   *产物*：仿真在 on_simulation_start 从配置重建宏观状态，从不回读它。直接改它会
 *   看起来生效、实际什么都没发生。
 * - 图表手写 SVG，与 population.js 同因：本目录没有构建步骤，引 CDN 图表库会让
 *   dashboard 失去离线可用性。
 */
(function () {
  "use strict";

  var TABS = ["currency", "environment", "services"];

  var state = {
    tab: "currency",
    data: null,
    health: null,
    dirty: {},    // "economy.macro.initial_inflation_rate" -> value
    invalid: {},  // same key -> true when the textarea holds unparseable JSON
    busy: false,
  };

  /* ----------------------------------------------------------------- utils */

  function $(id) {
    return document.getElementById(id);
  }

  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function money(v) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return n.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
  }

  function pct(v, digits) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return (n * 100).toFixed(digits == null ? 2 : digits) + "%";
  }

  function fixed(v, digits) {
    var n = Number(v);
    return isFinite(n) ? n.toFixed(digits == null ? 3 : digits) : "—";
  }

  var PHASE_LABEL = {
    expansion: "扩张 expansion",
    peak: "顶峰 peak",
    contraction: "收缩 contraction",
    trough: "谷底 trough",
  };

  var PHASE_SHORT = { expansion: "扩张", peak: "顶峰", contraction: "收缩", trough: "谷底" };

  var TYPE_LABEL = {
    natural: "自然", economic: "经济", political: "政策", technology: "科技",
  };

  var HEALTH_LABEL = { ok: "通", down: "不通", error: "异常", disabled: "未启用" };

  /* 中文标签只覆盖常用旋钮；没覆盖到的键直接显示原名，不影响可编辑性。 */
  var LABELS = {
    economy: "经济 / 货币系统", enabled: "启用", currency: "币种", output_dir: "输出目录",
    tax: "个人所得税", monthly_exemption: "月起征点", default_special_deduction: "专项附加扣除",
    brackets: "税率表 [上限, 税率, 速算扣除]",
    social_insurance: "社会保险（个人缴纳比例）", pension_rate: "养老", medical_rate: "医疗",
    unemployment_rate: "失业", work_injury_rate: "工伤", maternity_rate: "生育",
    housing_fund_rate: "公积金（个人）", housing_fund_employer_rate: "公积金（单位）",
    base_cap: "缴费基数上限", base_floor: "缴费基数下限",
    spending: "消费", engel_curve: "恩格尔曲线 [收入, 食品占比, 储蓄率]",
    budget_template: "预算分配模板", income_elasticity: "收入弹性", daily_variance: "日波动",
    investment: "投资", asset_returns: "资产收益 [均值, 波动]", portfolio_profiles: "组合画像",
    auto_save_enabled: "自动储蓄", checking_buffer_months: "活期缓冲月数", market_correlation: "市场共同因子相关度",
    credit: "信贷", credit_limit_months: "授信月数", annual_interest_rate: "年利率",
    hardship_liquidity_months: "困难期流动性月数", min_spend_factor: "最低消费系数",
    macro: "宏观周期", initial_inflation_rate: "初始通胀率", initial_unemployment_rate: "初始失业率",
    cycle_phase_duration_days: "阶段时长区间（天）", phases: "阶段顺序", phase_effects: "各阶段效应",
    income_mult: "收入乘数", expense_mult: "支出乘数", layoff_risk: "裁员概率", raise_chance: "涨薪概率",
    industry_conditions: "行业景气度",
    shocks: "冲击事件", layoff_base_prob: "裁员基准概率", raise_base_prob: "涨薪基准概率",
    medical_emergency_prob: "医疗急症概率", medical_cost_range: "医疗支出区间",
    year_end_bonus_enabled: "年终奖", year_end_bonus_months: "年终奖月数",
    routing: "支付路由", merchant_labor_share: "商户劳动分成", landlord_share: "房东分成",
    landlord_keywords: "房东关键词",
    friend_loans: "熟人借贷", max_outstanding_months: "最大未偿月数", lender_buffer_months: "出借方缓冲月数",
    willingness_factor: "出借意愿系数",
    sectors: "部门池初始余额", initial_firms_balance: "企业池", initial_government_balance: "政府池",
    initial_bank_balance: "银行池",
    initial_savings_months_min: "初始存款下限（月）", initial_savings_months_max: "初始存款上限（月）",
    inheritance_enabled: "启用继承/家庭资产", inheritance_base_probability: "继承基准概率",
    inheritance_age_peak_low: "继承年龄峰值下限", inheritance_age_peak_high: "继承年龄峰值上限",
    inheritance_ratio_min: "继承倍数下限", inheritance_ratio_max: "继承倍数上限",
    inheritance_hukou_bonus: "户籍加成",
    hours_per_step: "每步小时数", work_days_per_month: "月工作日", work_hours_per_day: "日工作小时",
    rent_income_ratio: "房租收入比", daily_utilities_cost: "日水电", base_living_cost_per_hour: "基础生活成本/小时",
    min_hourly_income: "最低时薪", income_volatility: "收入波动", target_work_hours_per_day: "目标工时",
    asset_safety_days: "资产安全天数", income_seek_threshold: "求财阈值",
    income_seek_probability_scale: "求财概率系数", income_seek_activities: "求财行为词",
    expense_ranges: "各类支出区间",

    external_environment: "外部环境生成器", seed: "随机种子", max_events_per_tick: "每 tick 最多事件数",
    generator: "生成方式", mode: "模式（llm / rule）", history_days: "回看天数", description: "城市背景描述",
    natural: "自然事件", daily_weather_chance: "每日天气概率", extreme_chance: "极端天气概率",
    weather_states: "天气状态与权重", extreme_events: "极端事件池",
    economic: "经济事件", daily_market_volatility: "市场日波动", daily_market_drift: "市场日漂移",
    market_news_threshold_pct: "行情播报阈值(%)", macro_event_chance: "宏观事件概率", macro_events: "宏观事件池",
    political: "政策事件", daily_policy_chance: "每日政策概率", policy_events: "政策事件池",
    technology: "科技事件", daily_tech_chance: "每日科技概率", tech_events: "科技事件池",
    intraday: "日内突发", natural_shock_chance: "自然突发概率", economic_shock_chance: "经济突发概率",
    political_shock_chance: "政策突发概率", technology_shock_chance: "科技突发概率",
    environment: "旧版环境事件（兼容）", event_chance: "事件概率",
    natural_events: "自然事件池", social_events: "社会事件池",

    external_environment_service: "外部环境服务（客户端）", base_url: "地址", timeout: "超时(秒)",
    fallback_to_empty: "不可用时降级为空",
    environment_server: "外部环境服务（本机服务端）", host: "监听地址", port: "端口",
    state_path: "状态文件", use_llm: "使用 LLM 生成",
    external_rag: "外部信息注入", top_k: "召回条数", bootstrap: "冷启动注入",
    use_seed_script: "使用种子脚本", only_when_empty: "仅在为空时", profile_items: "画像条数",
    web_items: "网络条数", use_web_search: "使用联网搜索", prefer_cached_news: "优先用缓存新闻",
    max_chars_per_item: "单条最大字数", runtime_absorb: "运行中持续吸收", daily_quota_per_agent: "每人每日配额",
    news: "外部新闻源", sources_path: "源清单", cache_path: "缓存文件", use_cache_first: "优先用缓存",
    daily_chance: "每日阅读概率", max_reads_per_day: "每日最多阅读", max_chars: "最大字数",
    memory_excerpt_chars: "写入记忆的摘录长度", user_agent: "User-Agent",
    info_seek: "主动检索", base_daily_chance: "每日基准概率", max_seeks_per_day: "每日最多检索",
    preferred_sites_per_agent: "每人偏好站点数", prefer_source_visit_ratio: "直访源站比例",
    engines: "搜索引擎", max_results: "结果条数", content_timeout: "正文超时", content_max_chars: "正文最大字数",
    x_mcp: "X / MCP", url: "地址", bearer_token_env: "Token 环境变量",
    min_interval_seconds: "最小间隔(秒)", cooldown_on_429_seconds: "429 冷却(秒)", cache_ttl_seconds: "缓存 TTL(秒)",
    contextual_keywords: "上下文关键词", contextual_max_keywords: "关键词上限",
    event_driven: "事件驱动检索", max_extra_seeks_per_day: "每日额外检索上限",
    stress_threshold: "压力阈值", curiosity_threshold: "好奇阈值", trigger_chance_on_event: "触发概率",
    distributed: "分布式中继", cluster: "集群名", node_id: "节点 ID",
    local_agent_ids: "本地 agent", peer_agent_ids: "对端 agent", send_probability: "发送概率",
    max_outbound_per_step: "每步最多外发", max_inbound_per_step: "每步最多接收",
    message_max_chars: "消息最大字数", fail_fast: "失败即停", relay: "中继客户端", server: "中继服务端",
    max_messages: "消息上限",
    llm: "LLM 路由", "default": "默认模型", tasks: "按任务指定",
  };

  function label(key) {
    return LABELS[key] || key;
  }

  /* -------------------------------------------------------------------- api */

  /** 任何失败都要看得见，并且一定把 busy 清掉：卡住的 busy 看起来就是"按钮没反应"。 */
  function api(method, path, body) {
    return fetch(path, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            return { error: "服务器返回了非 JSON 内容（HTTP " + res.status + "）" };
          })
          .then(function (payload) {
            if (!res.ok && !payload.error) payload.error = "HTTP " + res.status;
            return payload;
          });
      })
      .catch(function (err) {
        return { error: String((err && err.message) || err) };
      });
  }

  function status(text, kind) {
    var el = $("extStatus");
    if (!el) return;
    el.textContent = text || "";
    el.className = "ext-status" + (kind ? " " + kind : "");
  }

  /* ----------------------------------------------------------------- charts */

  /** 多序列折线图，共用 y 轴。points 为等间距数值数组。 */
  function lineChart(series, opts) {
    opts = opts || {};
    var width = opts.width || 640;
    var height = opts.height || 132;
    var pad = 26;
    var lengths = series.map(function (s) { return s.points.length; });
    var count = Math.max.apply(null, lengths.concat([0]));
    if (count < 2) return '<p class="ext-hint">数据点不足，跑一次仿真后再看。</p>';

    var all = [];
    series.forEach(function (s) { all = all.concat(s.points.filter(isFinite)); });
    var lo = Math.min.apply(null, all);
    var hi = Math.max.apply(null, all);
    if (lo === hi) { lo -= 1; hi += 1; }

    function x(i) { return pad + (i * (width - pad * 2)) / (count - 1); }
    function y(v) { return height - pad - ((v - lo) / (hi - lo)) * (height - pad * 2); }

    var paths = series.map(function (s) {
      var d = s.points.map(function (v, i) {
        return (i ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1);
      }).join(" ");
      return '<path d="' + d + '" fill="none" stroke="' + s.color + '" stroke-width="1.8" />';
    }).join("");

    var legend = series.map(function (s) {
      return '<span><i style="background:' + s.color + '"></i>' + esc(s.label) + "</span>";
    }).join("");

    return (
      '<svg class="ext-chart" viewBox="0 0 ' + width + " " + height + '" preserveAspectRatio="none" role="img">' +
      '<line x1="' + pad + '" y1="' + (height - pad) + '" x2="' + (width - pad) + '" y2="' + (height - pad) +
      '" stroke="#dde6de" />' +
      paths +
      '<text x="' + pad + '" y="14" font-size="10" fill="#66746c">' + esc(opts.hiLabel || String(Math.round(hi))) + "</text>" +
      '<text x="' + pad + '" y="' + (height - 6) + '" font-size="10" fill="#66746c">' +
      esc(opts.loLabel || String(Math.round(lo))) + "</text>" +
      "</svg>" +
      '<div class="ext-chart-legend">' + legend + "</div>"
    );
  }

  function tiles(items) {
    return '<div class="ext-tiles">' + items.map(function (t) {
      return '<div class="ext-tile' + (t.warn ? " is-warn" : "") + '"><b>' + esc(t.value) +
        "</b><span>" + esc(t.label) + "</span></div>";
    }).join("") + "</div>";
  }

  /* --------------------------------------------------------- config editor */

  function pathKey(prefix, key) {
    return prefix ? prefix + "." + key : String(key);
  }

  function currentValue(path, fallback) {
    return Object.prototype.hasOwnProperty.call(state.dirty, path) ? state.dirty[path] : fallback;
  }

  function fieldClass(path) {
    return "ext-field" +
      (Object.prototype.hasOwnProperty.call(state.dirty, path) ? " is-dirty" : "") +
      (state.invalid[path] ? " is-bad" : "");
  }

  /** 按 JSON 形状渲染控件。数组和无法判型的值退化为 JSON 文本框。 */
  function renderNode(key, value, path, depth) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      var body = Object.keys(value).map(function (childKey) {
        return renderNode(childKey, value[childKey], pathKey(path, childKey), depth + 1);
      }).join("");
      return '<details class="ext-group"' + (depth === 0 ? " open" : "") + ">" +
        "<summary>" + esc(label(key)) + "</summary>" +
        '<div class="ext-group-body">' + body + "</div></details>";
    }

    if (typeof value === "boolean") {
      var on = currentValue(path, value);
      return '<label class="' + fieldClass(path) + ' inline">' +
        '<input type="checkbox" data-path="' + esc(path) + '" data-kind="bool"' + (on ? " checked" : "") + " />" +
        "<span>" + esc(label(key)) + "</span></label>";
    }

    if (typeof value === "number") {
      return '<label class="' + fieldClass(path) + '"><span>' + esc(label(key)) + "</span>" +
        '<input type="number" step="any" data-path="' + esc(path) + '" data-kind="number" value="' +
        esc(currentValue(path, value)) + '" /></label>';
    }

    if (typeof value === "string") {
      return '<label class="' + fieldClass(path) + '"><span>' + esc(label(key)) + "</span>" +
        '<input type="text" data-path="' + esc(path) + '" data-kind="text" value="' +
        esc(currentValue(path, value)) + '" /></label>';
    }

    // 数组 / null：JSON 文本框。结构化控件在这里得不偿失，而 JSON 是可校验的。
    var raw = currentValue(path, value);
    var text = typeof raw === "string" && state.invalid[path] ? raw : JSON.stringify(raw);
    return '<label class="' + fieldClass(path) + '"><span>' + esc(label(key)) +
      (state.invalid[path] ? ' <b class="ext-warn">JSON 无法解析</b>' : "") + "</span>" +
      '<textarea data-path="' + esc(path) + '" data-kind="json">' + esc(text) + "</textarea></label>";
  }

  function renderConfigEditor(config) {
    var keys = Object.keys(config || {});
    if (!keys.length) return '<p class="ext-hint">这一节没有可编辑的配置。</p>';
    return keys.map(function (key) {
      return renderNode(key, config[key], key, 0);
    }).join("");
  }

  function dirtyCount() {
    return Object.keys(state.dirty).length;
  }

  /** 把扁平的 dirty 路径还原成嵌套补丁。 */
  function buildPatch() {
    var patch = {};
    Object.keys(state.dirty).forEach(function (path) {
      var parts = path.split(".");
      var node = patch;
      for (var i = 0; i < parts.length - 1; i++) {
        if (typeof node[parts[i]] !== "object" || node[parts[i]] === null) node[parts[i]] = {};
        node = node[parts[i]];
      }
      node[parts[parts.length - 1]] = state.dirty[path];
    });
    return patch;
  }

  /* -------------------------------------------------------- observe: money */

  function renderCurrencyObserve(data) {
    var rt = data.runtime;
    var macro = rt.macro || {};
    var cons = rt.conservation || {};
    var latest = cons.latest;
    var wealth = rt.wealth || {};
    var sectors = rt.sectors || {};

    var head = tiles([
      { label: "周期阶段", value: PHASE_SHORT[macro.phase] || macro.phase || "—" },
      { label: "通胀率（年化）", value: pct(macro.inflation_rate) },
      { label: "失业率", value: pct(macro.unemployment_rate) },
      { label: "累计物价指数", value: fixed(macro.cumulative_inflation, 4) },
      { label: "系统总货币", value: money(latest ? latest.system_total : rt.money_stock.final_system_total) },
      {
        label: "守恒漂移（最大绝对值）",
        value: cons.max_abs_drift == null ? "—" : money(cons.max_abs_drift),
        warn: cons.ok === false,
      },
      { label: "基尼系数", value: wealth.gini == null ? "—" : fixed(wealth.gini, 4) },
      { label: "负债 agent", value: (wealth.indebted_agents || 0) + " / " + (wealth.agents || 0) },
    ]);

    var sectorRows = ["firms", "government", "bank"].map(function (name) {
      var cn = { firms: "企业池", government: "政府池", bank: "银行池" }[name];
      return "<tr><td>" + cn + " <code>" + name + "</code></td><td class=\"num\">" +
        money(sectors[name]) + "</td></tr>";
    }).join("");

    var injected = Number(rt.money_stock.intervention_injected_total || 0);
    var conservationNote = cons.ok === false
      ? '<p class="ext-hint ext-warn">守恒审计发现漂移：钱在某处凭空产生或消失了，这通常是 bug 而不是设定。</p>'
      : cons.ok === true
        ? '<p class="ext-hint ext-ok">守恒审计通过：每一天的系统总货币都等于初始存量。</p>'
        : '<p class="ext-hint">还没有守恒审计数据，跑一次仿真后生成。</p>';

    var ledger = rt.ledger || [];
    var ledgerChart = lineChart(
      [
        { label: "全体日收入", color: "#0e7a58", points: ledger.map(function (d) { return d.income; }) },
        { label: "全体日支出", color: "#c04545", points: ledger.map(function (d) { return d.expense; }) },
      ],
      { hiLabel: "高", loLabel: "低" }
    );

    var totalChart = lineChart(
      [{ label: "系统总货币", color: "#3c5a68", points: (cons.rows || []).map(function (r) { return r.system_total; }) }],
      { hiLabel: "高", loLabel: "低" }
    );

    var iv = rt.interventions || { pending: [], applied: [] };
    var pendingList = iv.pending.length
      ? '<ul class="ext-queue">' + iv.pending.map(function (item) {
        return "<li><b>" + esc(item.id) + "</b> · " +
          (item.day == null ? "下一天生效" : "第 " + esc(item.day) + " 天生效") +
          (item.note ? " · " + esc(item.note) : "") +
          "<br/><code>" + esc(JSON.stringify({ macro: item.macro, sector_delta: item.sector_delta })) + "</code></li>";
      }).join("") + "</ul>"
      : '<p class="ext-hint">没有待生效的干预。</p>';

    var appliedList = (iv.applied || []).length
      ? '<ul class="ext-queue">' + iv.applied.slice().reverse().map(function (item) {
        return "<li><b>第 " + esc(item.applied_day) + " 天</b> · " + esc(item.id) +
          (item.note ? " · " + esc(item.note) : "") +
          "<br/><code>" + esc(JSON.stringify({
            macro: item.applied_macro, sector_delta: item.applied_sector_delta,
          })) + "</code></li>";
      }).join("") + "</ul>"
      : '<p class="ext-hint">还没有干预被执行过。</p>';

    return (
      '<div class="ext-card"><h2>货币系统现状</h2>' +
      '<p class="ext-lede">读自最近一次仿真的产物（<code>' + esc(rt.output_dir) +
      "</code>）。宏观状态每天由周期推进，钱在 agent 与企业/政府/银行三个部门池之间流转。</p>" +
      head +
      "<h3>部门池余额</h3>" +
      '<table class="ext-table"><thead><tr><th>部门</th><th class="num">余额</th></tr></thead><tbody>' +
      sectorRows +
      (injected ? '<tr><td>其中：人为注入累计</td><td class="num">' + money(injected) + "</td></tr>" : "") +
      "</tbody></table>" +
      "<h3>货币守恒</h3>" + conservationNote + totalChart +
      "<h3>全体日收支</h3>" + ledgerChart +
      "</div>" +

      '<div class="ext-card"><h2>财富分布</h2>' +
      '<p class="ext-lede">口径为流动资产（活期 + 储蓄 + 投资），公积金单列。</p>' +
      '<table class="ext-table"><tbody>' +
      ["agents:居民数:" + (wealth.agents || 0),
       "total:流动资产合计:" + money(wealth.total_balance),
       "mean:人均:" + money(wealth.mean_balance),
       "median:中位数:" + money(wealth.median_balance),
       "range:最低 / 最高:" + money(wealth.min_balance) + " / " + money(wealth.max_balance),
       "hf:公积金合计:" + money(wealth.total_housing_fund),
       "debt:负债合计:" + money(wealth.total_debt),
       "gini:基尼系数:" + (wealth.gini == null ? "—（少于 2 人或总额为 0）" : fixed(wealth.gini, 4))]
        .map(function (row) {
          var parts = row.split(":");
          return "<tr><td>" + esc(parts[1]) + '</td><td class="num">' + esc(parts.slice(2).join(":")) + "</td></tr>";
        }).join("") +
      "</tbody></table></div>" +

      '<div class="ext-card"><h2>干预队列</h2>' +
      '<p class="ext-lede">右侧提交的干预写进 <code>' + esc(iv.path) +
      "</code>，运行中的仿真在每个自然日边界消费它。仿真没在跑时会一直等到下次开跑。</p>" +
      "<h3>待生效</h3>" + pendingList +
      "<h3>已执行（最近 20 条）</h3>" + appliedList +
      "</div>"
    );
  }

  function renderCurrencyEdit(data) {
    var macro = (data.runtime && data.runtime.macro) || {};
    var phases = ["", "expansion", "peak", "contraction", "trough"];
    var options = phases.map(function (p) {
      return '<option value="' + esc(p) + '">' + (p ? esc(PHASE_LABEL[p]) : "不改变") + "</option>";
    }).join("");

    return (
      '<div class="ext-edit-card"><h3>干预运行中的货币系统</h3>' +
      '<p class="ext-note">留空的字段不改。部门余额填的是<b>增减量</b>（正数注入、负数抽离）；' +
      "注入会同步抬高守恒基准，所以审计不会把它误报成漏钱。</p>" +
      '<label class="ext-field"><span>周期阶段（当前：' + esc(PHASE_LABEL[macro.phase] || macro.phase || "—") + "）</span>" +
      '<select id="ivPhase">' + options + "</select></label>" +
      '<div class="ext-row">' +
      '<label class="ext-field"><span>通胀率（当前 ' + pct(macro.inflation_rate) + "）</span>" +
      '<input type="number" step="any" id="ivInflation" placeholder="0.08" /></label>' +
      '<label class="ext-field"><span>失业率（当前 ' + pct(macro.unemployment_rate) + "）</span>" +
      '<input type="number" step="any" id="ivUnemployment" placeholder="0.09" /></label>' +
      "</div>" +
      '<div class="ext-row">' +
      '<label class="ext-field"><span>企业池 ±</span><input type="number" step="any" id="ivFirms" /></label>' +
      '<label class="ext-field"><span>政府池 ±</span><input type="number" step="any" id="ivGovernment" /></label>' +
      '<label class="ext-field"><span>银行池 ±</span><input type="number" step="any" id="ivBank" /></label>' +
      "</div>" +
      '<div class="ext-row">' +
      '<label class="ext-field"><span>生效日（留空 = 下一天）</span><input type="number" step="1" id="ivDay" /></label>' +
      '<label class="ext-field"><span>备注</span><input type="text" id="ivNote" placeholder="财政刺激" /></label>' +
      "</div>" +
      '<div class="ext-edit-actions">' +
      '<button class="button" id="ivSubmit">加入干预队列</button>' +
      '<button class="button subtle" id="ivClear">清空待生效</button>' +
      "</div></div>" +
      renderConfigCard("currency", data.config,
        "改的是下一次仿真的初始条件（税率、社保、恩格尔曲线、宏观周期、冲击概率……），不影响正在跑的这一轮。")
    );
  }

  /* --------------------------------------------------- observe: environment */

  function renderEnvironmentObserve(data) {
    var rt = data.runtime;
    if (!rt.available) {
      return '<div class="ext-card"><h2>外部环境</h2>' +
        '<p class="ext-hint">还没有 <code>timeline.jsonl</code>。跑一次仿真后，这里会显示每天生成的环境事件。</p></div>';
    }

    var counts = rt.event_type_counts || {};
    var countTiles = Object.keys(counts).map(function (key) {
      return { label: (TYPE_LABEL[key] || key) + "事件", value: counts[key] };
    });

    var days = (rt.days || []).slice().reverse().map(function (day) {
      var events = (day.events || []).map(function (ev) {
        var sev = Number(ev.severity) || 0;
        return '<div class="ext-event"><div class="ext-event-head">' +
          '<span class="ext-badge t-' + esc(ev.type) + '">' + esc(TYPE_LABEL[ev.type] || ev.type) + "</span>" +
          "<b>" + esc(ev.name) + "</b>" +
          '<span class="ext-sev' + (sev >= 0.6 ? " high" : "") + '" title="严重度 ' + esc(sev) +
          '"><i style="width:' + Math.round(Math.min(1, sev) * 100) + '%"></i></span>' +
          (ev.impact_tags || []).map(function (tag) {
            return '<span class="ext-badge">' + esc(tag) + "</span>";
          }).join("") +
          "</div><p>" + esc(ev.description) + "</p></div>";
      }).join("");
      return '<div class="ext-day"><div class="ext-day-head"><b>第 ' + esc(day.day) + " 天</b>" +
        "<span>" + esc(day.date || "") + "</span></div>" +
        '<p class="ext-day-summary">' + esc(day.summary || "") + "</p>" + events + "</div>";
    }).join("");

    return (
      '<div class="ext-card"><h2>外部环境概览</h2>' +
      '<p class="ext-lede">环境生成器每天抛出自然/经济/政策/科技四类事件，进入 agent 的当日情境。读自 <code>' +
      esc(rt.timeline_path) + "</code>。</p>" +
      tiles([
        { label: "最新一天", value: rt.latest_day == null ? "—" : "第 " + rt.latest_day + " 天" },
        { label: "已生成天数", value: rt.day_count },
        { label: "日内 tick 记录", value: rt.tick_records },
        { label: "平均严重度", value: rt.mean_severity == null ? "—" : fixed(rt.mean_severity, 3) },
      ].concat(countTiles)) +
      "</div>" +
      '<div class="ext-card"><h2>最近 ' + (rt.days || []).length + " 天的事件</h2>" + (days || '<p class="ext-hint">暂无事件。</p>') + "</div>"
    );
  }

  function renderEnvironmentEdit(data) {
    return renderConfigCard("environment", data.config,
      "这些参数控制环境生成器：各类事件的日概率、天气权重、事件文案池，以及 policy_events 里排定的政策冲击。改完下次仿真生效。");
  }

  /* ------------------------------------------------------ observe: services */

  function renderServicesObserve(data) {
    var rt = data.runtime;
    var probed = {};
    ((state.health && state.health.targets) || []).forEach(function (t) { probed[t.id] = t; });

    var rows = (rt.targets || []).map(function (target) {
      var result = probed[target.id];
      var cls = result ? result.status : (target.enabled ? "" : "disabled");
      var text;
      if (!result) {
        text = target.enabled ? "未探测" : "未启用";
      } else {
        // `latency_ms` is absent for a target that was never dialled, so it is
        // appended only when a probe actually happened.
        text = (HEALTH_LABEL[result.status] || result.status) +
          "（" + (result.detail || "") +
          (result.latency_ms == null ? "" : "，" + result.latency_ms + "ms") + "）";
      }
      return "<tr><td>" + esc(target.label) + "</td>" +
        "<td><code>" + esc(target.url || "—") + "</code></td>" +
        '<td><span class="ext-dot ' + esc(cls) + '"></span>' + esc(text) + "</td></tr>";
    }).join("");

    var tasks = (rt.llm_routing && rt.llm_routing.tasks) || {};
    var taskRows = Object.keys(tasks).map(function (key) {
      return "<tr><td>" + esc(key) + "</td><td>" + esc(tasks[key]) + "</td></tr>";
    }).join("") || '<tr><td colspan="2">全部走默认模型</td></tr>';

    return (
      '<div class="ext-card"><h2>对外服务连通性</h2>' +
      '<p class="ext-lede">仿真需要向外拨号的地方：外部环境服务、分布式中继。点下面的按钮做一次即时探测。</p>' +
      '<table class="ext-table"><thead><tr><th>服务</th><th>地址</th><th>状态</th></tr></thead><tbody>' +
      (rows || '<tr><td colspan="3">没有配置对外服务。</td></tr>') + "</tbody></table>" +
      '<div class="ext-edit-actions"><button class="button subtle" id="svcProbe">探测一次</button>' +
      '<span class="ext-note">' + esc(state.health ? "上次探测：" + state.health.checked_at : "尚未探测") + "</span></div>" +
      "</div>" +

      '<div class="ext-card"><h2>LLM 路由</h2>' +
      '<p class="ext-lede">可用模型来自配置里的 providers（密钥不在此暴露，也不可在此编辑）。路由决定哪个任务用哪个模型。</p>' +
      tiles([
        { label: "可用模型", value: (rt.llm_providers || []).length },
        { label: "默认模型", value: (rt.llm_routing && rt.llm_routing["default"]) || "—" },
      ]) +
      "<h3>模型清单</h3><p class=\"ext-hint\">" + esc((rt.llm_providers || []).join(" · ") || "无") + "</p>" +
      "<h3>按任务指定</h3>" +
      '<table class="ext-table"><thead><tr><th>任务</th><th>模型</th></tr></thead><tbody>' + taskRows + "</tbody></table>" +
      "</div>" +

      '<div class="ext-card"><h2>外部信息源</h2>' +
      tiles([
        { label: "新闻缓存条目", value: (rt.news_cache && rt.news_cache.entries) || 0 },
        { label: "缓存文件", value: (rt.news_cache && rt.news_cache.exists) ? "存在" : "缺失" },
      ]) +
      '<p class="ext-hint">缓存路径：<code>' + esc((rt.news_cache && rt.news_cache.path) || "—") + "</code></p></div>"
    );
  }

  function renderServicesEdit(data) {
    return renderConfigCard("services", data.config,
      "外部环境服务地址、分布式中继、外部信息注入、新闻源与 LLM 路由。改完下次仿真生效；服务端进程需要自己重启。");
  }

  /* -------------------------------------------------------------- rendering */

  function renderConfigCard(tab, config, note) {
    var count = dirtyCount();
    return (
      '<div class="ext-edit-card"><h3>配置</h3>' +
      '<p class="ext-note">' + esc(note) + "</p>" +
      '<div id="extConfigTree">' + renderConfigEditor(config) + "</div>" +
      '<div class="ext-edit-actions">' +
      '<button class="button" id="cfgSave"' + (count ? "" : " disabled") + ">保存" + (count ? "（" + count + " 项）" : "") + "</button>" +
      '<button class="button subtle" id="cfgReset"' + (count ? "" : " disabled") + ">放弃改动</button>" +
      "</div></div>"
    );
  }

  var RENDERERS = {
    currency: { observe: renderCurrencyObserve, edit: renderCurrencyEdit },
    environment: { observe: renderEnvironmentObserve, edit: renderEnvironmentEdit },
    services: { observe: renderServicesObserve, edit: renderServicesEdit },
  };

  function render() {
    var data = state.data && state.data[state.tab];
    if (!data) {
      $("extObserve").innerHTML = '<div class="ext-card"><p class="ext-hint">正在加载…</p></div>';
      $("extEdit").innerHTML = "";
      return;
    }
    var renderer = RENDERERS[state.tab];
    $("extObserve").innerHTML = renderer.observe(data);
    $("extEdit").innerHTML = renderer.edit(data);

    Array.prototype.forEach.call(document.querySelectorAll("#extTabs .step"), function (btn) {
      btn.classList.toggle("is-active", btn.dataset.tab === state.tab);
    });

    var meta = $("extTopMeta");
    if (meta) {
      meta.innerHTML = "观测时间 " + esc(state.data.generated_at) +
        (dirtyCount() ? '<br/><b class="ext-ok">' + dirtyCount() + " 项配置改动未保存</b>" : "");
    }
  }

  function load() {
    return api("GET", "/api/external-systems/overview").then(function (payload) {
      if (payload.error) {
        $("extObserve").innerHTML = '<div class="ext-card"><h2>无法加载</h2><p class="ext-warn">' +
          esc(payload.error) + "</p></div>";
        status(payload.error, "err");
        return;
      }
      state.data = payload;
      render();
    });
  }

  /* ---------------------------------------------------------------- actions */

  function onConfigInput(event) {
    var el = event.target;
    var path = el.dataset && el.dataset.path;
    if (!path) return;
    var kind = el.dataset.kind;

    if (kind === "bool") {
      state.dirty[path] = el.checked;
    } else if (kind === "number") {
      if (el.value === "") { delete state.dirty[path]; } else { state.dirty[path] = Number(el.value); }
    } else if (kind === "json") {
      try {
        state.dirty[path] = JSON.parse(el.value);
        delete state.invalid[path];
      } catch (err) {
        state.dirty[path] = el.value;
        state.invalid[path] = true;
      }
    } else {
      state.dirty[path] = el.value;
    }
    el.parentNode.classList.add("is-dirty");
    el.parentNode.classList.toggle("is-bad", !!state.invalid[path]);
    syncSaveButton();
  }

  function syncSaveButton() {
    var count = dirtyCount();
    var save = $("cfgSave");
    var reset = $("cfgReset");
    if (save) { save.disabled = !count; save.textContent = "保存" + (count ? "（" + count + " 项）" : ""); }
    if (reset) reset.disabled = !count;
    var meta = $("extTopMeta");
    if (meta && state.data) {
      meta.innerHTML = "观测时间 " + esc(state.data.generated_at) +
        (count ? '<br/><b class="ext-ok">' + count + " 项配置改动未保存</b>" : "");
    }
  }

  function saveConfig() {
    var bad = Object.keys(state.invalid);
    if (bad.length) {
      status("有 " + bad.length + " 处 JSON 无法解析，先改对再保存：" + bad.join("、"), "err");
      return;
    }
    if (!dirtyCount()) return;
    status("正在保存…");
    api("POST", "/api/external-systems/config", { config: buildPatch() }).then(function (res) {
      if (res.error) { status(res.error, "err"); return; }
      state.dirty = {};
      state.invalid = {};
      var dropped = res.dropped || [];
      status(
        "已保存 " + (res.applied || []).join("、") +
        (dropped.length ? "；被丢弃的键：" + dropped.join("、") : ""),
        dropped.length ? "err" : "ok"
      );
      load();
    });
  }

  function submitIntervention() {
    var macro = {};
    var phase = $("ivPhase").value;
    if (phase) macro.phase = phase;
    if ($("ivInflation").value !== "") macro.inflation_rate = Number($("ivInflation").value);
    if ($("ivUnemployment").value !== "") macro.unemployment_rate = Number($("ivUnemployment").value);

    var sector = {};
    ["Firms:firms", "Government:government", "Bank:bank"].forEach(function (pair) {
      var parts = pair.split(":");
      var value = $("iv" + parts[0]).value;
      if (value !== "") sector[parts[1]] = Number(value);
    });

    status("正在提交干预…");
    api("POST", "/api/external-systems/interventions", {
      macro: macro,
      sector_delta: sector,
      day: $("ivDay").value,
      note: $("ivNote").value,
    }).then(function (res) {
      if (res.error) { status(res.error, "err"); return; }
      status("已加入队列：" + res.queued.id, "ok");
      load();
    });
  }

  function clearInterventions() {
    api("POST", "/api/external-systems/interventions/cancel", { all: true }).then(function (res) {
      if (res.error) { status(res.error, "err"); return; }
      status("已清空 " + res.removed + " 条待生效干预", "ok");
      load();
    });
  }

  function probeServices() {
    status("正在探测…");
    api("GET", "/api/external-systems/health").then(function (res) {
      if (res.error) { status(res.error, "err"); return; }
      state.health = res;
      status("探测完成", "ok");
      render();
    });
  }

  /* ------------------------------------------------------------------- boot */

  function switchTab(tab) {
    if (TABS.indexOf(tab) < 0 || tab === state.tab) return;
    if (dirtyCount() && !window.confirm("有未保存的配置改动，切换后会丢失。继续？")) return;
    state.dirty = {};
    state.invalid = {};
    state.tab = tab;
    status("");
    render();
  }

  function boot() {
    $("extTabs").addEventListener("click", function (event) {
      var btn = event.target.closest(".step");
      if (btn) switchTab(btn.dataset.tab);
    });

    $("extEdit").addEventListener("change", onConfigInput);
    $("extEdit").addEventListener("click", function (event) {
      var id = event.target.id;
      if (id === "cfgSave") saveConfig();
      else if (id === "cfgReset") { state.dirty = {}; state.invalid = {}; status(""); render(); }
      else if (id === "ivSubmit") submitIntervention();
      else if (id === "ivClear") clearInterventions();
    });

    $("extObserve").addEventListener("click", function (event) {
      if (event.target.id === "svcProbe") probeServices();
    });

    $("extRefresh").addEventListener("click", function () {
      status("正在刷新…");
      load().then(function () { status("已刷新", "ok"); });
    });

    load();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
