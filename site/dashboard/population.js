/* Population Studio — 造一座小镇，然后按群体模拟它。
 *
 * 五步：群体定义 → 人口结构 → 状态分布 → 群体模拟 → 验证与复核。
 *
 * 三个刻意的设计：
 *
 * - 旋钮定义来自 `GET /api/population/schema`，不在这里再抄一份。九维状态变量在本仓库
 *   已经被声明了两次（dashboard_server.py 与 studio.js）且靠手工同步，人口旋钮不该变成第三份。
 * - 图表全部手写 SVG。site/dashboard 没有构建步骤也没有 vendored 图表库，为几个坐标轴引入
 *   CDN 依赖会让 dashboard 失去离线可用性。
 * - 每个主操作都有**面板内的按钮**，不依赖页脚按钮改 label。靠 label 变化承载主操作
 *   是很差的可发现性——用户找不到就会以为功能坏了。
 */
(function () {
  "use strict";

  var state = {
    step: 1,
    schema: null,
    spec: null,
    preview: null,
    population: null,
    groupRun: null,
    verdict: null,
    written: [],
    run: {
      days: 7,
      budget: 20,
      audit: 0.03,
      coupling: 0.7,
      useLlm: false,
      provider: "",
      seed: 1,
    },
    busy: false,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function pct(v) {
    return Math.round(Number(v) * 100) + "%";
  }

  function money(v) {
    return Number(v).toLocaleString("zh-CN", { maximumFractionDigits: 0 });
  }

  /* ------------------------------------------------------------------- api */

  /** Every failure ends up visible and always clears `busy`.
   *
   *  The previous version had no `.catch`: one failed request left `busy`
   *  stuck true and every later click became a silent no-op — which looks
   *  exactly like "the button does nothing". */
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
        return { error: "无法连接到后端：" + (err && err.message ? err.message : err) };
      });
  }

  function fail(message) {
    state.busy = false;
    setProgress("❌ " + message, 0, true);
    render();
  }

  /* ------------------------------------------------------------------ spec */

  function deepGet(obj, path) {
    var parts = path.split(".");
    var cur = obj;
    for (var i = 0; i < parts.length; i++) {
      if (cur == null) return undefined;
      cur = cur[parts[i]];
    }
    return cur;
  }

  function deepSet(obj, path, value) {
    var parts = path.split(".");
    var cur = obj;
    for (var i = 0; i < parts.length - 1; i++) {
      if (typeof cur[parts[i]] !== "object" || cur[parts[i]] === null) cur[parts[i]] = {};
      cur = cur[parts[i]];
    }
    cur[parts[parts.length - 1]] = value;
  }

  /* ---------------------------------------------------------------- charts */

  function svg(width, height, inner) {
    return (
      '<svg viewBox="0 0 ' + width + " " + height + '" preserveAspectRatio="xMidYMid meet">' +
      inner + "</svg>"
    );
  }

  function agePyramid(bins) {
    if (!bins || !bins.length) return "<p class='pop-hint'>无数据</p>";
    var W = 320, H = 200, mid = W / 2, rowH = Math.max(4, (H - 20) / bins.length);
    var max = 1;
    bins.forEach(function (b) { max = Math.max(max, b.male, b.female); });
    var parts = [];
    bins.forEach(function (b, i) {
      var y = 10 + i * rowH;
      var lw = (b.male / max) * (mid - 26);
      var rw = (b.female / max) * (mid - 26);
      parts.push('<rect x="' + (mid - lw) + '" y="' + y + '" width="' + lw + '" height="' + (rowH - 1) + '" fill="#2563eb" opacity="0.75"><title>' + b.age_from + "-" + b.age_to + " 岁 男 " + b.male + " 人</title></rect>");
      parts.push('<rect x="' + mid + '" y="' + y + '" width="' + rw + '" height="' + (rowH - 1) + '" fill="#db2777" opacity="0.7"><title>' + b.age_from + "-" + b.age_to + " 岁 女 " + b.female + " 人</title></rect>");
      if (i % 3 === 0) {
        parts.push('<text x="' + mid + '" y="' + (y + rowH - 2) + '" font-size="8" text-anchor="middle" fill="#6b7280">' + b.age_from + "</text>");
      }
    });
    parts.push('<text x="6" y="9" font-size="9" fill="#2563eb">← 男</text>');
    parts.push('<text x="' + (W - 26) + '" y="9" font-size="9" fill="#db2777">女 →</text>');
    return svg(W, H, parts.join(""));
  }

  function lorenz(points) {
    if (!points || !points.length) return "<p class='pop-hint'>无数据</p>";
    var W = 300, H = 200, pad = 24;
    var path = points.map(function (p, i) {
      var x = pad + p.population_share * (W - pad * 2);
      var y = H - pad - p.income_share * (H - pad * 2);
      return (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
    }).join(" ");
    return svg(W, H,
      '<line x1="' + pad + '" y1="' + (H - pad) + '" x2="' + (W - pad) + '" y2="' + pad + '" stroke="#9ca3af" stroke-dasharray="3 3"><title>完全平均线</title></line>' +
      '<path d="' + path + '" fill="none" stroke="#2563eb" stroke-width="2"><title>实际收入分布</title></path>' +
      '<line x1="' + pad + '" y1="' + (H - pad) + '" x2="' + (W - pad) + '" y2="' + (H - pad) + '" stroke="#d1d5db"/>' +
      '<line x1="' + pad + '" y1="' + pad + '" x2="' + pad + '" y2="' + (H - pad) + '" stroke="#d1d5db"/>' +
      '<text x="' + (W / 2) + '" y="' + (H - 6) + '" font-size="8" text-anchor="middle" fill="#6b7280">← 由穷到富的人口累计占比 →</text>');
  }

  function barChart(rows, opts) {
    opts = opts || {};
    if (!rows || !rows.length) return "<p class='pop-hint'>无数据</p>";
    var W = 300, H = 180, pad = 26;
    var max = 1;
    rows.forEach(function (r) { max = Math.max(max, r.value); });
    var bw = (W - pad * 2) / rows.length;
    var parts = [];
    rows.forEach(function (r, i) {
      var h = (r.value / max) * (H - pad * 2);
      var x = pad + i * bw;
      parts.push('<rect x="' + (x + 1) + '" y="' + (H - pad - h) + '" width="' + (bw - 2) + '" height="' + h + '" fill="' + (opts.color || "#2563eb") + '" opacity="0.8"><title>' + esc(opts.unit ? r.label + " " + opts.unit + "：" + r.value + " 人" : r.label + "：" + r.value) + "</title></rect>");
      if (rows.length <= 26 || i % 2 === 0) {
        parts.push('<text x="' + (x + bw / 2) + '" y="' + (H - pad + 10) + '" font-size="8" text-anchor="middle" fill="#6b7280">' + esc(r.label) + "</text>");
      }
    });
    parts.push('<line x1="' + pad + '" y1="' + (H - pad) + '" x2="' + (W - pad) + '" y2="' + (H - pad) + '" stroke="#d1d5db"/>');
    return svg(W, H, parts.join(""));
  }

  function stateRadar(stats, keys) {
    var W = 300, H = 260, cx = W / 2, cy = H / 2 + 6, R = 84;
    var n = keys.length;
    function point(i, value) {
      var a = (Math.PI * 2 * i) / n - Math.PI / 2;
      return [cx + Math.cos(a) * R * value, cy + Math.sin(a) * R * value];
    }
    function poly(getter, fill, stroke, op) {
      var pts = keys.map(function (k, i) {
        return point(i, Math.max(0, Math.min(1, getter(k)))).map(function (v) { return v.toFixed(1); }).join(",");
      });
      return '<polygon points="' + pts.join(" ") + '" fill="' + fill + '" fill-opacity="' + op + '" stroke="' + stroke + '" stroke-width="1.5"/>';
    }
    var rings = [0.25, 0.5, 0.75, 1].map(function (r) {
      return '<circle cx="' + cx + '" cy="' + cy + '" r="' + R * r + '" fill="none" stroke="#e5e7eb"/>';
    }).join("");
    var labels = keys.map(function (k, i) {
      var p = point(i, 1.2);
      var s = stats[k] || {};
      return '<text x="' + p[0].toFixed(1) + '" y="' + p[1].toFixed(1) + '" font-size="8" text-anchor="middle" fill="#6b7280">' + esc(label(k, "zh")) + "<title>" + esc(label(k, "zh")) + "：均值 " + (s.mean || 0).toFixed(2) + "，四分之一的人低于 " + (s.p25 || 0).toFixed(2) + "，四分之一高于 " + (s.p75 || 0).toFixed(2) + "</title></text>";
    }).join("");
    var band = poly(function (k) { return (stats[k] || {}).p75 || 0; }, "#2563eb", "#93c5fd", 0.15) +
      poly(function (k) { return (stats[k] || {}).p25 || 0; }, "#ffffff", "#93c5fd", 0.9);
    var mean = poly(function (k) { return (stats[k] || {}).mean || 0; }, "none", "#2563eb", 1);
    return svg(W, H, rings + band + mean + labels);
  }

  /* -------------------------------------------------------------- 文案定义 */

  /** 「中文 English」双语标注。标签来自后端 schema 的 `labels`，
   *  不在这里再抄一份——面板之前就是因为一半中文一半英文标识符才显得混乱。
   *  `zhOnly` 用于图表这类空间紧张的地方，英文放在悬停里。 */
  function label(key, mode) {
    var l = (state.schema && state.schema.labels && state.schema.labels[key]) || null;
    if (!l) return key;
    if (mode === "zh") return l.zh;
    if (mode === "en") return l.en;
    return l.zh + " " + l.en;
  }

  function labelHtml(key) {
    var l = (state.schema && state.schema.labels && state.schema.labels[key]) || null;
    if (!l) return esc(key);
    return esc(l.zh) + ' <em class="pop-key">' + esc(l.en) + "</em>";
  }

  var STATE_HELP = {
    emotion: "0 = 长期低落，1 = 长期愉快。会被收入变化、社交反馈、政策冲击推动。",
    stress: "0 = 没有压力，1 = 长期高压。受工作强度、房租、绩效影响。",
    econ_security: "对自己经济状况的安全感。0 = 随时可能撑不住，1 = 很有底气。",
    city_identity: "对这座城市的归属感。0 = 强烈疏离，1 = 强烈认同。外来人口通常偏低。",
    policy_sensitivity: "有多关注政策变化。0 = 几乎不感知，1 = 高度敏感。",
    platform_dependence: "对线上平台的依赖程度。0 = 线下多元收入，1 = 收入和生活高度绑定平台。",
    risk_preference: "0 = 强烈规避风险，1 = 愿意冒险。影响创业、迁移这类决策。",
    voice_propensity: "遇到不合理时会不会发声。0 = 沉默回避，1 = 主动投诉或公开表达。",
    mobility_intent: "想不想离开这座城市。0 = 打算长期定居，1 = 随时准备走。",
  };

  var KNOB_HELP = {
    "size": "要造多少个居民。500 人大约会被划分成 30–40 个群体。人越多越慢，但群体模拟的成本几乎不随人数增长。",
    "seed": "决定所有随机抽样的起点。同样的参数配同样的种子，生成出来的这批人会一模一样——换句话说，把种子记下来，你和同事就能拿到完全一样的小镇。想换一批人但保持人口结构不变，就只改种子。",
    "name": "输出文件的名字前缀，比如填 my_town 会得到 my_town_state_init.csv。",
    "demography.median_age": "把所有人按年龄排队，站在正中间那个人的年龄。它受少儿占比和老龄占比夹逼，可达范围见右侧。",
    "demography.share_under_18": "18 岁以下人口占总人口的比例。",
    "demography.share_over_65": "65 岁及以上人口占总人口的比例。",
    "demography.migrant_share": "非本地户籍的人口比例。外来人口通常城市认同更低、迁移意愿更高。",
    "household.mean_size": "平均每户住几个人。它和「单人户占比」互相牵制——单人户越多，户均规模的上限越低。",
    "household.share_single_person": "一个人独居的家庭占所有家庭的比例。",
    "household.share_multigen": "三代同堂（有老人同住）的家庭比例。受老年人口数量硬约束——没那么多老人就凑不出那么多三代户。",
    "education_work.tertiary_rate": "成年人里拥有大专及以上学历的比例。",
    "education_work.employment_rate": "**劳动年龄人口（18–64 岁）**里有工作的比例，不是全人口口径。儿童和老人本来就不计入。",
    "income.median_monthly": "把所有在业者的月收入排队，正中间那个人的收入（元）。",
    "income.gini": "收入差距有多大。0 = 所有人收入一样，1 = 收入全集中在一个人手上。中国城镇大约 0.4 左右。",
    "psychology.state_sd": "同一个群体内部，人和人之间差异有多大。调到很小 = 所有人几乎一模一样（可用于对照实验），调大 = 群体内部分化明显。",
  };

  var RUN_HELP = {
    days: "模拟多少天。天数越多，群体之间的差异累积得越明显。",
    budget: "每天有多少人会被拎出来按「完整个体」的方式模拟（其余人只跟着自己所属群体走）。这是唯一重要的成本旋钮——群体层几乎不花钱，总开销基本等于这个数字乘以天数。",
    audit: "每天随机抽多少比例的人，专门用来**测量**群体近似有多不准（而不是让它更准）。砍掉它能省一点钱，但运行时你就完全看不到误差了。",
    coupling: "让「邻居之间互相影响」这件事在群体层面也能表达出来。调成 0 的话，同一个群体里所有人每天的变化完全相同，社交网络等于不存在——验证门的 L2 一定不通过。0.7 是目前标定出来的合适值。",
    useLlm: "关闭时用确定性的占位文本代替模型输出，整轮零成本，适合先把参数调顺。打开后会真的调用模型并产生费用。",
    provider: "用哪个后端模型来写群体简报。本地 ollama 模型不产生 API 费用但更慢，云端模型更快但按量计费。",
  };

  function help(text) {
    return text ? ' <span class="pop-q" title="' + esc(text.replace(/\*\*/g, "")) + '">?</span>' : "";
  }

  /* ------------------------------------------------------------- field 构件 */

  function fieldSlider(path, label, min, max, step, fmt) {
    var value = deepGet(state.spec, path);
    return (
      '<div class="pop-field"><label><span>' + esc(label) + help(KNOB_HELP[path]) +
      '</span><span class="pop-value" data-out="' + path + '">' + esc(fmt ? fmt(value) : value) + "</span></label>" +
      '<input type="range" data-path="' + path + '" data-fmt="' + (fmt === pct ? "pct" : fmt === money ? "money" : "raw") +
      '" min="' + min + '" max="' + max + '" step="' + step + '" value="' + value + '" title="' + esc((KNOB_HELP[path] || "").replace(/\*\*/g, "")) + '" /></div>'
    );
  }

  function fieldNumber(path, label, min, max, step) {
    var value = deepGet(state.spec, path);
    return (
      '<div class="pop-field"><label><span>' + esc(label) + help(KNOB_HELP[path]) + "</span></label>" +
      '<input type="number" data-path="' + path + '" min="' + min + '" max="' + max + '" step="' + step +
      '" value="' + value + '" title="' + esc((KNOB_HELP[path] || "").replace(/\*\*/g, "")) + '" /></div>'
    );
  }

  function actionBar(html) {
    return '<div class="pop-actionbar">' + html + "</div>";
  }

  /* --------------------------------------------------------------- step 1 */

  function renderStep1() {
    var desc = (state.schema.preset_descriptions || {})[state.spec.preset];
    var presets = (state.schema.presets || []).map(function (p) {
      var d = (state.schema.preset_descriptions || {})[p] || {};
      return '<option value="' + esc(p) + '"' + (state.spec.preset === p ? " selected" : "") + ">" +
        esc(d.title ? d.title + "（" + p + "）" : p) + "</option>";
    }).join("");

    var descBox = desc
      ? '<div class="pop-presetcard"><h4>' + esc(desc.title) + "</h4><p>" + esc(desc.summary) +
        '</p><p class="pop-usewhen"><b>什么时候用它：</b>' + esc(desc.use_when) + "</p></div>"
      : "";

    return (
      '<div class="pop-card">' +
      '<h2>第 1 步 · 这座小镇是什么样的</h2>' +
      '<p class="pop-lede">先挑一个现成的人口模板，后面几步再微调。每个模板本身都是自洽的，直接用也能跑。</p>' +
      '<div class="pop-grid">' +
      '<div class="pop-field"><label><span>人口模板</span>' + help("挑一个接近你研究场景的起点。选中后下面会显示它具体是什么样的人口。") + "</label>" +
      '<select data-path="preset">' + presets + "</select></div>" +
      fieldNumber("size", "居民人数", 20, 5000, 10) +
      fieldNumber("seed", "随机种子", 0, 2147483647, 1) +
      '<div class="pop-field"><label><span>小镇名称</span>' + help(KNOB_HELP.name) + "</label>" +
      '<input type="text" data-path="name" value="' + esc(state.spec.name) + '" /></div>' +
      "</div>" + descBox +
      '<div class="pop-seedbox"><b>随机种子是什么？</b>' +
      "它决定了「掷骰子」从哪里开始。参数一样、种子一样 → 生成出来的 500 个人完全相同，" +
      "你和同事各自跑一遍会得到同一座小镇，实验因此可复现。" +
      "想在同样的人口结构下换一批人，只改种子即可。</div>" +
      actionBar('<button class="btn" data-go="2">下一步：设定人口结构 →</button>') +
      "</div>"
    );
  }

  /* --------------------------------------------------------------- step 2 */

  function renderStep2() {
    var busy = state.busy;
    return (
      '<div class="pop-card">' +
      '<h2>第 2 步 · 这些人是什么样的</h2>' +
      '<p class="pop-lede">拖动滑块设定你想要的人口特征。这些是「总体比例」，' +
      '至于「什么样的人拿高收入」这类属性之间的关联，由生成器自动拟合。' +
      '参数互相矛盾时，右侧会立刻告诉你该改哪一个。</p>' +
      '<div class="pop-grid">' +
      fieldSlider("demography.median_age", "中位年龄（岁）", 18, 65, 1) +
      fieldSlider("demography.share_under_18", "未成年人占比", 0, 0.4, 0.01, pct) +
      fieldSlider("demography.share_over_65", "65 岁以上占比", 0, 0.5, 0.01, pct) +
      fieldSlider("demography.migrant_share", "外地户籍占比", 0, 0.9, 0.01, pct) +
      fieldSlider("household.mean_size", "户均人数", 1, 6, 0.1) +
      fieldSlider("household.share_single_person", "独居家庭占比", 0, 0.8, 0.01, pct) +
      fieldSlider("household.share_multigen", "三代同堂占比", 0, 0.6, 0.01, pct) +
      fieldSlider("education_work.tertiary_rate", "大专及以上学历占比", 0, 1, 0.01, pct) +
      fieldSlider("education_work.employment_rate", "就业率（劳动年龄口径）", 0, 1, 0.01, pct) +
      fieldSlider("income.median_monthly", "月收入中位数（元）", 1000, 40000, 100, money) +
      fieldSlider("income.gini", "收入差距（基尼系数）", 0.15, 0.65, 0.01) +
      "</div>" +
      actionBar(
        '<button class="btn primary" id="popGenerate"' + (busy ? " disabled" : "") + ">" +
        (busy ? "正在生成…" : state.population ? "↻ 重新生成这批人" : "✦ 生成这 " + state.spec.size + " 个人") +
        "</button>" +
        (state.population ? '<button class="btn ghost" data-go="3">下一步：状态分布 →</button>' : "") +
        '<span class="pop-actionhint">' +
        (state.population ? "已生成。改动上面的滑块后需要重新生成。" : "生成大约需要 1–3 秒，不消耗任何模型费用。") +
        "</span>"
      ) +
      "</div>" + (state.population ? achievedCard() : "")
    );
  }

  function achievedCard() {
    var rep = state.population.report;
    var rows = Object.keys(rep.achieved).map(function (k) {
      var e = rep.achieved[k];
      var rel = Math.abs(e.target) > 1e-9 ? Math.abs(e.delta) / Math.abs(e.target) : 0;
      var color = rel > 0.1 ? "#dc2626" : rel > 0.05 ? "#d97706" : "#16a34a";
      var note = rel > 0.1 ? "差得较多" : rel > 0.05 ? "略有出入" : "基本达成";
      return "<tr><td>" + labelHtml(k) + '</td><td class="num">' + e.target +
        '</td><td class="num">' + e.achieved + '</td><td class="num" style="color:' + color + '" title="' +
        esc(note) + '">' + (rel * 100).toFixed(1) + "%</td></tr>";
    }).join("");

    var gaps = (rep.achieved && state.population.worst_gaps) || [];
    var gapNote = gaps.length && gaps[0].relative_error > 0.05
      ? '<p class="pop-warn">有参数没能完全达成——通常是因为你要的几个条件互相冲突（比如老人不够多却要求很多三代同堂户）。' +
        "上表里标红的行就是被牺牲掉的那些。不影响使用，但写论文时应当说明。</p>"
      : "";

    return (
      '<div class="pop-card"><h2>生成结果：你要的 vs 实际拿到的</h2>' +
      '<p class="pop-lede">生成器不会假装每个参数都达成了。达不到的会在这里显示偏差。</p>' + gapNote +
      '<table class="pop-table"><thead><tr><th>指标 Metric</th><th class="num">你要的 Target</th>' +
      '<th class="num">实际 Achieved</th><th class="num">偏差 Error</th></tr></thead><tbody>' + rows + "</tbody></table>" +
      '<div class="pop-charts">' +
      '<div class="pop-chart"><h4>年龄金字塔</h4>' + agePyramid(rep.charts.age_pyramid) +
      '<p class="pop-chart-note">每一横条是一个 5 岁年龄段，左蓝为男、右粉为女，条越长人越多。鼠标悬停看具体人数。</p></div>' +
      '<div class="pop-chart"><h4>收入差距</h4>' + lorenz(rep.charts.lorenz) +
      '<p class="pop-chart-note">虚线代表「所有人收入完全一样」。实线离虚线越远，贫富差距越大。</p></div>' +
      '<div class="pop-chart"><h4>家庭规模</h4>' +
      barChart((rep.charts.household_sizes || []).map(function (r) { return { label: r.size, value: r.count }; }), { unit: "人户" }) +
      '<p class="pop-chart-note">横轴是每户人数，纵轴是这样的家庭有多少个。</p></div>' +
      '<div class="pop-chart"><h4>社交关系分布</h4>' +
      barChart((rep.network.degree_histogram || []).slice(0, 24).map(function (r) { return { label: r.degree, value: r.count }; }), { color: "#0891b2", unit: "个朋友" }) +
      '<p class="pop-chart-note">横轴是一个人有多少条社交关系，纵轴是这样的人有多少个。' +
      "这张网络是「小世界」的：熟人抱团（聚类 " + rep.network.clustering.toFixed(2) +
      "，随机连线只有 " + rep.network.random_clustering.toFixed(2) + "），但任意两人平均只隔 " +
      rep.network.mean_path_length.toFixed(1) + " 层关系。</p></div>" +
      "</div></div>"
    );
  }

  /* --------------------------------------------------------------- step 3 */

  function renderStep3() {
    var keys = state.schema.state_var_keys || [];
    var sliders = keys.map(function (k) {
      var path = "psychology.state_means." + k;
      var value = deepGet(state.spec, path);
      return '<div class="pop-field"><label><span>' + esc(label(k, "zh")) +
        ' <em class="pop-key">' + esc(k) + "</em>" + help(STATE_HELP[k]) +
        '</span><span class="pop-value" data-out="' + path + '">' + value + "</span></label>" +
        '<input type="range" data-path="' + path + '" data-fmt="raw" min="0" max="1" step="0.01" value="' + value +
        '" title="' + esc(STATE_HELP[k] || "") + '" /></div>';
    }).join("");

    var radar = state.population
      ? '<div class="pop-chart" style="max-width:340px"><h4>生成出来的群体状态</h4>' +
        stateRadar(state.population.report.charts.state_distribution, keys) +
        '<p class="pop-chart-note">粗蓝线是平均值。浅蓝色带表示「中间一半人」落在哪个范围——' +
        "带子越宽说明这个群体内部差异越大。悬停查看具体数值。</p></div>"
      : '<p class="pop-hint">先在第 2 步生成人口，这里会显示实际的状态分布。</p>';

    return (
      '<div class="pop-card"><h2>第 3 步 · 这些人的心理状态</h2>' +
      '<p class="pop-lede">九个 0–1 之间的状态量，描述居民的情绪、压力、安全感等。' +
      '这里设的是**整体平均值**；具体到每个人还会根据他的收入、户籍、职业自动调整。</p>' +
      '<div class="pop-grid">' + sliders + "</div>" +
      '<div class="pop-grid" style="margin-top:14px">' +
      fieldSlider("psychology.state_sd", "群体内部差异程度", 0.02, 0.3, 0.01) +
      "</div>" + radar +
      actionBar(
        '<button class="btn" id="popRegen">↻ 用新的状态重新生成</button>' +
        '<button class="btn ghost" data-go="4">下一步：跑群体模拟 →</button>' +
        '<span class="pop-actionhint">改了上面的滑块后，需要重新生成才会生效。</span>'
      ) +
      "</div>"
    );
  }

  /* --------------------------------------------------------------- step 4 */

  function renderStep4() {
    var r = state.run;
    var providers = state.schema.providers || [];
    var providerOptions = ['<option value="">使用配置文件里的默认模型</option>'].concat(
      providers.map(function (p) {
        return '<option value="' + esc(p.name) + '"' + (r.provider === p.name ? " selected" : "") + ">" +
          esc(p.name + "　—　" + p.model + "（" + p.type + (p.is_default ? "，默认" : "") + "）") + "</option>";
      })
    ).join("");

    var warn = r.coupling === 0
      ? '<p class="pop-warn"><b>当前社交影响关闭。</b>同一群体里所有人每天的变化会完全相同，' +
        "社交网络等于没起作用。这一档只适合研究「整体分布怎么变」和「政策影响有多大」，" +
        "不能用来研究观点扩散、极化这类问题（第 5 步的 L2 会不通过）。</p>"
      : "";

    var costHint = r.useLlm
      ? '<p class="pop-warn">已开启真实模型调用，本次运行会产生费用。粗略估计：约 ' +
        Math.round(state.spec.size / 13) * r.days + " 次群体简报调用" +
        (r.budget ? "，另加 " + r.budget * r.days + " 个体-天" : "") + "。</p>"
      : "";

    return (
      '<div class="pop-card"><h2>第 4 步 · 让这座小镇运转起来</h2>' +
      '<p class="pop-lede">把人口按属性分成若干「群体」，每个群体每天只花一次模型调用来写一份群体简报；' +
      '同时每天挑一小批人按完整个体的方式详细模拟。这样几百人的模拟才跑得起。</p>' +
      warn + costHint +
      '<div class="pop-grid">' +
      runSlider("days", "模拟天数", 1, 60, 1, r.days) +
      runSlider("budget", "每天详细模拟几个人", 0, 200, 1, r.budget) +
      runSlider("audit", "误差抽查比例", 0, 0.2, 0.01, r.audit, pct) +
      runSlider("coupling", "社交影响强度", 0, 1.5, 0.05, r.coupling, function (v) { return Number(v).toFixed(2); }) +
      '<div class="pop-field"><label><span>调用真实模型</span>' + help(RUN_HELP.useLlm) + "</label>" +
      '<select data-run="useLlm"><option value="0"' + (r.useLlm ? "" : " selected") + ">否 — 试跑，零成本</option>" +
      '<option value="1"' + (r.useLlm ? " selected" : "") + ">是 — 真实调用，会产生费用</option></select></div>" +
      '<div class="pop-field"><label><span>使用哪个模型</span>' + help(RUN_HELP.provider) + "</label>" +
      '<select data-run="provider"' + (r.useLlm ? "" : " disabled") + ">" + providerOptions + "</select>" +
      '<span class="pop-note">' + (r.useLlm ? "本地 ollama 模型不产生 API 费用。" : "先把上面切到「是」才能选模型。") + "</span></div>" +
      "</div>" +
      actionBar(
        '<button class="btn primary" id="popRunGroup"' + (state.busy ? " disabled" : "") + ">" +
        (state.busy ? "正在模拟…" : "▶ 开始模拟 " + r.days + " 天") + "</button>" +
        (state.groupRun ? '<button class="btn ghost" data-go="5">下一步：检查结果可不可信 →</button>' : "") +
        '<span class="pop-actionhint">' +
        (state.population ? "" : "⚠️ 还没有人口，会先自动生成。") + "</span>"
      ) +
      "</div>" + (state.groupRun ? groupResultCard() : "")
    );
  }

  function runSlider(key, label, min, max, step, value, fmt) {
    return '<div class="pop-field"><label><span>' + esc(label) + help(RUN_HELP[key]) +
      '</span><span class="pop-value">' + esc(fmt ? fmt(value) : value) + "</span></label>" +
      '<input type="range" data-run="' + key + '" min="' + min + '" max="' + max + '" step="' + step +
      '" value="' + value + '" title="' + esc(RUN_HELP[key] || "") + '" /></div>';
  }

  function groupResultCard() {
    var g = state.groupRun;
    var c = g.cost;
    var rows = g.cohorts.slice(0, 40).map(function (co) {
      return "<tr><td>" + esc(co.label) + '</td><td class="num">' + co.size +
        '</td><td class="num">' + (co.centroid.stress || 0).toFixed(2) +
        '</td><td class="num">' + (co.dispersion.stress || 0).toFixed(2) + "</td></tr>";
    }).join("");
    var saving = c.savings_factor
      ? "比逐个模拟省了约 " + c.savings_factor.toFixed(0) + " 倍"
      : "本次没有调用模型，无法比较成本";
    return (
      '<div class="pop-card"><h2>模拟完成</h2>' +
      '<div class="pop-statgrid">' +
      stat(label("population"), c.population, "这次模拟里的总人数") +
      stat(label("cohorts"), c.cohorts, "按属性划分出的群体个数。每个群体每天花一次模型调用") +
      stat(label("group_llm_calls"), c.group_llm_calls, "本次真正发生的调用次数") +
      stat(label("individual_agent_days"), c.individual_agent_days, "被拎出来按完整个体方式模拟的人次") +
      stat(label("savings_factor"), saving, "如果每个人都单独完整模拟，预计需要 " + c.full_individual_llm_calls_estimate + " 次调用") +
      stat(label("max_residual_l1"), g.max_residual_l1.toFixed(4), "抽查样本上，群体预测与个体实际表现的最大偏差。越接近 0 越好；0 表示这次没有可比的变化") +
      "</div>" +
      '<h4 class="pop-subhead">各个群体现在什么样</h4>' +
      '<p class="pop-chart-note">「压力均值」是这个群体的平均压力水平，「内部差异」表示同一群体里人和人相差多少——' +
      "差异不该变成 0，否则群体就退化成了一个平均人。</p>" +
      '<table class="pop-table"><thead><tr><th>群体 Cohort</th><th class="num">人数 Size</th>' +
      '<th class="num">压力均值 stress mean</th><th class="num">内部差异 stress sd</th>' +
      "</tr></thead><tbody>" + rows + "</tbody></table>" +
      '<h4 class="pop-subhead">每天发生了什么</h4>' +
      '<div class="pop-log">' + esc(g.day_blocks.join("\n\n")) + "</div>" +
      "</div>"
    );
  }

  function stat(label, value, tip) {
    return (
      '<div class="pop-stat" title="' + esc(tip) + '">' +
      '<span class="pop-stat-k">' + esc(label) + "</span>" +
      '<span class="pop-stat-v">' + esc(value) + "</span>" +
      "</div>"
    );
  }

  /** Files the user can actually open, not just a path to go hunting for.
   *  The dashboard already serves the repo statically, so a repo-relative URL
   *  is directly clickable. */
  function writtenCard() {
    var files = state.written || [];
    if (!files.length) return "";
    var cards = files.map(function (f) {
      var size = f.bytes > 1024 * 1024
        ? (f.bytes / 1024 / 1024).toFixed(1) + " MB"
        : Math.max(1, Math.round(f.bytes / 1024)) + " KB";
      var open = f.url
        ? '<a class="btn small" href="' + esc(f.url) + '" target="_blank" rel="noopener">在新标签打开 ↗</a>' +
          '<a class="btn small ghost" href="' + esc(f.url) + '" download>下载</a>'
        : '<span class="pop-hint">（文件在仓库之外，无法直接打开）</span>';
      return (
        '<div class="pop-file">' +
        '<div class="pop-file-head"><b>' + esc(f.label) + "</b><span>" + esc(size) + "</span></div>" +
        '<p class="pop-file-hint">' + esc(f.hint) + "</p>" +
        '<code class="pop-file-path">' + esc(f.path) + "</code>" +
        '<div class="pop-file-acts">' + open + "</div>" +
        "<details><summary>预览前几行</summary><pre class=\"pop-pre\">" + esc(f.preview) + "</pre></details>" +
        "</div>"
      );
    }).join("");
    return (
      '<div class="pop-card"><h2>已保存的文件</h2>' +
      '<p class="pop-lede">点「在新标签打开」可以直接在浏览器里查看。' +
      "这三个文件就是仿真器读取的全部内容——把前两个的路径填进 " +
      "<code>CONFIG[\"csv_path\"]</code> 和 <code>CONFIG[\"md_path\"]</code> 就能用它们跑个体模拟。</p>" +
      '<div class="pop-files">' + cards + "</div></div>"
    );
  }

  /* --------------------------------------------------------------- step 5 */

  function renderStep5() {
    var intro =
      '<div class="pop-explain">' +
      "<h4>这一步在做什么？</h4>" +
      "<p>群体模拟是一种<b>近似</b>：它把几十个人打包成一个群体一起处理，从而省下大量成本。" +
      "问题是——这么做会丢掉什么？" +
      "<b>验证门就是来回答这个问题的。</b></p>" +
      "<p>它的做法是做一次<b>对照实验</b>：拿同一批人、同样的起点、同样的随机种子，" +
      "一边用群体方式模拟，一边老老实实一个一个地模拟，然后比较两边的结果差多少。" +
      "差得少的方面，说明群体模拟在这方面是可信的；差得多的方面，说明这类问题不能用群体模拟来研究。</p>" +
      "<p class=\"pop-hint\">运行需要十几秒到一分钟，不消耗模型费用。</p>" +
      "</div>";

    var layerGuide =
      '<div class="pop-explain"><h4>它会检查四件事</h4><ul class="pop-guide">' +
      "<li><b>L1 整体分布</b>：收入、情绪这些指标的<em>分布形状</em>是否一致。" +
      "只比平均值是不够的——把所有人都压成同一个数值，平均值也可以是对的。</li>" +
      "<li><b>L2 邻里影响</b>：关系好的人是否会一起变化。" +
      "这是群体模拟最容易丢掉的东西，因为「同一个群体」和「互为邻居」是两种不同的分组方式。" +
      "<b>研究观点扩散、极化必须看这一项。</b></li>" +
      "<li><b>L3 边缘人群</b>：极端个体（比如快要撑不下去的人）的比例是否被保留。" +
      "聚合类近似的典型毛病就是「中间那批人算得挺准，两头的人被抹平了」。</li>" +
      "<li><b>L4 政策反应</b>：给这批人施加同一个冲击（比如收入下降），两种模拟得出的" +
      "<em>影响方向和大小</em>是否一致，不同人群受影响的差别是否还在。" +
      "<b>做政策研究必须看这一项。</b></li>" +
      "</ul><p class=\"pop-hint\"><b>L2 和 L4 是分水岭</b>：这两项不过，就不能说这次群体模拟是可信的。</p></div>";

    var body = "";
    if (state.verdict) {
      var v = state.verdict.verdict;
      var MARK = {
        pass: { icon: "✅", word: "通过", meaning: "这方面两种模拟结果足够接近，可以放心用" },
        fail: { icon: "❌", word: "未通过", meaning: "这方面差异太大，不要用群体模拟研究这类问题" },
        inconclusive: { icon: "⚠️", word: "测不出来", meaning: "这次实验信号太弱，既不能说好也不能说坏——不算通过" },
      };
      var byLayer = {};
      v.layers.forEach(function (l) { byLayer[l.layer] = l; });

      // 一句话结论 + 能做/不能做清单。用户真正想知道的是「那我现在能拿它干什么」，
      // 而不是四个字母代号各自的 z 值。
      var can = [], cannot = [];
      function verdictOf(id) { return byLayer[id] && byLayer[id].status; }
      (verdictOf("L1") === "pass" ? can : cannot).push("看整体分布怎么变（收入、情绪、压力的分布）");
      (verdictOf("L3") === "pass" ? can : cannot).push("看边缘人群（极端困难者的比例）");
      (verdictOf("L4") === "pass" ? can : cannot).push("做政策实验（某个冲击造成多大影响、谁受影响最大）");
      (verdictOf("L2") === "pass" ? can : cannot).push("研究观点扩散、极化、口碑传播这类靠社交网络传的东西");

      var checklist =
        '<div class="pop-usecase">' +
        '<div class="pop-usecase-col ok"><h5>✅ 这次结果可以用来</h5>' +
        (can.length ? "<ul>" + can.map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("") + "</ul>"
                    : '<p class="pop-hint">（没有通过的项）</p>') + "</div>" +
        '<div class="pop-usecase-col no"><h5>❌ 不要用来</h5>' +
        (cannot.length ? "<ul>" + cannot.map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("") + "</ul>"
                       : '<p class="pop-hint">（四项全通过）</p>') + "</div></div>";

      var headline = v.gate_passed
        ? '<div class="pop-verdict-box pass"><b>✅ 这次群体模拟站得住</b>' +
          "四项关键检查都通过了：群体模拟得到的结果，和老老实实一个一个模拟得到的结果，" +
          "在统计上没有明显区别。你可以放心用它下结论。</div>"
        : '<div class="pop-verdict-box fail"><b>❌ 这次群体模拟还不能全信</b>' +
          "有关键项没通过（见下）。" +
          (verdictOf("L2") !== "pass"
            ? "最常见的原因是<b>社交影响强度设成了 0</b>——回到第 4 步把它调到 0.7 再跑一次。"
            : "具体看下面每一项的说明。") + "</div>";

      var layers = v.layers.map(function (l) {
        var m = MARK[l.status];
        return '<div class="pop-layer ' + l.status + '">' +
          '<div class="pop-layer-head">' + m.icon + " " + esc(label(l.layer, "zh")) +
          ' <em>' + esc(label(l.layer, "en")) + "</em> — " + esc(m.word) + "</div>" +
          '<div class="pop-layer-note">' + esc(LAYER_QUESTION[l.layer] || "") + "</div>" +
          '<div class="pop-layer-note">' + esc(m.meaning) + "</div>" +
          layerDetail(l) + "</div>";
      }).join("");

      body = headline + checklist + '<h4 class="pop-subhead">逐项结果</h4>' +
        '<div class="pop-verdict">' + layers + "</div>" +
        '<details class="pop-details"><summary>展开完整技术输出（写方法学时用）</summary>' +
        '<div class="pop-log">' + esc(state.verdict.text) + "</div></details>";
    }

    return (
      '<div class="pop-card"><h2>第 5 步 · 这次模拟的结果可信吗</h2>' +
      intro + layerGuide + body +
      actionBar(
        '<button class="btn primary" id="popValidate"' + (state.busy ? " disabled" : "") + ">" +
        (state.busy ? "正在检查…" : state.verdict ? "↻ 重新检查" : "🔍 开始检查") + "</button>" +
        '<button class="btn ghost" id="popWrite"' + (state.busy ? " disabled" : "") + ">💾 把这批人保存成文件</button>" +
        '<span class="pop-actionhint">保存后会给出可直接打开的链接。</span>'
      ) +
      "</div>" + writtenCard()
    );
  }

  /** 每一层回答的问题，用一句话说清楚。 */
  var LAYER_QUESTION = {
    L1: "问题：收入、情绪这些指标的分布形状，两种模拟一样吗？",
    L2: "问题：关系好的人会不会一起变化？这是群体模拟最容易丢掉的东西。",
    L3: "问题：处境最极端的那批人，比例有没有被抹平？",
    L4: "问题：给同一个冲击，两种模拟算出的影响方向和大小一致吗？",
  };

  /** 差在哪一边——「传不动」和「传得太猛」是两种完全不同的毛病，
   *  但都只表现为一个 z 值，所以这里从每个指标的实测 Moran's I 反推方向。 */
  function moranDirection(d) {
    var keys = (d.failures && d.failures.length ? d.failures : d.discriminating_keys) || [];
    if (!keys.length || !d.by_key) return "";
    var k = keys[0], e = d.by_key[k];
    if (!e) return "";
    var weaker = Math.abs(e.group_morans_i) < Math.abs(e.reference_morans_i);
    return (
      "以「" + esc(label(k, "zh")) + "」为例：逐个模拟里这个共变强度是 " +
      e.reference_morans_i.toFixed(3) + "，群体模拟是 " + e.group_morans_i.toFixed(3) + "——" +
      (weaker ? "群体模拟里<b>传得太弱</b>，社交网络的作用被削掉了。"
              : "群体模拟里<b>传得过强</b>，邻里影响被放大了。")
    );
  }

  function layerDetail(l) {
    var d = l.detail || {};
    if (l.layer === "L1" && d.gaps) {
      var worst = null;
      Object.keys(d.gaps).forEach(function (k) {
        if (!worst || d.gaps[k].wasserstein1 > d.gaps[worst].wasserstein1) worst = k;
      });
      if (!worst) return "";
      var gap = d.gaps[worst].wasserstein1, allow = d.budget[worst];
      return '<div class="pop-layer-fact">差异最大的是「' + esc(label(worst, "zh")) + "」：" +
        "两种模拟得到的分布，平均相差 " + gap.toFixed(3) + "（这些指标本身在 0–1 之间，" +
        "所以相当于 " + (gap * 100).toFixed(1) + " 个百分点）。允许范围是 " + allow.toFixed(3) +
        " 以内——这个上限不是拍脑袋定的，是先让逐个模拟自己换几个随机种子跑几遍、" +
        "量出它本身的波动有多大，再拿这个波动当尺子。" +
        (gap <= allow ? "差异在噪声范围内。" : "<b>超出了。</b>") + "</div>";
    }
    if (l.layer === "L4" && d.reference_ate !== undefined) {
      var relErr = (d.magnitude_relative_error * 100).toFixed(0);
      return '<div class="pop-layer-fact">' +
        "施加同一个冲击后，逐个模拟测到的影响是 <b>" + d.reference_ate.toFixed(3) + "</b>，" +
        "群体模拟测到的是 <b>" + d.group_ate.toFixed(3) + "</b>——" +
        (d.same_sign ? "方向一致（都是" + (d.reference_ate < 0 ? "下降" : "上升") + "）"
                     : "<b style='color:#dc2626'>方向相反，这会让你得出完全错误的政策结论</b>") +
        "，大小相差 " + relErr + "%。" +
        "不同人群受影响的差异保留了 " + (d.heterogeneity_retained_ratio * 100).toFixed(0) + "%" +
        "（太低说明「谁受影响更大」这个信息被抹平了）。</div>";
    }
    if (l.layer === "L2" && d.worst_z !== undefined) {
      return '<div class="pop-layer-fact">' +
        "衡量的是「关系好的人是否一起变化」。群体模拟与逐个模拟在这一点上相差 <b>" +
        d.worst_z.toFixed(2) + " 个标准差</b>（允许 " + d.tolerance_z.toFixed(1) + " 以内）。" +
        "这个标准差是逐个模拟自己换种子重跑时的天然波动，所以「差 1 个标准差」" +
        "≈「和它自己重跑一遍的差别差不多」。" +
        moranDirection(d) + "</div>";
    }
    if (l.layer === "L3" && d.by_key) {
      var k0 = Object.keys(d.by_key).filter(function (k) { return d.by_key[k] && d.by_key[k].spread_ratio; })[0];
      if (k0) {
        var ratio = d.by_key[k0].spread_ratio;
        return '<div class="pop-layer-fact">以「' + esc(label(k0, "zh")) + "」为例：" +
          "群体模拟保留了逐个模拟 " + (ratio * 100).toFixed(0) + "% 的人群离散程度。" +
          "接近 100% 说明两头的极端人群没有被压扁；明显低于 100% 说明大家被拉向了中间。</div>";
      }
    }
    if (d.failures && d.failures.length) {
      return '<div class="pop-layer-fact">未通过的项：' + esc(d.failures.join("、")) + "</div>";
    }
    return "";
  }

  /* ------------------------------------------------------------- 侧栏 / 壳 */

  function renderIssues() {
    var el = $("popIssues");
    if (!el) return;
    if (!state.preview) {
      el.innerHTML = '<p class="pop-hint">正在检查…</p>';
      return;
    }
    var issues = state.preview.issues || [];
    var html = issues.length
      ? issues.map(function (i) {
          return '<div class="pop-issue ' + esc(i.level) + '"><b>' +
            (i.level === "error" ? "这组参数做不出来" : "可能达不成") + "</b>" + esc(i.message) +
            (i.suggestion ? '<div class="pop-suggest">👉 ' + esc(i.suggestion) + "</div>" : "") + "</div>";
        }).join("")
      : '<div class="pop-issue ok"><b>参数没有冲突</b>可以直接生成。</div>';

    var b = state.preview.bounds;
    html += '<div class="pop-issue info"><b>当前设定下的可行范围</b>' +
      "户均人数只能在 " + b.household_mean_size.min.toFixed(1) + "–" + b.household_mean_size.max.toFixed(1) +
      " 之间；中位年龄只能在 " + b.median_age.min.toFixed(0) + "–" + b.median_age.max.toFixed(0) + " 岁之间。" +
      '<div class="pop-suggest">超出范围是因为这些参数互相牵制，不是 bug。</div></div>';
    el.innerHTML = html;
  }

  function renderSummary() {
    var el = $("popSummary");
    if (!el) return;
    if (!state.population) {
      el.innerHTML = '<p class="pop-hint">还没有生成人口。<br/>在第 2 步点「生成这些人」。</p>';
      return;
    }
    var a = state.population.report.achieved;
    el.innerHTML = "<dl>" +
      "<dt>人数</dt><dd>" + state.population.report.size + "</dd>" +
      "<dt>中位年龄</dt><dd>" + a.median_age.achieved + " 岁</dd>" +
      "<dt>就业率</dt><dd>" + pct(a.employment_rate.achieved) + "</dd>" +
      "<dt>月收入中位数</dt><dd>" + money(a.income_median.achieved) + "</dd>" +
      "<dt>收入差距</dt><dd>" + a.income_gini.achieved.toFixed(2) + "</dd>" +
      "<dt>户均人数</dt><dd>" + a.household_mean_size.achieved.toFixed(1) + "</dd>" +
      "<dt>人均关系数</dt><dd>" + a.mean_degree.achieved.toFixed(0) + "</dd>" +
      "</dl>";
  }

  function render() {
    var renderers = { 1: renderStep1, 2: renderStep2, 3: renderStep3, 4: renderStep4, 5: renderStep5 };
    $("popPanel").innerHTML = (renderers[state.step] || renderStep1)();
    Array.prototype.forEach.call(document.querySelectorAll("#popSteps .step"), function (btn) {
      btn.classList.toggle("is-active", Number(btn.dataset.step) === state.step);
    });
    var prev = $("popPrev"), next = $("popNext");
    if (prev) prev.disabled = state.step === 1;
    if (next) next.disabled = state.step === 5;
    renderIssues();
    renderSummary();
    bindPanel();
  }

  function setProgress(text, fraction, isError) {
    var el = $("popProgress");
    if (!el) return;
    el.innerHTML = text
      ? '<span class="' + (isError ? "pop-progress-err" : "") + '">' + esc(text) + "</span>" +
        (isError ? "" : '<div class="pop-bar"><i style="width:' + Math.round((fraction || 0) * 100) + '%"></i></div>')
      : "";
  }

  /* --------------------------------------------------------------- events */

  var previewTimer = null;
  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(function () {
      api("POST", "/api/population/preview", { spec: state.spec }).then(function (res) {
        if (res.error) {
          var el = $("popIssues");
          if (el) el.innerHTML = '<div class="pop-issue error"><b>预检失败</b>' + esc(res.error) + "</div>";
          return;
        }
        state.preview = res;
        state.spec = res.spec;
        renderIssues();
      });
    }, 180);
  }

  function bindPanel() {
    var panel = $("popPanel");

    Array.prototype.forEach.call(panel.querySelectorAll("[data-path]"), function (input) {
      input.addEventListener("input", function () {
        var path = input.dataset.path;
        var value = input.type === "range" || input.type === "number" ? Number(input.value) : input.value;
        deepSet(state.spec, path, value);
        var out = panel.querySelector('[data-out="' + path + '"]');
        if (out) {
          var f = input.dataset.fmt;
          out.textContent = f === "pct" ? pct(value) : f === "money" ? money(value) : value;
        }
        if (path === "preset") {
          api("POST", "/api/population/preview", { preset: value }).then(function (res) {
            if (res.error) return fail(res.error);
            state.spec = res.spec;
            state.preview = res;
            render();
          });
          return;
        }
        schedulePreview();
      });
    });

    Array.prototype.forEach.call(panel.querySelectorAll("[data-run]"), function (input) {
      input.addEventListener("input", function () {
        var key = input.dataset.run;
        if (key === "useLlm") {
          state.run.useLlm = input.value === "1";
          render();
          return;
        }
        if (key === "provider") {
          state.run.provider = input.value;
          return;
        }
        state.run[key] = Number(input.value);
        var out = input.parentNode.querySelector(".pop-value");
        if (out) {
          out.textContent = key === "audit" ? pct(state.run[key])
            : key === "coupling" ? state.run[key].toFixed(2) : state.run[key];
        }
        if (key === "coupling" || key === "days" || key === "budget") render();
      });
    });

    Array.prototype.forEach.call(panel.querySelectorAll("[data-go]"), function (btn) {
      btn.addEventListener("click", function () {
        state.step = Number(btn.dataset.go);
        render();
      });
    });

    bind("popGenerate", generate);
    bind("popRegen", generate);
    bind("popRunGroup", runGroup);
    bind("popValidate", runValidation);
    bind("popWrite", writePopulation);
  }

  function bind(id, fn) {
    var el = $(id);
    if (el) el.addEventListener("click", fn);
  }

  function poll(jobId, onDone) {
    function tick() {
      api("GET", "/api/population/jobs/" + jobId).then(function (job) {
        if (job.error || !job.status) {
          return fail(job.error || "任务丢失");
        }
        setProgress(job.message, job.progress);
        if (job.status === "running") {
          setTimeout(tick, 600);
          return;
        }
        state.busy = false;
        if (job.status === "error") {
          return fail(job.message);
        }
        setProgress("", 0);
        onDone(job.result);
      });
    }
    tick();
  }

  function generate(after) {
    if (state.busy) return;
    state.busy = true;
    render();
    setProgress("正在生成 " + state.spec.size + " 位居民…", 0.1);
    api("POST", "/api/population/generate", { spec: state.spec }).then(function (res) {
      if (res.error) return fail(res.error);
      poll(res.job_id, function (result) {
        state.population = result;
        state.groupRun = null;
        state.verdict = null;
        render();
        if (typeof after === "function") after();
      });
    });
  }

  function runGroup() {
    if (state.busy) return;
    if (!state.population) {
      // 自动补上缺的一步，而不是让用户对着一个不动的按钮发呆
      generate(runGroup);
      return;
    }
    state.busy = true;
    render();
    setProgress("正在模拟 " + state.run.days + " 天…", 0.1);
    api("POST", "/api/population/group-run", {
      source: "last",
      days: state.run.days,
      materialization_budget: state.run.budget,
      audit_fraction: state.run.audit,
      network_coupling: state.run.coupling,
      use_llm: state.run.useLlm,
      provider: state.run.provider,
      seed: state.run.seed,
    }).then(function (res) {
      if (res.error) return fail(res.error);
      poll(res.job_id, function (result) {
        state.groupRun = result;
        render();
      });
    });
  }

  function runValidation() {
    if (state.busy) return;
    state.busy = true;
    render();
    setProgress("正在做对照实验（跑几遍不同随机种子，需要一点时间）…", 0.1);
    api("POST", "/api/population/validate", {
      days: 14,
      materialization_budget: state.run.budget,
      network_coupling: state.run.coupling,
      seed: state.run.seed,
    }).then(function (res) {
      if (res.error) return fail(res.error);
      poll(res.job_id, function (result) {
        state.verdict = result;
        render();
      });
    });
  }

  function writePopulation() {
    if (state.busy) return;
    state.busy = true;
    render();
    setProgress("正在写出文件…", 0.1);
    api("POST", "/api/population/generate", { spec: state.spec, write: true }).then(function (res) {
      if (res.error) return fail(res.error);
      poll(res.job_id, function (result) {
        state.population = result;
        state.written = result.written || [];
        render();
        setProgress(
          state.written.length ? "✅ 已保存 " + state.written.length + " 个文件，见下方链接" : "完成",
          1
        );
      });
    });
  }

  /* ----------------------------------------------------------------- boot */

  function boot() {
    api("GET", "/api/population/schema").then(function (schema) {
      if (schema.error) {
        $("popPanel").innerHTML = '<div class="pop-card"><h2>无法加载</h2><p class="pop-warn">' +
          esc(schema.error) + "</p><p>请确认 dashboard 后端正在运行。</p></div>";
        return;
      }
      state.schema = schema;
      state.spec = schema.defaults;
      var meta = $("popTopMeta");
      if (meta) {
        meta.innerHTML = "可用模型 " + (schema.providers || []).length + " 个<br/>群体划分维度：" +
          esc((schema.cohort_axes || []).map(function (a) {
            return (schema.cohort_axis_labels || {})[a] || a;
          }).join("、"));
      }
      render();
      schedulePreview();
    });

    bind("popPrev", function () {
      state.step = Math.max(1, state.step - 1);
      render();
    });
    bind("popNext", function () {
      state.step = Math.min(5, state.step + 1);
      render();
    });
    Array.prototype.forEach.call(document.querySelectorAll("#popSteps .step"), function (btn) {
      btn.addEventListener("click", function () {
        state.step = Number(btn.dataset.step);
        render();
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  /* Test hook. The step-5 copy reads a dozen nested fields off the validator's
     output; a renamed field there would blank the card while every Python test
     stays green. This lets a node test push a real verdict payload in. */
  if (typeof global !== "undefined") {
    global.__POP_TEST__ = {
      setVerdict: function (v) { state.verdict = v; },
      setWritten: function (w) { state.written = w; },
      setStep: function (n) { state.step = n; },
      render: render,
      state: state,
    };
  }
})();
