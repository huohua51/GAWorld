// Analytics view: renders the artifacts of a finished (or running) simulation
// as SVG. No chart library — every figure below is a string of SVG built from
// the /api/analytics/* payloads, so the page works fully offline.
(function () {
  "use strict";

  var PALETTE = [
    "#0e7a58", "#3c5a68", "#d6a81e", "#c04545", "#7b5ea7",
    "#17936c", "#b3703a", "#4a7fb5", "#8a9a3f", "#a4478b",
  ];

  // The nine seeded state variables get a Chinese label; anything else the
  // simulator emits falls back to its raw key.
  var METRIC_LABELS = {
    emotion: "情绪", stress: "压力", econ_security: "经济安全感",
    city_identity: "城市认同", policy_sensitivity: "政策敏感度",
    platform_dependence: "平台依赖", risk_preference: "风险偏好",
    voice_propensity: "表达倾向", mobility_intent: "出行意愿",
    energy: "精力", fatigue_debt: "疲劳负债", hunger: "饥饿",
    social_need: "社交需求", self_control: "自控力", time_pressure: "时间压力",
    stance_score: "立场倾向", toxicity_score: "戾气指数",
    misinformation_risk: "误信风险", cross_viewpoint_exposure: "跨观点暴露",
    intervention_reward: "干预回报", metric: "综合指标",
  };

  var ECON_LABELS = {
    balance: "总资产", income: "收入", expense: "支出", checking: "活期",
    savings: "储蓄", investment: "投资", debt: "负债",
    econ_security: "经济安全感", engel_coefficient: "恩格尔系数",
  };

  var PERIOD_LABELS = {
    morning: "上午", noon: "中午", afternoon: "下午", evening: "傍晚", night: "夜间",
  };

  var EVENT_COLORS = {
    natural: "#3c5a68", technology: "#7b5ea7", policy: "#0e7a58",
    economy: "#d6a81e", social: "#c04545", health: "#b3703a",
  };

  var state = {
    overview: null, history: null, economy: null,
    social: null, behavior: null, events: null,
    metrics: [],        // selected state metrics
    agents: [],         // selected agent ids (strings)
    econSeries: ["balance", "income", "expense"],
  };

  function $(id) { return document.getElementById(id); }

  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function metricLabel(key) { return METRIC_LABELS[key] || key; }
  function color(index) { return PALETTE[index % PALETTE.length]; }
  function num(value, digits) {
    if (value == null || isNaN(value)) return "—";
    return Number(value).toFixed(digits == null ? 2 : digits);
  }
  function compact(value) {
    if (value == null || isNaN(value)) return "—";
    var abs = Math.abs(value);
    if (abs >= 1e8) return (value / 1e8).toFixed(2) + "亿";
    if (abs >= 1e4) return (value / 1e4).toFixed(2) + "万";
    return Number(value).toFixed(abs >= 100 ? 0 : 2);
  }

  async function api(path) {
    var res = await fetch(path, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(path + " → HTTP " + res.status);
    return res.json();
  }

  function note(message) {
    return '<p class="an-empty">' + esc(message) + "</p>";
  }

  /* ------------------------------------------------------------ primitives */

  // Multi-series line chart. Each series is {label, color, points:[y|null]};
  // x is the point index normalized across the longest series.
  function lineChart(series, opts) {
    opts = opts || {};
    var W = 320, H = 150, padL = 34, padR = 8, padT = 10, padB = 20;
    var live = series.filter(function (s) { return s.points && s.points.length; });
    if (!live.length) return note("暂无数据");

    var values = [];
    live.forEach(function (s) {
      s.points.forEach(function (v) { if (v != null && !isNaN(v)) values.push(v); });
    });
    if (!values.length) return note("暂无数据");
    var lo = opts.yMin != null ? opts.yMin : Math.min.apply(null, values);
    var hi = opts.yMax != null ? opts.yMax : Math.max.apply(null, values);
    if (hi - lo < 1e-9) { hi = lo + Math.max(1e-6, Math.abs(lo) * 0.1 || 1); }

    var maxLen = Math.max.apply(null, live.map(function (s) { return s.points.length; }));
    var x = function (i, len) {
      var t = len > 1 ? i / (len - 1) : 0;
      return padL + t * (W - padL - padR);
    };
    var y = function (v) {
      return padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
    };

    var grid = "", i;
    for (i = 0; i <= 4; i++) {
      var value = lo + ((hi - lo) * i) / 4;
      var gy = y(value).toFixed(1);
      grid += '<line x1="' + padL + '" y1="' + gy + '" x2="' + (W - padR) + '" y2="' + gy +
        '" stroke="#e4ece5" stroke-width="1"/>' +
        '<text x="' + (padL - 4) + '" y="' + (Number(gy) + 3).toFixed(1) +
        '" font-size="8" fill="#8a968f" text-anchor="end">' + esc(compact(value)) + "</text>";
    }
    // Zero baseline stands out when a series crosses it (deltas, net income).
    if (lo < 0 && hi > 0) {
      grid += '<line x1="' + padL + '" y1="' + y(0).toFixed(1) + '" x2="' + (W - padR) +
        '" y2="' + y(0).toFixed(1) + '" stroke="#b9c6bc" stroke-width="1" stroke-dasharray="3 3"/>';
    }

    var paths = live.map(function (s, index) {
      var segments = [], open = false;
      s.points.forEach(function (v, idx) {
        if (v == null || isNaN(v)) { open = false; return; }
        segments.push((open ? "L" : "M") + x(idx, s.points.length).toFixed(1) + " " + y(v).toFixed(1));
        open = true;
      });
      if (!segments.length) return "";
      return '<path d="' + segments.join(" ") + '" fill="none" stroke="' +
        (s.color || color(index)) + '" stroke-width="1.7" stroke-linejoin="round"/>';
    }).join("");

    var xAxis = "";
    if (opts.xLabels && opts.xLabels.length) {
      var ticks = [0, Math.floor(opts.xLabels.length / 2), opts.xLabels.length - 1];
      ticks.forEach(function (idx, position) {
        if (idx < 0 || idx >= opts.xLabels.length) return;
        var anchor = position === 0 ? "start" : position === 2 ? "end" : "middle";
        xAxis += '<text x="' + x(idx, opts.xLabels.length).toFixed(1) + '" y="' + (H - 5) +
          '" font-size="8" fill="#8a968f" text-anchor="' + anchor + '">' +
          esc(opts.xLabels[idx]) + "</text>";
      });
    } else {
      xAxis = '<text x="' + (W - padR) + '" y="' + (H - 5) +
        '" font-size="8" fill="#8a968f" text-anchor="end">' + maxLen + " 步</text>";
    }

    return '<svg class="an-chart" viewBox="0 0 ' + W + " " + H + '" role="img">' +
      grid + paths + xAxis + "</svg>";
  }

  // Horizontal bars. Values may be negative (diverging around a zero axis).
  function barChart(items, opts) {
    opts = opts || {};
    if (!items.length) return note("暂无数据");
    var rowH = 20, W = 320, padL = opts.labelWidth || 96;
    // Reserve room for the longest value label, otherwise long strings such as
    // "0.62 → 1.00" run past the viewBox and get clipped by the card.
    var widest = items.reduce(function (max, item) {
      return Math.max(max, String(item.display || num(item.value, 3)).length);
    }, 0);
    var padR = Math.max(30, widest * 5 + 6);
    var H = items.length * rowH + 6;
    var values = items.map(function (item) { return Number(item.value) || 0; });
    var hi = Math.max.apply(null, values.concat([0]));
    var lo = Math.min.apply(null, values.concat([0]));
    var span = Math.max(hi - lo, 1e-9);
    var plot = W - padL - padR;
    var zero = padL + ((0 - lo) / span) * plot;

    var rows = items.map(function (item, index) {
      var value = Number(item.value) || 0;
      var width = (Math.abs(value) / span) * plot;
      var bx = value >= 0 ? zero : zero - width;
      var cy = index * rowH + 4;
      var fill = item.color || (opts.diverging ? (value >= 0 ? "#0e7a58" : "#c04545") : color(index));
      return '<text x="' + (padL - 6) + '" y="' + (cy + 11) +
        '" font-size="9" fill="#3f4d45" text-anchor="end">' + esc(item.label) + "</text>" +
        '<rect x="' + bx.toFixed(1) + '" y="' + cy + '" width="' + Math.max(width, 1).toFixed(1) +
        '" height="12" rx="2" fill="' + fill + '" opacity="0.85"><title>' +
        esc(item.label + "：" + (item.display || num(value, 3))) + "</title></rect>" +
        '<text x="' + (W - 4) + '" y="' + (cy + 11) +
        '" font-size="8.5" fill="#66746c" text-anchor="end">' +
        esc(item.display || num(value, 3)) + "</text>";
    }).join("");

    var axis = opts.diverging
      ? '<line x1="' + zero.toFixed(1) + '" y1="0" x2="' + zero.toFixed(1) + '" y2="' + H +
        '" stroke="#c4d1c6" stroke-width="1"/>'
      : "";
    return '<svg class="an-chart" viewBox="0 0 ' + W + " " + H + '" role="img">' + axis + rows + "</svg>";
  }

  function radarChart(axes, entries) {
    if (!axes.length || !entries.length) return note("暂无数据");
    var cx = 110, cy = 110, R = 74, n = axes.length;
    var angle = function (i) { return (-90 + (i * 360) / n) * (Math.PI / 180); };
    var point = function (i, r) { return [cx + Math.cos(angle(i)) * r, cy + Math.sin(angle(i)) * r]; };

    var rings = [0.25, 0.5, 0.75, 1].map(function (f) {
      var pts = axes.map(function (_, i) {
        return point(i, R * f).map(function (v) { return v.toFixed(1); }).join(",");
      }).join(" ");
      return '<polygon points="' + pts + '" fill="none" stroke="#d8e3da" stroke-width="1"/>';
    }).join("");

    var labels = axes.map(function (key, i) {
      var p = point(i, R + 16);
      var anchor = Math.abs(p[0] - cx) < 6 ? "middle" : p[0] > cx ? "start" : "end";
      return '<text x="' + p[0].toFixed(1) + '" y="' + (p[1] + 3).toFixed(1) +
        '" font-size="8" fill="#66746c" text-anchor="' + anchor + '">' +
        esc(metricLabel(key)) + "</text>";
    }).join("");

    var shapes = entries.map(function (entry, index) {
      var stroke = entry.color || color(index);
      var pts = axes.map(function (key, i) {
        var v = Math.max(0, Math.min(1, Number(entry.values[key]) || 0));
        return point(i, R * v).map(function (c) { return c.toFixed(1); }).join(",");
      }).join(" ");
      return '<polygon points="' + pts + '" fill="' + stroke + '" fill-opacity="0.13" stroke="' +
        stroke + '" stroke-width="1.6"/>';
    }).join("");

    return '<svg class="an-chart is-compact" viewBox="0 0 220 220" role="img">' +
      rings + shapes + labels + "</svg>";
  }

  function heatmap(rows, cols, lookup, labelFor) {
    if (!rows.length || !cols.length) return note("暂无数据");
    var cellW = 54, cellH = 26, padL = 62, padT = 34;
    var W = padL + cols.length * cellW + 8;
    var H = padT + rows.length * cellH + 6;
    var max = 0;
    rows.forEach(function (r) {
      cols.forEach(function (c) { max = Math.max(max, lookup(r, c) || 0); });
    });
    if (max <= 0) max = 1;

    var header = cols.map(function (c, i) {
      return '<text x="' + (padL + i * cellW + cellW / 2) + '" y="' + (padT - 8) +
        '" font-size="8.5" fill="#66746c" text-anchor="middle">' + esc(c) + "</text>";
    }).join("");

    var body = rows.map(function (r, ri) {
      var label = '<text x="' + (padL - 8) + '" y="' + (padT + ri * cellH + cellH / 2 + 3) +
        '" font-size="9" fill="#3f4d45" text-anchor="end">' + esc(labelFor ? labelFor(r) : r) + "</text>";
      var cells = cols.map(function (c, ci) {
        var value = lookup(r, c) || 0;
        var alpha = value <= 0 ? 0.04 : 0.12 + 0.78 * (value / max);
        return '<rect x="' + (padL + ci * cellW) + '" y="' + (padT + ri * cellH) +
          '" width="' + (cellW - 3) + '" height="' + (cellH - 3) +
          '" rx="3" fill="#0e7a58" fill-opacity="' + alpha.toFixed(3) + '"><title>' +
          esc(String(r) + " · " + String(c) + "：" + num(value, 3)) + "</title></rect>";
      }).join("");
      return label + cells;
    }).join("");

    return '<svg class="an-chart is-compact" viewBox="0 0 ' + W + " " + H + '" role="img">' +
      header + body + "</svg>";
  }

  /* -------------------------------------------------------------- sections */

  function renderOverview() {
    var data = state.overview;
    if (!data) return;
    var span = data.day_span ? "Day " + data.day_span.first + " – " + data.day_span.last : "—";
    var cards = [
      { label: "参与智能体", value: data.agent_count, hint: data.metric_count + " 项状态指标" },
      { label: "状态采样步数", value: data.step_count, hint: span },
      { label: "回放帧数", value: data.frame_count, hint: data.finished ? "已完成" : "运行中" },
      { label: "环境事件", value: data.event_total, hint: "累计注入" },
      { label: "日记条目", value: data.diary_count, hint: "跨天叙事" },
      { label: "社会关系", value: data.relationship_total, hint: "含亲属/熟人" },
    ];
    $("anOverview").innerHTML = cards.map(function (card) {
      return '<article class="an-kpi"><span class="an-kpi-label">' + esc(card.label) +
        '</span><strong class="an-kpi-value">' + esc(card.value == null ? "—" : card.value) +
        '</strong><span class="an-kpi-hint">' + esc(card.hint) + "</span></article>";
    }).join("");

    var movers = (data.top_movers || []).map(function (item) {
      return { label: metricLabel(item.metric), value: item.mean_delta, display: (item.mean_delta > 0 ? "+" : "") + num(item.mean_delta, 3) };
    });
    $("anMovers").innerHTML = movers.length
      ? barChart(movers, { diverging: true })
      : note("尚未产生状态变化。运行一次仿真后刷新。");

    var meta = data.sim_meta || {};
    $("anRunMeta").innerHTML = [
      ["仿真天数", meta.sim_days],
      ["每天秒数", meta.seconds_per_day],
      ["时间步长", meta.time_step_minutes == null ? "默认" : meta.time_step_minutes],
      ["地图", meta.map_path],
      ["生成时间", data.generated_at],
      ["最后更新", data.last_updated],
    ].map(function (pair) {
      return '<div><dt>' + esc(pair[0]) + "</dt><dd>" + esc(pair[1] == null || pair[1] === "" ? "—" : pair[1]) + "</dd></div>";
    }).join("");
  }

  function agentColor(agentId) {
    var index = (state.history ? state.history.agents : []).findIndex(function (a) {
      return String(a.id) === String(agentId);
    });
    return color(index < 0 ? 0 : index);
  }

  function renderStateControls() {
    var data = state.history;
    if (!data || !data.available) return;
    $("anMetricPicker").innerHTML = data.metrics.map(function (key) {
      var on = state.metrics.indexOf(key) >= 0;
      return '<button type="button" class="an-chip' + (on ? " is-on" : "") +
        '" data-metric="' + esc(key) + '">' + esc(metricLabel(key)) + "</button>";
    }).join("");
    $("anAgentPicker").innerHTML = data.agents.map(function (agent) {
      var on = state.agents.indexOf(String(agent.id)) >= 0;
      return '<button type="button" class="an-chip' + (on ? " is-on" : "") +
        '" data-agent="' + esc(agent.id) + '" style="--chip:' + agentColor(agent.id) + '">' +
        '<i class="an-swatch"></i>' + esc(agent.name) + "</button>";
    }).join("");
  }

  function renderStateCharts() {
    var data = state.history;
    if (!data || !data.available) {
      $("anStateGrid").innerHTML = note("尚无状态历史。运行仿真后会生成 output/state/agent_state_history.csv。");
      $("anStateDelta").innerHTML = "";
      $("anStateRadar").innerHTML = "";
      return;
    }
    if (!state.metrics.length || !state.agents.length) {
      $("anStateGrid").innerHTML = note("请至少选择一个指标和一位居民。");
      $("anStateDelta").innerHTML = "";
      $("anStateRadar").innerHTML = "";
      return;
    }

    $("anStateGrid").innerHTML = state.metrics.map(function (metric) {
      var perAgent = data.series[metric] || {};
      var series = state.agents.map(function (agentId) {
        return { label: agentId, color: agentColor(agentId), points: perAgent[agentId] || [] };
      });
      var deltas = data.deltas[metric] || {};
      var mean = state.agents.reduce(function (sum, agentId) {
        var stats = deltas[agentId];
        return sum + (stats && stats.delta != null ? stats.delta : 0);
      }, 0) / state.agents.length;
      var badge = (mean > 0 ? "+" : "") + num(mean, 3);
      return '<article class="an-card"><header class="an-card-head"><h4>' + esc(metricLabel(metric)) +
        '</h4><span class="an-badge ' + (mean >= 0 ? "is-up" : "is-down") + '">Δ ' + esc(badge) +
        "</span></header>" + lineChart(series, { yMin: 0, yMax: 1 }) + "</article>";
    }).join("");

    // Start → end movement, one bar per metric per selected agent.
    var bars = [];
    state.metrics.forEach(function (metric) {
      state.agents.forEach(function (agentId) {
        var stats = (data.deltas[metric] || {})[agentId];
        if (!stats || stats.delta == null) return;
        var name = (data.agents.find(function (a) { return String(a.id) === agentId; }) || {}).name || agentId;
        bars.push({
          label: metricLabel(metric) + (state.agents.length > 1 ? " · " + name : ""),
          value: stats.delta,
          display: num(stats.first, 2) + " → " + num(stats.last, 2),
        });
      });
    });
    $("anStateDelta").innerHTML = bars.length
      ? barChart(bars, { diverging: true, labelWidth: 118 })
      : note("暂无变化数据");

    var axes = state.metrics.slice(0, 9);
    var entries = state.agents.map(function (agentId) {
      var values = {};
      axes.forEach(function (metric) {
        var stats = (data.deltas[metric] || {})[agentId];
        values[metric] = stats ? stats.last : 0;
      });
      return { label: agentId, color: agentColor(agentId), values: values };
    });
    $("anStateRadar").innerHTML = radarChart(axes, entries);
  }

  function renderEconomy() {
    var data = state.economy;
    if (!data || !data.available) {
      $("anEconGrid").innerHTML = note("尚无经济数据。开启经济模块运行仿真后会生成 output/economy/。");
      $("anEconWealth").innerHTML = "";
      $("anEconMacro").innerHTML = "";
      return;
    }

    var ledgers = data.ledger.filter(function (item) {
      return !state.agents.length || state.agents.indexOf(String(item.id)) >= 0;
    });
    if (!ledgers.length) ledgers = data.ledger;

    $("anEconSeriesPicker").innerHTML = data.series_keys.map(function (key) {
      var on = state.econSeries.indexOf(key) >= 0;
      return '<button type="button" class="an-chip' + (on ? " is-on" : "") +
        '" data-econ="' + esc(key) + '">' + esc(ECON_LABELS[key] || key) + "</button>";
    }).join("");

    $("anEconGrid").innerHTML = state.econSeries.map(function (key) {
      var series = ledgers.map(function (item) {
        return { label: item.name, color: agentColor(item.id), points: item[key] || [] };
      });
      var labels = (ledgers[0] && ledgers[0].days || []).map(function (day) { return "D" + day; });
      var bounded = key === "engel_coefficient" || key === "econ_security";
      return '<article class="an-card"><header class="an-card-head"><h4>' +
        esc(ECON_LABELS[key] || key) + "</h4></header>" +
        lineChart(series, bounded ? { yMin: 0, yMax: 1, xLabels: labels } : { xLabels: labels }) +
        "</article>";
    }).join("");

    var wealth = data.wealth.slice(0, 12).map(function (item) {
      return { label: item.name, value: item.balance, display: compact(item.balance) };
    });
    $("anEconWealth").innerHTML = barChart(wealth, { labelWidth: 84 });

    var macro = data.macro || {};
    var chips = [
      ["宏观周期", macro.phase || "—"],
      ["周期进度", macro.phase_day_counter == null ? "—" : macro.phase_day_counter + " / " + macro.phase_duration],
      ["通胀率", macro.inflation_rate == null ? "—" : (macro.inflation_rate * 100).toFixed(2) + "%"],
      ["失业率", macro.unemployment_rate == null ? "—" : (macro.unemployment_rate * 100).toFixed(2) + "%"],
      ["累计通胀", macro.cumulative_inflation == null ? "—" : macro.cumulative_inflation.toFixed(4)],
    ];
    if (data.conservation) {
      chips.push(["货币守恒漂移", num(data.conservation.drift, 4)]);
      chips.push(["系统总量", compact(data.conservation.system_total)]);
    }
    $("anEconMacro").innerHTML = chips.map(function (pair) {
      return '<div><dt>' + esc(pair[0]) + "</dt><dd>" + esc(pair[1]) + "</dd></div>";
    }).join("");
  }

  // Deterministic spring layout: agents seeded on a circle, ghost ties pushed
  // outward from their owner, then relaxed. No RNG, so the graph is stable
  // across reloads.
  function layoutGraph(nodes, links, width, height) {
    var positions = {}, agents = nodes.filter(function (n) { return n.kind === "agent"; });
    var cx = width / 2, cy = height / 2;
    nodes.forEach(function (node, index) {
      var ring = node.kind === "agent" ? Math.min(width, height) * 0.18 : Math.min(width, height) * 0.38;
      var total = node.kind === "agent" ? Math.max(agents.length, 1) : nodes.length;
      var theta = (index * 2 * Math.PI) / total;
      positions[node.id] = { x: cx + Math.cos(theta) * ring, y: cy + Math.sin(theta) * ring };
    });

    var index = {};
    nodes.forEach(function (node) { index[node.id] = node; });
    for (var step = 0; step < 220; step++) {
      var force = {};
      nodes.forEach(function (node) { force[node.id] = { x: 0, y: 0 }; });
      // Repulsion between every pair — node counts here are in the hundreds
      // at most, so O(n^2) is cheap enough.
      for (var i = 0; i < nodes.length; i++) {
        for (var j = i + 1; j < nodes.length; j++) {
          var a = positions[nodes[i].id], b = positions[nodes[j].id];
          var dx = a.x - b.x, dy = a.y - b.y;
          var dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
          var push = 900 / (dist * dist);
          force[nodes[i].id].x += (dx / dist) * push;
          force[nodes[i].id].y += (dy / dist) * push;
          force[nodes[j].id].x -= (dx / dist) * push;
          force[nodes[j].id].y -= (dy / dist) * push;
        }
      }
      links.forEach(function (link) {
        var a = positions[link.source], b = positions[link.target];
        if (!a || !b) return;
        var dx = b.x - a.x, dy = b.y - a.y;
        var dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        // Closer ties sit nearer: rest length shrinks with closeness.
        var rest = 130 - 70 * (link.closeness || 0);
        var pull = (dist - rest) * 0.02;
        a.x += (dx / dist) * pull; a.y += (dy / dist) * pull;
        b.x -= (dx / dist) * pull; b.y -= (dy / dist) * pull;
      });
      nodes.forEach(function (node) {
        var p = positions[node.id];
        p.x += Math.max(-6, Math.min(6, force[node.id].x));
        p.y += Math.max(-6, Math.min(6, force[node.id].y));
        // Gentle pull to center keeps disconnected components on canvas.
        p.x += (cx - p.x) * 0.004;
        p.y += (cy - p.y) * 0.004;
        p.x = Math.max(24, Math.min(width - 24, p.x));
        p.y = Math.max(20, Math.min(height - 20, p.y));
      });
    }
    return positions;
  }

  function renderSocial() {
    var data = state.social;
    if (!data || !data.available) {
      $("anSocialGraph").innerHTML = note("尚无关系数据。运行仿真后会生成 output/memory/agent_*_relationships.json。");
      $("anSocialTiers").innerHTML = "";
      $("anSocialRoles").innerHTML = "";
      return;
    }
    var W = 640, H = 420;
    var positions = layoutGraph(data.nodes, data.links, W, H);

    var edges = data.links.map(function (link) {
      var a = positions[link.source], b = positions[link.target];
      if (!a || !b) return "";
      var trust = link.trust || 0;
      return '<line x1="' + a.x.toFixed(1) + '" y1="' + a.y.toFixed(1) + '" x2="' + b.x.toFixed(1) +
        '" y2="' + b.y.toFixed(1) + '" stroke="' + (trust >= 0.6 ? "#0e7a58" : trust >= 0.35 ? "#8aa79a" : "#c9b7a0") +
        '" stroke-width="' + (0.6 + 3 * (link.closeness || 0)).toFixed(2) +
        '" stroke-opacity="0.6"><title>' +
        esc(link.role + " 亲密度 " + num(link.closeness, 2) + " · 信任 " + num(trust, 2)) +
        "</title></line>";
    }).join("");

    var dots = data.nodes.map(function (node) {
      var p = positions[node.id];
      if (!p) return "";
      var isAgent = node.kind === "agent";
      var r = isAgent ? 9 : 5;
      return '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="' + r +
        '" fill="' + (isAgent ? agentColor(node.agent_id) : "#c8d6cb") +
        '" stroke="#ffffff" stroke-width="1.5"><title>' +
        esc(node.label + (node.role ? " · " + node.role : "")) + "</title></circle>" +
        (isAgent
          ? '<text x="' + p.x.toFixed(1) + '" y="' + (p.y - 13).toFixed(1) +
            '" font-size="9.5" fill="#243029" text-anchor="middle">' + esc(node.label) + "</text>"
          : '<text x="' + p.x.toFixed(1) + '" y="' + (p.y + 13).toFixed(1) +
            '" font-size="7.5" fill="#7e8b84" text-anchor="middle">' + esc(node.label) + "</text>");
    }).join("");

    $("anSocialGraph").innerHTML =
      '<svg class="an-graph" viewBox="0 0 ' + W + " " + H + '" role="img">' + edges + dots + "</svg>";

    var tierNames = { inner: "核心圈", close: "亲近", acquaintance: "熟人", weak: "弱连接", unknown: "未分层" };
    $("anSocialTiers").innerHTML = barChart(
      Object.keys(data.tier_counts).map(function (tier) {
        return { label: tierNames[tier] || tier, value: data.tier_counts[tier], display: String(data.tier_counts[tier]) };
      }), { labelWidth: 70 });
    $("anSocialRoles").innerHTML = barChart(
      Object.keys(data.role_counts).map(function (role) {
        return { label: role, value: data.role_counts[role], display: String(data.role_counts[role]) };
      }), { labelWidth: 110 });
  }

  function renderBehavior() {
    var data = state.behavior;
    if (!data || !data.available) {
      $("anPlaces").innerHTML = note("尚无行为数据。运行仿真后会生成 output/memory/agent_*_locations.json。");
      $("anModes").innerHTML = "";
      $("anHeatmap").innerHTML = "";
      $("anHours").innerHTML = "";
      $("anHabits").innerHTML = "";
      return;
    }

    $("anPlaces").innerHTML = barChart(
      data.places.slice(0, 14).map(function (item) {
        return { label: item.name, value: item.visits, display: String(item.visits) };
      }), { labelWidth: 140 });

    $("anModes").innerHTML = barChart(
      data.modes.map(function (item) {
        return { label: item.mode, value: item.trips, display: String(item.trips) };
      }), { labelWidth: 64 });

    var cells = {};
    (data.heatmap.cells || []).forEach(function (cell) {
      cells[cell.period + "||" + cell.context] = cell.value;
    });
    $("anHeatmap").innerHTML = heatmap(
      data.heatmap.periods, data.heatmap.contexts,
      function (period, context) { return cells[period + "||" + context]; },
      function (period) { return PERIOD_LABELS[period] || period; });

    var hours = data.schedule_hours || [];
    $("anHours").innerHTML = hours.some(function (h) { return h.count > 0; })
      ? lineChart([{ label: "日程", color: "#0e7a58", points: hours.map(function (h) { return h.count; }) }],
          { yMin: 0, xLabels: hours.map(function (h) { return h.hour + "时"; }) })
      : note("暂无日程数据");

    $("anHabits").innerHTML = data.habits.length
      ? '<table class="an-table"><thead><tr><th>居民</th><th>时段</th><th>情境</th><th>活动</th><th>强度</th></tr></thead><tbody>' +
        data.habits.map(function (habit) {
          return "<tr><td>" + esc(habit.name || habit.agent_id) + "</td><td>" +
            esc(PERIOD_LABELS[habit.period] || habit.period) + "</td><td>" + esc(habit.context) +
            '</td><td class="an-cell-wide">' + esc(habit.activity) + "</td><td>" +
            num(habit.strength, 3) + "</td></tr>";
        }).join("") + "</tbody></table>"
      : note("暂无习惯数据");
  }

  function renderEvents() {
    var data = state.events;
    if (!data || !data.available) {
      $("anEventTimeline").innerHTML = note("尚无事件数据。运行仿真后会生成 output/visualization/simulation_trace.json。");
      $("anEventTypes").innerHTML = "";
      $("anEventImpacts").innerHTML = "";
      return;
    }

    var days = data.timeline.map(function (item) { return item.day; }).filter(function (d) { return d != null; });
    var minDay = days.length ? Math.min.apply(null, days) : 0;
    var maxDay = days.length ? Math.max.apply(null, days) : 1;
    // Lane labels are event type names ("technology", "economic", …), so the
    // left gutter has to clear the widest of them.
    var W = 640, H = 150, padR = 16, padT = 24, padB = 26;
    var padL = Math.max(40, Object.keys(data.type_counts).reduce(function (max, type) {
      return Math.max(max, type.length);
    }, 0) * 4.6 + 20);
    // Inset the first dot past the lane label — a Day-1 event drawn exactly on
    // padL would otherwise overlap the longest type name.
    var x0 = padL + 9;
    var xFor = function (day) {
      var t = maxDay > minDay ? (day - minDay) / (maxDay - minDay) : 0.5;
      return x0 + t * (W - x0 - padR);
    };

    var types = Object.keys(data.type_counts);
    var laneY = {};
    types.forEach(function (type, index) {
      laneY[type] = padT + (index * (H - padT - padB)) / Math.max(types.length - 1, 1);
    });

    var lanes = types.map(function (type) {
      return '<line x1="' + padL + '" y1="' + laneY[type].toFixed(1) + '" x2="' + (W - padR) +
        '" y2="' + laneY[type].toFixed(1) + '" stroke="#e8efe9" stroke-width="1"/>' +
        '<text x="' + (padL - 4) + '" y="' + (laneY[type] + 3).toFixed(1) +
        '" font-size="8" fill="#8a968f" text-anchor="end">' + esc(type) + "</text>";
    }).join("");

    var dots = data.timeline.map(function (frame) {
      return frame.events.map(function (event) {
        var y = laneY[event.type];
        if (y == null || frame.day == null) return "";
        return '<circle cx="' + xFor(frame.day).toFixed(1) + '" cy="' + y.toFixed(1) +
          '" r="' + (2.5 + 5 * (event.severity || 0)).toFixed(1) + '" fill="' +
          (EVENT_COLORS[event.type] || "#66746c") + '" fill-opacity="0.65"><title>' +
          esc("Day " + frame.day + " · " + event.name + "（强度 " + num(event.severity, 2) + "）") +
          "</title></circle>";
      }).join("");
    }).join("");

    var axis = '<text x="' + padL + '" y="' + (H - 6) + '" font-size="8" fill="#8a968f">Day ' + minDay +
      '</text><text x="' + (W - padR) + '" y="' + (H - 6) +
      '" font-size="8" fill="#8a968f" text-anchor="end">Day ' + maxDay + "</text>";

    $("anEventTimeline").innerHTML =
      '<svg class="an-chart is-wide" viewBox="0 0 ' + W + " " + H + '" role="img">' +
      lanes + dots + axis + "</svg>" +
      '<div class="an-event-list">' + data.timeline.slice(-30).reverse().map(function (frame) {
        return frame.events.map(function (event) {
          return '<div class="an-event"><span class="an-event-day">Day ' + esc(frame.day) +
            '</span><span class="an-event-dot" style="background:' +
            (EVENT_COLORS[event.type] || "#66746c") + '"></span><span class="an-event-name">' +
            esc(event.name) + '</span><span class="an-event-meta">' + esc(event.scope) + " · 强度 " +
            num(event.severity, 2) + "</span></div>";
        }).join("");
      }).join("") + "</div>";

    $("anEventTypes").innerHTML = barChart(types.map(function (type) {
      return { label: type, value: data.type_counts[type], display: String(data.type_counts[type]), color: EVENT_COLORS[type] };
    }), { labelWidth: 80 });

    $("anEventImpacts").innerHTML = barChart(Object.keys(data.impact_counts).map(function (tag) {
      return { label: tag, value: data.impact_counts[tag], display: String(data.impact_counts[tag]) };
    }), { labelWidth: 120 });
  }

  /* ----------------------------------------------------------------- wiring */

  function pickDefaults() {
    var data = state.history;
    if (!data || !data.available) return;
    if (!state.agents.length) {
      state.agents = data.agents.slice(0, 4).map(function (agent) { return String(agent.id); });
    }
    if (!state.metrics.length) {
      // Rank by how much each metric moved so the first screenful shows the
      // signal, but still fill up to six charts when few metrics changed.
      state.metrics = data.metrics.slice().sort(function (a, b) {
        return Math.abs(meanDelta(b)) - Math.abs(meanDelta(a));
      }).slice(0, 6);
    }
  }

  function meanDelta(metric) {
    var deltas = (state.history.deltas || {})[metric] || {};
    var values = Object.keys(deltas).map(function (key) { return deltas[key].delta || 0; });
    if (!values.length) return 0;
    return values.reduce(function (a, b) { return a + b; }, 0) / values.length;
  }

  function toggle(list, value) {
    var index = list.indexOf(value);
    if (index >= 0) list.splice(index, 1);
    else list.push(value);
    return list;
  }

  function bindPickers() {
    $("anMetricPicker").addEventListener("click", function (event) {
      var button = event.target.closest("[data-metric]");
      if (!button) return;
      toggle(state.metrics, button.dataset.metric);
      renderStateControls();
      renderStateCharts();
    });
    $("anAgentPicker").addEventListener("click", function (event) {
      var button = event.target.closest("[data-agent]");
      if (!button) return;
      toggle(state.agents, button.dataset.agent);
      renderStateControls();
      renderStateCharts();
      renderEconomy();
    });
    $("anEconSeriesPicker").addEventListener("click", function (event) {
      var button = event.target.closest("[data-econ]");
      if (!button) return;
      toggle(state.econSeries, button.dataset.econ);
      renderEconomy();
    });
    $("anRefreshBtn").addEventListener("click", function () { load(); });
  }

  async function load() {
    var status = $("anStatus");
    status.textContent = "加载中…";
    status.className = "an-status is-busy";
    try {
      var results = await Promise.all([
        api("/api/analytics/overview"),
        api("/api/analytics/state-history"),
        api("/api/analytics/economy"),
        api("/api/analytics/social"),
        api("/api/analytics/behavior"),
        api("/api/analytics/events"),
      ]);
      state.overview = results[0];
      state.history = results[1];
      state.economy = results[2];
      state.social = results[3];
      state.behavior = results[4];
      state.events = results[5];
      // Drop selections that no longer exist in the new payload.
      state.metrics = state.metrics.filter(function (m) { return state.history.metrics.indexOf(m) >= 0; });
      var ids = state.history.agents.map(function (a) { return String(a.id); });
      state.agents = state.agents.filter(function (a) { return ids.indexOf(a) >= 0; });
      pickDefaults();

      renderOverview();
      renderStateControls();
      renderStateCharts();
      renderEconomy();
      renderSocial();
      renderBehavior();
      renderEvents();

      status.textContent = state.overview.finished ? "已完成的运行" : "运行中 / 部分数据";
      status.className = "an-status" + (state.overview.finished ? " is-ok" : " is-busy");
    } catch (error) {
      status.textContent = "加载失败：" + error.message;
      status.className = "an-status is-error";
    }
  }

  bindPickers();
  load();
})();
