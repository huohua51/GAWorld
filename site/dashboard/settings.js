/* 配置中心 —— 项目里所有配置项的唯一入口。
 *
 * 四个刻意的设计：
 *
 * - **表单是从配置本身长出来的**，和 external.js 同因：这棵树有 500+ 个叶子，手写
 *   表单写不完，也会在加旋钮的当天过期。这里按 JSON 形状渲染控件，后端再按现有配置
 *   的类型把补丁强制成形。
 * - **每一项都必有 hover 说明**。有人写过的说明就用人写的，没有的就退回「路径 · 类型 ·
 *   默认值 · 这个值从哪来」。后者听起来简陋，但它回答的恰恰是最常卡住人的那个问题。
 * - **来源比数值更重要**。改了一项、保存成功、却什么都没变，是这里最贵的一种困惑：
 *   data/environment_config.json 在覆盖链的最后一环，它写了的键，你在别处改都白改。
 *   所以来自它的项会被标红并明说「在这里改不生效」。
 * - **搜索是跨分区的**。一个人想调「通胀」时，他不知道通胀属于哪个分区，也不该知道。
 */
(function () {
  "use strict";

  var META_TABS = [
    { id: "__env", title: "环境变量", help: "密钥和运行时开关。只显示有没有配、配的是哪一个（密钥打码），不在网页里回显或修改 —— 请直接编辑仓库根目录的 .env 文件。" },
    { id: "__files", title: "配置文件", help: "覆盖层的原文：dashboard_config.json 是这个面板写入的地方，environment_config.json 在覆盖链的最后一环。" },
  ];

  var SOURCE_LABEL = {
    "default": "代码默认值",
    dashboard: "dashboard_config.json（本面板写入）",
    env: "环境变量 GAWORLD_CONFIG_OVERRIDES",
    env_file: "data/environment_config.json",
  };

  var SOURCE_SHORT = { dashboard: "已改", env: "环境变量", env_file: "环境文件" };

  var PROVIDER_TYPES = {
    ollama: {
      label: "本地 Ollama",
      endpoint: "http://localhost:11434/api/generate",
      needsKey: false,
      note: "本地 Ollama 服务。地址填到 /api/generate 为止，模型名要和 ollama list 里的完全一致。",
    },
    openai: {
      label: "OpenAI 兼容接口",
      endpoint: "https://api.openai.com/v1",
      needsKey: true,
      note: "任何 OpenAI 兼容的接口都走这一类：官方 OpenAI、vLLM、LM Studio、omlx 等。地址填到 /v1 为止，不含 /chat/completions。",
    },
    anthropic: {
      label: "Anthropic 兼容接口",
      endpoint: "https://api.anthropic.com",
      needsKey: true,
      note: "Anthropic Messages 接口，MiniMax 的 anthropic 端点也走这一类。地址不含 /v1/messages，代码会自己拼。",
    },
  };

  var state = {
    data: null,
    tab: null,
    query: "",
    onlyOverridden: false,
    dirty: {},   // "economy.macro.initial_inflation_rate" -> value
    invalid: {}, // 同 key，JSON 文本框解析不了时为 true
    busy: false,
    probes: {},  // 后端名 -> {busy|ok|error}，测试结果就地更新，不重绘整页
    draft: { type: "ollama", name: "", endpoint: "", model: "", api_key_env: "", timeout: "" },
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

  function has(obj, key) {
    return Object.prototype.hasOwnProperty.call(obj, key);
  }

  function pathKey(prefix, key) {
    return prefix ? prefix + "." + key : String(key);
  }

  /** 按点分路径取值。中途断链返回 undefined，而不是抛错。 */
  function at(root, path) {
    var node = root;
    var parts = String(path).split(".");
    for (var i = 0; i < parts.length; i++) {
      if (node == null || typeof node !== "object") return undefined;
      node = node[parts[i]];
    }
    return node;
  }

  function typeName(value) {
    if (value === null) return "空值 null";
    if (Array.isArray(value)) return "列表 (" + value.length + " 项)";
    if (typeof value === "object") return "分组";
    if (typeof value === "boolean") return "开关";
    if (typeof value === "number") return "数字";
    return "文本";
  }

  function preview(value) {
    if (value === undefined) return "（无默认值）";
    if (value === null) return "null";
    if (typeof value === "string") return value.length > 60 ? value.slice(0, 59) + "…" : value;
    var text;
    try {
      text = JSON.stringify(value);
    } catch (err) {
      return String(value);
    }
    return text.length > 60 ? text.slice(0, 59) + "…" : text;
  }

  function docFor(path) {
    return (state.data && state.data.docs && state.data.docs[path]) || {};
  }

  function labelFor(path) {
    var doc = docFor(path);
    return doc.label || path.split(".").pop();
  }

  function sourceFor(path) {
    return (state.data && state.data.sources && state.data.sources[path]) || "default";
  }

  function defaultFor(path) {
    return at(state.data ? state.data.defaults : null, path);
  }

  /** 闭集取值（目前只有模型路由）。没有就返回 null，走原来的自由文本框。 */
  function choicesFor(path) {
    var map = (state.data && state.data.choices) || {};
    return has(map, path) ? map[path] : null;
  }

  function isReadOnly(path) {
    var list = (state.data && state.data.read_only) || [];
    for (var i = 0; i < list.length; i++) {
      if (path === list[i] || path.indexOf(list[i] + ".") === 0) return true;
    }
    return false;
  }

  /** 每一项都有说明：人写的在前，「路径/类型/默认/来源」永远兜底。 */
  function helpText(path, value) {
    var doc = docFor(path);
    var lines = [];
    if (doc.help) lines.push(doc.help);
    var source = sourceFor(path);
    lines.push("路径：" + path);
    lines.push("类型：" + typeName(value));
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      lines.push("默认：" + preview(defaultFor(path)));
    }
    lines.push("当前来自：" + (SOURCE_LABEL[source] || source));
    if (source === "env_file") {
      lines.push("⚠ 这一项由 data/environment_config.json 最后覆盖，在本面板改它不会生效。");
    } else if (source === "env") {
      lines.push("⚠ 这一项由环境变量 GAWORLD_CONFIG_OVERRIDES 覆盖，优先级高于本面板。");
    }
    if (isReadOnly(path)) {
      lines.push("🔒 只读：模型后端里含有明文密钥，不在网页里编辑。");
    }
    return lines.join("\n");
  }

  function tipFor(path, value) {
    return ' <span class="help-tip" data-help="' + esc(helpText(path, value)) + '"></span>';
  }

  /* -------------------------------------------------------------------- api */

  /** 失败一定看得见，busy 一定清掉：卡住的 busy 看起来就是「按钮没反应」。 */
  function api(method, path, body) {
    state.busy = true;
    syncFooter();
    return fetch(path, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            throw new Error("服务端返回的不是 JSON（HTTP " + res.status + "）");
          })
          .then(function (payload) {
            if (!res.ok) throw new Error(payload.error || "HTTP " + res.status);
            return payload;
          });
      })
      .catch(function (err) {
        status(String(err.message || err), "bad");
        throw err;
      })
      .then(
        function (payload) {
          state.busy = false;
          return payload;
        },
        function (err) {
          state.busy = false;
          syncFooter();
          throw err;
        }
      );
  }

  function status(text, kind) {
    var el = $("setStatus");
    el.className = "set-status" + (kind ? " is-" + kind : "");
    el.textContent = text || "";
  }

  /* ------------------------------------------------------------- 树的渲染 */

  function currentValue(path, fallback) {
    return has(state.dirty, path) ? state.dirty[path] : fallback;
  }

  function fieldClass(path) {
    var source = sourceFor(path);
    return "set-field" +
      (has(state.dirty, path) ? " is-dirty" : "") +
      (state.invalid[path] ? " is-bad" : "") +
      (source !== "default" ? " is-overridden" : "") +
      (source === "env_file" || source === "env" ? " is-shadowed" : "");
  }

  /** 「已改 / 环境文件」小标签 + 单项恢复默认。 */
  function badges(path) {
    var source = sourceFor(path);
    if (source === "default") return "";
    var out = '<span class="set-badge is-' + source + '">' + esc(SOURCE_SHORT[source] || source) + "</span>";
    if (source === "dashboard") {
      out += '<button type="button" class="set-revert" data-revert="' + esc(path) +
        '" title="把这一项从 dashboard_config.json 里删掉，恢复代码默认值">↺</button>';
    }
    return out;
  }

  function labelCell(path, value) {
    return '<span class="set-label">' + esc(labelFor(path)) + tipFor(path, value) +
      '<code class="set-path">' + esc(path.split(".").pop()) + "</code>" + badges(path) + "</span>";
  }

  /** 下拉选项。当前值不在清单里也要列出来并标明 ——
   *  悄悄显示成另一个后端，比显示一个坏值更危险。 */
  function optionsHtml(options, current) {
    var list = options.slice();
    var stale = current && list.indexOf(current) < 0;
    if (stale) list.unshift(current);
    return list.map(function (name) {
      return '<option value="' + esc(name) + '"' + (name === current ? " selected" : "") + ">" +
        esc(name) + (stale && name === current ? "（清单里没有这个后端）" : "") + "</option>";
    }).join("");
  }

  /** 搜索命中判断：标签、路径、说明都算。 */
  function matches(path) {
    if (!state.query) return true;
    var doc = docFor(path);
    var hay = (path + " " + (doc.label || "") + " " + (doc.help || "")).toLowerCase();
    return hay.indexOf(state.query) >= 0;
  }

  function overriddenOk(path) {
    return !state.onlyOverridden || sourceFor(path) !== "default";
  }

  /** 子树里有没有任何一个叶子通过了当前的搜索/筛选。 */
  function subtreeVisible(value, path) {
    if (value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length) {
      if (matches(path) && !state.onlyOverridden) return true;
      var keys = Object.keys(value);
      for (var i = 0; i < keys.length; i++) {
        if (subtreeVisible(value[keys[i]], pathKey(path, keys[i]))) return true;
      }
      return false;
    }
    return matches(path) && overriddenOk(path);
  }

  function renderNode(key, value, path, depth) {
    if (!subtreeVisible(value, path)) return "";

    if (value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length) {
      var body = Object.keys(value).map(function (childKey) {
        return renderNode(childKey, value[childKey], pathKey(path, childKey), depth + 1);
      }).join("");
      var open = depth === 0 || !!state.query || state.onlyOverridden;
      return '<details class="set-group depth-' + depth + '"' + (open ? " open" : "") + ">" +
        "<summary>" + labelCell(path, value) + "</summary>" +
        '<div class="set-group-body">' + body + "</div></details>";
    }

    var locked = isReadOnly(path);
    var attrs = ' data-path="' + esc(path) + '"' + (locked ? " disabled" : "");

    if (typeof value === "boolean") {
      var on = currentValue(path, value);
      return '<label class="' + fieldClass(path) + ' is-inline">' +
        '<input type="checkbox" data-kind="bool"' + attrs + (on ? " checked" : "") + " />" +
        labelCell(path, value) + "</label>";
    }

    if (typeof value === "number") {
      return '<label class="' + fieldClass(path) + '">' + labelCell(path, value) +
        '<input type="number" step="any" data-kind="number"' + attrs +
        ' value="' + esc(currentValue(path, value)) + '" /></label>';
    }

    if (typeof value === "string") {
      var text = String(currentValue(path, value));
      var options = choicesFor(path);
      if (options) {
        return '<label class="' + fieldClass(path) + '">' + labelCell(path, value) +
          '<select data-kind="text"' + attrs + ">" + optionsHtml(options, text) + "</select></label>";
      }
      if (text.length > 80) {
        return '<label class="' + fieldClass(path) + '">' + labelCell(path, value) +
          '<textarea data-kind="text"' + attrs + ">" + esc(text) + "</textarea></label>";
      }
      return '<label class="' + fieldClass(path) + '">' + labelCell(path, value) +
        '<input type="text" data-kind="text"' + attrs + ' value="' + esc(text) + '" /></label>';
    }

    // 列表 / null / 空对象：JSON 文本框。给这些做结构化控件得不偿失，而 JSON 可校验。
    var raw = currentValue(path, value);
    var json = typeof raw === "string" && state.invalid[path] ? raw : JSON.stringify(raw);
    return '<label class="' + fieldClass(path) + '">' + labelCell(path, value) +
      (state.invalid[path] ? '<b class="set-warn">JSON 无法解析</b>' : "") +
      '<textarea data-kind="json"' + attrs + ">" + esc(json) + "</textarea></label>";
  }

  /* ---------------------------------------------------------- 语言模型卡片 */

  /* 这一段是整个面板里唯一一处手写表单，因为「模型」这一项的三件事都是通用树渲染
   * 不可能长出来的：选后端要的是闭集下拉而不是自由文本、加后端要的是一次写进一整
   * 个块、测连通性根本不是配置读写。其余 500 多项仍然走下面的通用渲染。 */

  function providerRows() {
    return (state.data && state.data.providers) || [];
  }

  function probeHtml(probe) {
    if (!probe) return "";
    if (probe.busy) return '<span class="llm-result is-busy">正在调用…</span>';
    if (probe.ok) {
      return '<span class="llm-result is-ok">✓ 通了 · ' + probe.latency_ms + " ms" +
        (probe.sample ? " · 回答：" + esc(probe.sample) : "") + "</span>";
    }
    return '<span class="llm-result is-bad">✗ ' + esc(probe.error || "调用失败") + "</span>";
  }

  function renderPicker() {
    var path = "llm.routing.default";
    var value = String(currentValue(path, at(state.data.tree, path) || ""));
    var options = choicesFor(path) || [];
    var help = "所有没有单独指定的任务都用这个后端，它决定了绝大部分成本。" +
      "选完要点右下角「保存配置」才会写进 dashboard_config.json，并在下一次启动仿真时生效。" +
      "个别任务想用别的后端，去下面的 llm → routing → tasks。";
    return '<div class="llm-card llm-pick">' +
      '<h3>用哪个大模型<span class="help-tip" data-help="' + esc(help) + '"></span></h3>' +
      '<label class="' + fieldClass(path) + '">' +
      '<span class="set-label">默认后端<code class="set-path">' + esc(path) + "</code>" + badges(path) + "</span>" +
      '<select data-kind="text" data-path="' + esc(path) + '">' + optionsHtml(options, value) + "</select></label>" +
      '<p class="set-hint">改动会进入右侧「待保存的修改」，点「保存配置」生效。</p></div>';
  }

  function renderProviderList() {
    var rows = providerRows().map(function (item) {
      var meta = [
        item.type,
        item.model,
        item.endpoint,
        item.timeout ? "超时 " + item.timeout + "s" : "",
      ].filter(Boolean).map(esc).join(" · ");
      var key = "";
      if (item.needs_key) {
        key = item.key_ready
          ? '<span class="llm-key is-ok">密钥已就绪</span>'
          : '<span class="llm-key is-bad">缺密钥：' +
            esc(item.api_key_envs.join("、") || "未指定环境变量") + "</span>";
      }
      return '<div class="llm-row' + (item.is_default ? " is-default" : "") + '">' +
        '<div class="llm-row-head"><b>' + esc(item.name) + "</b>" +
        (item.is_default ? '<span class="set-badge is-dashboard">默认</span>' : "") +
        (item.editable ? '<span class="set-badge is-dashboard">本面板添加</span>' : "") +
        key + "</div>" +
        '<div class="llm-row-meta">' + meta + "</div>" +
        '<div class="llm-row-actions">' +
        '<button type="button" class="button subtle" data-test-provider="' + esc(item.name) + '">测试连通性</button>' +
        (item.editable
          ? '<button type="button" class="button subtle" data-drop-provider="' + esc(item.name) +
            '" title="把它从 dashboard_config.json 里删掉">删除</button>'
          : "") +
        '<span class="llm-slot" data-result="' + esc(item.name) + '">' +
        probeHtml(state.probes[item.name]) + "</span></div></div>";
    }).join("");
    var help = "「测试连通性」会真的向这个后端发一次极短的生成请求 —— 只有真发一次才分得清" +
      "「连得上」和「连得上但模型没拉下来 / 密钥被拒 / 只吐思考不吐正文」。它不改任何配置。";
    return '<div class="llm-card">' +
      "<h3>已配置的后端 <span class=\"set-count\">" + providerRows().length + "</span>" +
      '<span class="help-tip" data-help="' + esc(help) + '"></span></h3>' +
      (rows || '<p class="set-hint">还没有任何后端。</p>') + "</div>";
  }

  function renderAddForm() {
    var draft = state.draft;
    var spec = PROVIDER_TYPES[draft.type] || PROVIDER_TYPES.ollama;
    var types = Object.keys(PROVIDER_TYPES).map(function (id) {
      return '<option value="' + id + '"' + (id === draft.type ? " selected" : "") + ">" +
        esc(PROVIDER_TYPES[id].label) + "（" + id + "）</option>";
    }).join("");
    function field(key, label, placeholder, help) {
      return '<label class="llm-field"><span>' + esc(label) +
        '<span class="help-tip" data-help="' + esc(help) + '"></span></span>' +
        '<input type="text" data-draft="' + key + '" value="' + esc(draft[key]) +
        '" placeholder="' + esc(placeholder) + '" /></label>';
    }
    return '<div class="llm-form">' +
      '<label class="llm-field"><span>类型<span class="help-tip" data-help="' + esc(spec.note) +
      '"></span></span><select data-draft="type">' + types + "</select></label>" +
      field("name", "名称", "例如 my_local_qwen",
        "在配置里引用这个后端时用的名字，也是上面下拉里显示的名字。只能用字母、数字、下划线、短横线。") +
      field("model", "模型名", draft.type === "ollama" ? "qwen3.5:9b" : "gpt-5.4",
        "后端自己认识的模型标识，必须和服务端完全一致。写错了「测试连通性」会直接告诉你。") +
      field("endpoint", "接口地址", spec.endpoint,
        "留空就用默认地址：" + spec.endpoint) +
      (spec.needsKey
        ? field("api_key_env", "密钥环境变量", "MY_PROVIDER_API_KEY",
            "填环境变量的「名字」，不是密钥本身。dashboard_config.json 会进版本库，" +
            "所以这里不接受明文密钥。把值写进仓库根目录的 .env，重启仿真进程后即可生效；" +
            "「环境变量」页签能看到它有没有被读到。")
        : "") +
      field("timeout", "超时（秒）", spec.needsKey ? "120" : "600",
        "单次调用等多久。本地模型慢，通常要 600；云端 120 足够。留空用代码默认值。") +
      '<div class="llm-form-actions">' +
      '<button type="button" class="button subtle" id="llmDraftTest">先测一下</button>' +
      '<button type="button" class="button primary" id="llmDraftSave">添加</button>' +
      '<span class="llm-slot" id="llmDraftResult">' + probeHtml(state.probes.__draft) + "</span></div></div>";
  }

  function renderAddCard() {
    var help = "新后端会写进 dashboard_config.json 的 llm.providers 里，立刻出现在上面的下拉中，" +
      "并在下一次启动仿真时可用。密钥只收环境变量名，不收明文。";
    return '<div class="llm-card">' +
      '<h3>添加本地或云端模型<span class="help-tip" data-help="' + esc(help) + '"></span></h3>' +
      '<div id="llmAddBox">' + renderAddForm() + "</div></div>";
  }

  function renderLlmPanel() {
    return renderPicker() + renderProviderList() + renderAddCard();
  }

  /* ------------------------------------------------------------ 各页签内容 */

  function renderSection(section) {
    var tree = state.data.tree;
    var head = section.id === "llm" ? renderLlmPanel() : "";
    var body = section.keys.map(function (key) {
      return renderNode(key, tree[key], key, 0);
    }).join("");
    if (!body) {
      if (head) return '<p class="set-section-help">' + esc(section.help) + "</p>" + head;
      return '<p class="set-hint">' +
        (state.query ? "这一分区里没有匹配「" + esc(state.query) + "」的配置项。" : "这一分区里没有可显示的配置项。") +
        "</p>";
    }
    return '<p class="set-section-help">' + esc(section.help) + "</p>" + head + body;
  }

  /** 搜索时跨分区平铺，因为想调「通胀」的人不该先知道它属于哪个分区。 */
  function renderSearch() {
    var tree = state.data.tree;
    var blocks = state.data.sections.map(function (section) {
      var body = section.keys.map(function (key) {
        return renderNode(key, tree[key], key, 0);
      }).join("");
      if (!body) return "";
      return '<div class="set-search-group"><h3>' + esc(section.title) + "</h3>" + body + "</div>";
    }).join("");
    if (!blocks) {
      return '<p class="set-hint">没有匹配「' + esc(state.query) + "」的配置项。</p>";
    }
    return blocks;
  }

  function renderEnv() {
    var env = state.data.env;
    var groups = {};
    var order = [];
    env.vars.forEach(function (item) {
      var name = item.group || "其他";
      if (!groups[name]) { groups[name] = []; order.push(name); }
      groups[name].push(item);
    });
    var rows = order.map(function (name) {
      var items = groups[name].map(function (item) {
        var help = [
          item.help || "（.env.example 里没有为它写说明）",
          "变量名：" + item.name,
          item.set ? "状态：已设置" : "状态：未设置",
          item.secret ? "这是一个密钥，只显示打码后的头尾，用来确认「装进去的是哪一把钥匙」。" :
            "非密钥，显示完整值。",
          "要修改请编辑仓库根目录的 .env 文件，然后重启仿真进程。",
        ].join("\n");
        return '<div class="set-env-row' + (item.set ? " is-set" : "") + '">' +
          '<code class="set-env-name">' + esc(item.name) + "</code>" +
          '<span class="help-tip" data-help="' + esc(help) + '"></span>' +
          '<span class="set-env-state">' + (item.set ? "已设置" : "未设置") + "</span>" +
          '<span class="set-env-value">' + (item.value ? esc(item.value) : "—") + "</span>" +
          '<span class="set-env-help">' + esc(item.help || "") + "</span></div>";
      }).join("");
      return '<div class="set-env-group"><h3>' + esc(name) + "</h3>" + items + "</div>";
    }).join("");
    return '<p class="set-section-help">这些变量在进程启动时由 <code>gaworld.env_loader</code> 从 ' +
      '<code>.env</code> 读进来。本面板<strong>只读</strong>：密钥打码显示，改动请直接编辑文件。' +
      "改完要重启仿真进程才生效。</p>" +
      '<p class="set-envfile">.env 文件：<code>' + esc(env.env_file) + "</code> · " +
      (env.env_file_exists ? "存在" : '<b class="set-warn">不存在</b>') + "</p>" + rows;
  }

  function renderFiles() {
    var files = state.data.files;
    function block(id, title, note, info) {
      return '<div class="set-file"><h3>' + esc(title) +
        '<span class="help-tip" data-help="' + esc(note) + '"></span></h3>' +
        '<p class="set-filepath"><code>' + esc(info.path) + "</code> · " +
        (info.exists ? "存在" : "不存在") + "</p>" +
        '<pre class="codebox">' + esc(info.text || "（空）") + "</pre></div>";
    }
    return block(
      "dashboard",
      "dashboard_config.json",
      "本面板保存的就是这个文件。它在代码默认值之上做一次深合并；「恢复默认」等于把对应的键从这里删掉，而不是把默认值写回去 —— 写回去会把它钉死，以后改代码默认值就不生效了。",
      files.dashboard_config
    ) + block(
      "environment",
      "data/environment_config.json",
      "环境生成器的配置。它在覆盖链的最后一环应用，所以它写了的键，在 dashboard_config.json 或环境变量里改都会被它盖掉。只允许 environment / external_environment / external_environment_service / environment_server 四个键。",
      files.environment_config
    );
  }

  /* --------------------------------------------------------------- 侧边栏 */

  function dirtyPaths() {
    return Object.keys(state.dirty);
  }

  function renderSide() {
    var paths = dirtyPaths();
    var overridden = Object.keys(state.data.sources || {});
    var shadowed = overridden.filter(function (p) {
      return state.data.sources[p] === "env_file" || state.data.sources[p] === "env";
    });

    var pending = paths.length
      ? '<ul class="set-pending">' + paths.map(function (path) {
          return "<li" + (state.invalid[path] ? ' class="is-bad"' : "") + ">" +
            '<code>' + esc(path) + "</code>" +
            "<span>" + esc(preview(state.dirty[path])) + "</span>" +
            '<button type="button" class="set-undo" data-undo="' + esc(path) + '" title="撤销这一项的修改">×</button>' +
            "</li>";
        }).join("") + "</ul>"
      : '<p class="set-hint">还没有改动。改过的项会列在这里，确认无误再保存。</p>';

    return '<div class="set-card">' +
      "<h3>待保存的修改 <span class=\"set-count\">" + paths.length + "</span>" +
      '<span class="help-tip" data-help="改动先留在浏览器里，点「保存配置」才会写进 dashboard_config.json。保存只影响下一次启动的仿真，不会打断正在跑的那一轮。"></span></h3>' +
      pending + "</div>" +
      '<div class="set-card">' +
      '<h3>当前覆盖情况<span class="help-tip" data-help="有多少项的实际取值不等于代码里的默认值，以及它们分别来自哪一层。被 environment_config.json 或环境变量盖住的项，在本面板改是不生效的。"></span></h3>' +
      '<p class="set-stat"><b>' + overridden.length + "</b> 项被覆盖，其中 <b>" + shadowed.length +
      "</b> 项来自本面板改不动的层。</p>" +
      '<button type="button" class="button subtle set-wide" id="setShowOverridden">只看被改过的</button>' +
      '<button type="button" class="button danger set-wide" id="setResetAll">清空全部覆盖</button>' +
      '<p class="set-hint">「清空全部覆盖」会把 dashboard_config.json 清空，所有项回到代码默认值。环境变量和 environment_config.json 不受影响。</p>' +
      "</div>";
  }

  /* ---------------------------------------------------------------- 渲染 */

  function tabs() {
    return state.data.sections.concat(META_TABS);
  }

  function renderTabs() {
    var html = tabs().map(function (tab) {
      var count = tab.keys ? countOverridden(tab) : 0;
      return '<button class="step' + (tab.id === state.tab ? " is-active" : "") + '" data-tab="' + esc(tab.id) + '">' +
        esc(tab.title) +
        (count ? '<em class="set-tabcount">' + count + "</em>" : "") +
        '<span class="help-tip" data-help="' + esc(tab.help) + '"></span></button>';
    }).join("");
    $("setTabs").innerHTML = html;
  }

  function countOverridden(tab) {
    var sources = state.data.sources || {};
    var total = 0;
    Object.keys(sources).forEach(function (path) {
      var head = path.split(".")[0];
      if (tab.keys.indexOf(head) >= 0) total += 1;
    });
    return total;
  }

  function render() {
    if (!state.data) return;
    renderTabs();

    var body;
    if (state.query) {
      body = renderSearch();
    } else if (state.tab === "__env") {
      body = renderEnv();
    } else if (state.tab === "__files") {
      body = renderFiles();
    } else {
      var section = null;
      state.data.sections.forEach(function (item) {
        if (item.id === state.tab) section = item;
      });
      body = section ? renderSection(section) : '<p class="set-hint">未知分区。</p>';
    }
    $("setBody").innerHTML = body;
    $("setSide").innerHTML = renderSide();

    var sources = state.data.sources || {};
    $("setTopMeta").innerHTML =
      '<span class="set-chip">配置项 <b>' + countLeaves(state.data.tree) + "</b></span>" +
      '<span class="set-chip">已覆盖 <b>' + Object.keys(sources).length + "</b></span>";

    syncFooter();
    if (window.HelpTips) window.HelpTips.scan($("setBody").parentNode);
  }

  function countLeaves(node) {
    if (node && typeof node === "object" && !Array.isArray(node)) {
      var keys = Object.keys(node);
      if (!keys.length) return 1;
      return keys.reduce(function (sum, key) { return sum + countLeaves(node[key]); }, 0);
    }
    return 1;
  }

  function syncFooter() {
    var count = dirtyPaths().length;
    var bad = Object.keys(state.invalid).length;
    $("setSave").disabled = state.busy || !count || !!bad;
    $("setDiscard").disabled = state.busy || !count;
    $("setSave").textContent = count ? "保存配置（" + count + "）" : "保存配置";
  }

  /* ------------------------------------------------------------- 事件绑定 */

  function readControl(el) {
    var kind = el.getAttribute("data-kind");
    if (kind === "bool") return el.checked;
    if (kind === "number") {
      var num = Number(el.value);
      return isFinite(num) ? num : el.value;
    }
    if (kind === "json") return JSON.parse(el.value);
    return el.value;
  }

  function onFieldChange(event) {
    var el = event.target;
    var path = el.getAttribute && el.getAttribute("data-path");
    if (!path) return;
    var original = at(state.data.tree, path);
    var value;
    try {
      value = readControl(el);
      delete state.invalid[path];
    } catch (err) {
      state.invalid[path] = true;
      state.dirty[path] = el.value;
      el.closest(".set-field").classList.add("is-bad");
      $("setSide").innerHTML = renderSide();
      syncFooter();
      return;
    }
    // 改回原值就不算改动，免得「待保存」里堆一堆什么都没改的项。
    if (JSON.stringify(value) === JSON.stringify(original)) {
      delete state.dirty[path];
    } else {
      state.dirty[path] = value;
    }
    // 默认后端在页面上有两个控件（顶部的选择器和下面的 routing 树），它们绑同一个
    // 路径。不同步的话，面板会同时显示两个互相矛盾的「当前值」。
    var twins = document.querySelectorAll('[data-path="' + path + '"]');
    for (var i = 0; i < twins.length; i++) {
      if (twins[i] === el) continue;
      if (twins[i].type === "checkbox") twins[i].checked = el.checked;
      else twins[i].value = el.value;
      var twinField = twins[i].closest(".set-field");
      if (twinField) twinField.classList.toggle("is-dirty", has(state.dirty, path));
    }
    var field = el.closest(".set-field");
    if (field) {
      field.classList.toggle("is-dirty", has(state.dirty, path));
      field.classList.remove("is-bad");
    }
    $("setSide").innerHTML = renderSide();
    if (window.HelpTips) window.HelpTips.scan($("setSide"));
    syncFooter();
  }

  /** 把扁平的 dirty 路径还原成嵌套补丁。 */
  function buildPatch() {
    var patch = {};
    dirtyPaths().forEach(function (path) {
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

  function absorb(payload) {
    state.data = payload;
    state.dirty = {};
    state.invalid = {};
    render();
  }

  function save() {
    if (Object.keys(state.invalid).length) {
      status("有 JSON 填错了，先改对再保存。", "bad");
      return;
    }
    var count = dirtyPaths().length;
    api("POST", "/api/settings/save", { config: buildPatch() }).then(function (payload) {
      var notes = [];
      if (payload.saved) notes.push("已保存 " + (payload.applied || []).length + " 项");
      else notes.push("没有任何改动被写入");
      if (payload.dropped && payload.dropped.length) notes.push("丢弃 " + payload.dropped.length + " 项（类型不符或不存在）");
      if (payload.blocked && payload.blocked.length) notes.push("拒绝 " + payload.blocked.join("、") + "（只读）");
      // 写进去了、却仍然不是生效值的那些项：被后面的覆盖层盖住了。这正是本面板
      // 想消除的那种「保存成功但什么都没变」，所以要在保存后当场说出来，不能只
      // 指望用户去 hover。
      var shadowed = (payload.applied || []).filter(function (path) {
        var source = (payload.sources || {})[path];
        return source && source !== "dashboard";
      });
      absorb(payload);
      status(notes.join("；") + "。改动在下一次启动仿真时生效。", payload.saved ? "ok" : "warn");
      if (shadowed.length) {
        status("已写入，但这 " + shadowed.length + " 项仍不会生效 —— 它们被更靠后的覆盖层盖住了：" +
          shadowed.join("、") + "。请改对应的 data/environment_config.json 或环境变量。", "warn");
      }
      if (!payload.saved && count) {
        status("提交的 " + count + " 项都没能写入：" + (payload.dropped || []).join("、"), "bad");
      }
    }).catch(function () {});
  }

  function revert(path) {
    api("POST", "/api/settings/reset", { paths: [path] }).then(function (payload) {
      absorb(payload);
      status(payload.removed.length ? "已恢复默认：" + payload.removed.join("、") : "这一项本来就不在覆盖文件里。", "ok");
    }).catch(function () {});
  }

  function resetAll() {
    if (!window.confirm("将清空 dashboard_config.json 里的全部覆盖，所有配置回到代码默认值。\n环境变量和 environment_config.json 不受影响。\n\n继续？")) return;
    api("POST", "/api/settings/reset-all", {}).then(function (payload) {
      absorb(payload);
      status("已清空 " + payload.removed.length + " 项覆盖。", "ok");
    }).catch(function () {});
  }

  /* -------------------------------------------------------- 语言模型的动作 */

  /** 测试结果就地更新：整页重绘会把用户正在填的表单和滚动位置一起清掉。 */
  function paintProbe(key) {
    var slot = key === "__draft" ? $("llmDraftResult") : document.querySelector('[data-result="' + key + '"]');
    if (slot) slot.innerHTML = probeHtml(state.probes[key]);
  }

  function probe(key, payload) {
    var label = key === "__draft" ? "待添加的后端" : "后端「" + key + "」";
    state.probes[key] = { busy: true };
    paintProbe(key);
    api("POST", "/api/settings/llm/test", payload).then(function (result) {
      state.probes[key] = result;
      paintProbe(key);
      status(result.ok ? label + "：连通，用时 " + result.latency_ms + " ms。" : label + "：没连上，看那一行的红字。",
        result.ok ? "ok" : "bad");
    }).catch(function (err) {
      state.probes[key] = { ok: false, error: String((err && err.message) || err) };
      paintProbe(key);
    });
  }

  /** 表单 -> provider 配置块。地址的键名随类型变，所以在这里而不是在后端拍板。 */
  function draftPayload() {
    var draft = state.draft;
    var spec = PROVIDER_TYPES[draft.type] || PROVIDER_TYPES.ollama;
    var config = { type: draft.type, model: draft.model.trim() };
    config[draft.type === "ollama" ? "url" : "base_url"] = draft.endpoint.trim() || spec.endpoint;
    if (spec.needsKey && draft.api_key_env.trim()) config.api_key_env = draft.api_key_env.trim();
    if (draft.timeout.trim()) config.timeout = draft.timeout.trim();
    return { name: draft.name.trim(), config: config };
  }

  function addProvider() {
    var payload = draftPayload();
    api("POST", "/api/settings/llm/provider", payload).then(function (result) {
      state.draft = { type: state.draft.type, name: "", endpoint: "", model: "", api_key_env: "", timeout: "" };
      delete state.probes.__draft;
      absorb(result);
      status("已添加后端「" + result.name + "」。它已经写进 dashboard_config.json，" +
        "可以在上面的下拉里选它，也可以点它那一行的「测试连通性」。", "ok");
    }).catch(function () {});
  }

  function dropProvider(name) {
    if (!window.confirm("将把后端「" + name + "」从 dashboard_config.json 里删掉。\n\n继续？")) return;
    // 复用通用的 reset：删一个覆盖项本来就是「把这个路径从覆盖文件里剪掉」。
    api("POST", "/api/settings/reset", { paths: ["llm.providers." + name] }).then(function (result) {
      delete state.probes[name];
      absorb(result);
      status(result.removed.length ? "已删除后端「" + name + "」。" : "这个后端不在覆盖文件里，删不掉。",
        result.removed.length ? "ok" : "warn");
    }).catch(function () {});
  }

  function load() {
    status("正在读取配置…");
    api("GET", "/api/settings/overview").then(function (payload) {
      if (!state.tab) state.tab = (payload.sections[0] || {}).id || "__env";
      absorb(payload);
      status("");
    }).catch(function () {});
  }

  /* ------------------------------------------------------------------ wire */

  var body = $("setBody");
  body.addEventListener("change", onFieldChange);
  body.addEventListener("input", function (event) {
    // 文本/数字/JSON 边打边记；勾选框由 change 处理，避免重复。
    var kind = event.target.getAttribute && event.target.getAttribute("data-kind");
    if (kind && kind !== "bool") onFieldChange(event);
  });
  // 新增表单的输入只记进 state.draft，不触发重绘 —— 边打字边重绘会把光标弹走。
  body.addEventListener("input", function (event) {
    var key = event.target.getAttribute && event.target.getAttribute("data-draft");
    if (key && key !== "type") state.draft[key] = event.target.value;
  });
  body.addEventListener("change", function (event) {
    if (!event.target.getAttribute) return;
    if (event.target.getAttribute("data-draft") !== "type") return;
    // 换类型要换字段（本地后端没有密钥环境变量）和占位提示，只重画这一张表单。
    state.draft.type = event.target.value;
    var box = $("llmAddBox");
    if (box) {
      box.innerHTML = renderAddForm();
      if (window.HelpTips) window.HelpTips.scan(box);
    }
  });

  body.addEventListener("click", function (event) {
    var test = event.target.closest("[data-test-provider]");
    if (test) {
      probe(test.getAttribute("data-test-provider"), { name: test.getAttribute("data-test-provider") });
      return;
    }
    var drop = event.target.closest("[data-drop-provider]");
    if (drop) {
      dropProvider(drop.getAttribute("data-drop-provider"));
      return;
    }
    if (event.target.id === "llmDraftTest") {
      probe("__draft", draftPayload());
      return;
    }
    if (event.target.id === "llmDraftSave") {
      addProvider();
      return;
    }
    var target = event.target.closest("[data-revert]");
    if (!target) return;
    event.preventDefault();
    revert(target.getAttribute("data-revert"));
  });

  $("setSide").addEventListener("click", function (event) {
    var undo = event.target.closest("[data-undo]");
    if (undo) {
      var path = undo.getAttribute("data-undo");
      delete state.dirty[path];
      delete state.invalid[path];
      render();
      return;
    }
    if (event.target.id === "setResetAll") resetAll();
    if (event.target.id === "setShowOverridden") {
      state.onlyOverridden = true;
      $("setOnlyOverridden").checked = true;
      render();
    }
  });

  $("setTabs").addEventListener("click", function (event) {
    var btn = event.target.closest(".step");
    if (!btn) return;
    state.tab = btn.getAttribute("data-tab");
    render();
  });

  var searchTimer = null;
  $("setSearch").addEventListener("input", function (event) {
    var value = event.target.value.trim().toLowerCase();
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(function () {
      state.query = value;
      render();
    }, 140);
  });

  $("setOnlyOverridden").addEventListener("change", function (event) {
    state.onlyOverridden = event.target.checked;
    render();
  });

  $("setSave").addEventListener("click", save);
  $("setReload").addEventListener("click", load);
  $("setDiscard").addEventListener("click", function () {
    state.dirty = {};
    state.invalid = {};
    render();
    status("已放弃未保存的修改。");
  });

  load();
})();
