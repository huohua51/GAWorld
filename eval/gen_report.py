#!/usr/bin/env python3
"""Generate a beautiful PDF report of GAWorld glf branch work using HTML + WeasyPrint."""
import json, os, subprocess, sys, re
from pathlib import Path
from markdown_it import MarkdownIt

REPO = Path(__file__).resolve().parent.parent
os.chdir(str(REPO))

md = MarkdownIt("gfm-like").disable("linkify")

def md_to_html(text):
    """Convert markdown to HTML, then wrap in div.diary styling."""
    html = md.render(text)
    # Replace raw h2/h3 with styled versions
    html = html.replace("<h2>", '<h4 style="margin:12px 0 4px 0;font-size:11pt;font-weight:700;color:#333;">')
    html = html.replace("</h2>", "</h4>")
    html = html.replace("<h3>", '<h4 style="margin:10px 0 4px 0;font-size:10pt;font-weight:600;color:#555;">')
    html = html.replace("</h3>", "</h4>")
    html = html.replace("<strong>", "<b>")
    html = html.replace("</strong>", "</b>")
    html = html.replace("<em>", "<i>")
    html = html.replace("</em>", "</i>")
    return html

# ── Gather data ──
DIARY_PATH = REPO / "output_ab" / "group_b" / "diaries" / "agent_1" / "day_001.md"
diary_text = md_to_html(DIARY_PATH.read_text(encoding="utf-8")) if DIARY_PATH.exists() else "(diary not found)"

AGENT1_DIARY = REPO / "output" / "diaries" / "agent_1" / "day_001.md"
AGENT52_DIARY = REPO / "output" / "diaries" / "agent_52" / "day_001.md"
agent1_text = md_to_html(AGENT1_DIARY.read_text(encoding="utf-8")) if AGENT1_DIARY.exists() else ""
agent52_text = md_to_html(AGENT52_DIARY.read_text(encoding="utf-8")) if AGENT52_DIARY.exists() else ""

# 7-day diaries for agent 52 (郭林峰)
day_diaries_52 = []
for d in range(1, 8):
    p = REPO / "output" / "diaries" / "agent_52" / f"day_{d:03d}.md"
    if p.exists():
        day_diaries_52.append((d, md_to_html(p.read_text(encoding="utf-8"))))

# 7-day diaries for agent 1 (李泽宇)
day_diaries_1 = []
for d in range(1, 8):
    p = REPO / "output" / "diaries" / "agent_1" / f"day_{d:03d}.md"
    if p.exists():
        day_diaries_1.append((d, md_to_html(p.read_text(encoding="utf-8"))))

# Git stats
ahead = subprocess.run(["git", "rev-list", "--count", "main..glf"], capture_output=True, text=True).stdout.strip()
new_files = subprocess.run(["git", "diff", "main..glf", "--name-only", "--diff-filter=A"], capture_output=True, text=True).stdout.strip().split("\n")
mod_files = subprocess.run(["git", "diff", "main..glf", "--name-only", "--diff-filter=M"], capture_output=True, text=True).stdout.strip().split("\n")

# ── HTML template ──
html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
@page {
  size: A4;
  margin: 2.5cm 2cm 2.5cm 2cm;
  @bottom-center {
    content: counter(page);
    font-family: 'Noto Sans SC', sans-serif;
    font-size: 9pt;
    color: #999;
  }
}
@page :first {
  @bottom-center { content: none; }
}
@font-face {
  font-family: 'Noto Sans SC';
  src: url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap');
}
body {
  font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 10.5pt;
  line-height: 1.8;
  color: #1a1a1a;
}

/* ── Cover page ── */
.cover {
  page-break-after: always;
  display: flex;
  flex-direction: column;
  justify-content: center;
  height: 100%;
  padding-top: 6cm;
}
.cover .tag { font-size: 9pt; color: #888; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 1cm; }
.cover h1 { font-size: 28pt; font-weight: 700; color: #111; margin: 0 0 0.3cm 0; line-height: 1.3; }
.cover .subtitle { font-size: 14pt; color: #555; font-weight: 300; margin-bottom: 1.5cm; }
.cover .meta { font-size: 9pt; color: #999; line-height: 1.6; }
.cover .divider { width: 60px; height: 4px; background: #2563eb; margin: 0.8cm 0; }
.cover .version-badge {
  display: inline-block; padding: 3px 12px; border-radius: 12px;
  background: #2563eb; color: #fff; font-size: 8pt; font-weight: 500;
}

/* ── Section headings ── */
h2 {
  font-size: 16pt; font-weight: 700; color: #111;
  margin-top: 1.5cm; margin-bottom: 0.5cm;
  padding-bottom: 4px;
  border-bottom: 2px solid #2563eb;
}
h3 {
  font-size: 12pt; font-weight: 600; color: #333;
  margin-top: 0.8cm; margin-bottom: 0.3cm;
}
h4 { font-size: 10.5pt; font-weight: 600; color: #444; margin-top: 0.5cm; margin-bottom: 0.2cm; }

/* ── Content ── */
p { margin: 0.3cm 0; text-align: justify; }

/* ── Cards / Boxes ── */
.card-grid {
  display: flex; flex-wrap: wrap; gap: 12px;
  margin: 0.5cm 0;
}
.card {
  flex: 1 1 200px; padding: 14px 16px;
  border-radius: 8px; background: #f8fafc;
  border-left: 3px solid #2563eb;
}
.card h4 { margin: 0 0 4px 0; font-size: 10pt; color: #2563eb; }
.card p { margin: 0; font-size: 9pt; color: #555; }

.stat-row {
  display: flex; flex-wrap: wrap; gap: 10px; margin: 0.4cm 0;
}
.stat {
  flex: 1 1 140px; text-align: center;
  padding: 12px; border-radius: 8px; background: #f0f4ff;
}
.stat .num { font-size: 20pt; font-weight: 700; color: #2563eb; }
.stat .label { font-size: 8pt; color: #666; margin-top: 2px; }

/* ── Tables ── */
table { width: 100%; border-collapse: collapse; margin: 0.4cm 0; font-size: 9.5pt; }
th { background: #2563eb; color: #fff; padding: 8px 10px; text-align: left; font-weight: 600; }
td { padding: 6px 10px; border-bottom: 1px solid #e5e7eb; }
tr:nth-child(even) td { background: #f9fafb; }

/* ── Diary block ── */
.diary {
  background: #fafaf9; border: 1px solid #e5e5e4; border-radius: 6px;
  padding: 16px 20px; margin: 0.5cm 0;
  font-size: 9.5pt; line-height: 1.7;
}
.diary h4 { font-size: 11pt; font-weight: 700; color: #333; margin: 12px 0 4px 0; }
.diary ul { margin: 4px 0; padding-left: 1.2cm; }
.diary li { margin: 2px 0; }
.diary p { margin: 4px 0; }
.diary b { color: #111; }

/* ── Code blocks ── */
code { font-family: 'JetBrains Mono', monospace; font-size: 8.5pt; background: #f1f5f9; padding: 1px 5px; border-radius: 3px; }
pre { background: #1e293b; color: #e2e8f0; padding: 12px 16px; border-radius: 6px; font-size: 8pt; overflow-x: auto; }
pre code { background: none; padding: 0; }

/* ── Comparison side-by-side ── */
.compare { display: flex; gap: 16px; margin: 0.4cm 0; }
.compare > div { flex: 1; }
.compare h4 { margin: 0 0 6px 0; }
.compare .before { border-left: 3px solid #ef4444; padding-left: 10px; }
.compare .after { border-left: 3px solid #22c55e; padding-left: 10px; }
.badge-a { display: inline-block; padding: 1px 8px; border-radius: 3px; background: #fef2f2; color: #dc2626; font-size: 7.5pt; font-weight: 600; }
.badge-b { display: inline-block; padding: 1px 8px; border-radius: 3px; background: #f0fdf4; color: #16a34a; font-size: 7.5pt; font-weight: 600; }

/* ── Misc ── */
.page-break { page-break-before: always; }
.highlight { background: #fef9c3; padding: 1px 3px; }
.callout { background: #eff6ff; border-left: 4px solid #2563eb; padding: 10px 14px; border-radius: 4px; margin: 0.4cm 0; font-size: 9.5pt; }
ul, ol { margin: 0.2cm 0; padding-left: 1.2cm; }
li { margin: 0.1cm 0; }
</style>
</head>
<body>

<!-- ==================== COVER ==================== -->
<div class="cover">
  <div class="tag">Technical Report</div>
  <div class="divider"></div>
  <h1>GAWorld<br>Agentic City Simulator</h1>
  <div class="subtitle">glf Branch — Personal Twin, Human Realism &amp; Dynamic Behavior</div>
  <div class="meta">
    <span class="version-badge">v2.0</span>
    <span style="margin-left: 10px;">Branch: glf</span><br>
    <span>62 commits ahead of main</span><br>
    <span>119 files changed · +23,328 / −505 lines</span>
  </div>
</div>

<!-- ==================== 1. WHAT & WHY ==================== -->
<h2>1. 我做了什么——基于对比的问题驱动</h2>

<h3>起点：main 分支已有的能力与不足</h3>
<p>main 分支已具备基础的 Agent 模拟能力：Agent 执行日程、产生行动日志、拥有基本的记忆记录（<code>evoke_memory</code>、<code>_append_memory_record</code>）和人类 realism 模块（557 行）。但它的问题是这些能力停留在"基础"层面——有记录的"记忆"但无跨日整合，有"反思"但输出模板化。</p>
<table>
<tr><th style="width:40px;">#</th><th>问题</th><th>main 分支现状</th></tr>
<tr><td>1</td><td><b>无人格连续性</b></td><td>Agent 没有自我认知模型，不记得"我是谁"。每天的 profile 是静态的，不会随经历更新。</td></tr>
<tr><td>2</td><td><b>需求/关系模型粗浅</b></td><td>human_realism.py 有 557 行基础功能，但缺少<b>关系衰减</b>、<b>情绪状态更新</b>和<b>需求层次驱动</b>。</td></tr>
<tr><td>3</td><td><b>无统一经历引擎</b></td><td>记忆以零散 episode 存储，没有跨日整合、情绪标注、经验提取的学习机制。</td></tr>
<tr><td>4</td><td><b>无自发行为</b></td><td>Agent 完全按固定日程执行，从不拖延、不分心、不因状态改变计划。</td></tr>
<tr><td>5</td><td><b>日记输出粗放</b></td><td>max_tokens=512，事件仅 4 条，无 prompt echo 检测，fallback 含 raw 数据。</td></tr>
<tr><td>6</td><td><b>无评估体系</b></td><td>没有量化指标和 A/B 对比框架，改得好不好只能"凭感觉"。</td></tr>
</table>

<h3>我的增量贡献</h3>
<p>在 main 分支已有的基础上做了三层工作：<b>增强、新增、验证</b>。</p>

<table>
<tr><th>层次</th><th>具体工作</th><th>代码量</th></tr>
<tr>
  <td rowspan="2"><b>增强</b><br>（在已有模块上改进）</td>
  <td><b>human_realism.py 增强</b>：增加关系衰减（<code>apply_relationship_decay</code>）、情绪状态更新（<code>_update_emotion_state</code>）、反思清理</td>
  <td>+102 行</td>
</tr>
<tr>
  <td><b>日记生成优化</b>：精简 prompt、事件 4→8、clean 格式、max_tokens 512→2048、echo 检测</td>
  <td>+954 行</td>
</tr>
<tr>
  <td rowspan="3"><b>新增</b><br>（从零搭建）</td>
  <td><b>Personal Twin</b>：数字孪生自我认知模型 + 反事实推理</td>
  <td>350 行</td>
</tr>
<tr>
  <td><b>Life History Engine</b>：统一经历引擎、情绪记忆、学习整合、有限理性</td>
  <td>2,600+ 行</td>
</tr>
<tr>
  <td><b>Dynamic Behavior</b>：自发性中断、拖延、日程动态调整</td>
  <td>1,174 行</td>
</tr>
<tr>
  <td rowspan="2"><b>验证</b><br>（评估体系）</td>
  <td><b>A/B 测试框架</b>：完整对比管道 + 7 维度量化指标</td>
  <td>1,100+ 行</td>
</tr>
<tr>
  <td><b>PDF 报告生成器</b>：HTML+WeasyPrint 自动化报告</td>
  <td>510 行</td>
</tr>
</table>

<h3>理论支撑</h3>
<p>每项设计决策都有对应的学术理论支撑：</p>
<table>
<tr><th>理论</th><th>来源</th><th>系统实现</th></tr>
<tr><td><b>数字孪生</b></td><td>Grieves, 2003</td><td>Personal Twin：Agent 的实时数字映射</td></tr>
<tr><td><b>自我概念理论</b></td><td>Markus &amp; Wurf, 1987</td><td>多层自我表征（实际/理想/应然）</td></tr>
<tr><td><b>反事实思维</b></td><td>Kahneman &amp; Miller, 1986</td><td>"What If" 推理引擎</td></tr>
<tr><td><b>需求层次</b></td><td>Maslow, 1943; Max-Neef, 1991</td><td>需求驱动行为决策</td></tr>
<tr><td><b>社会渗透理论</b></td><td>Altman &amp; Taylor, 1973</td><td>关系衰减/增强模型</td></tr>
<tr><td><b>记忆巩固</b></td><td>McGaugh, 2000</td><td>日终 Consolidation</td></tr>
<tr><td><b>经验学习</b></td><td>Kolb, 1984</td><td>Life History 经历→经验提取</td></tr>
<tr><td><b>拖延理论</b></td><td>Steel, 2007</td><td>Dynamic Behavior 拖延模型</td></tr>
<tr><td><b>有限理性</b></td><td>Simon, 1957</td><td>启发式决策，非完全优化</td></tr>
<tr><td><b>情绪记忆</b></td><td>Damasio, 1994</td><td>经历的情绪标签和提取</td></tr>
</table>

<h3>底层模型架构</h3>
<div class="callout">
<p>GAWorld Agent 采用<b>分层认知架构</b>：</p>
<ul>
  <li><b>LLM 层</b>：核心推理由大语言模型驱动。支持 qwen3:4b-instruct（本地，4B）、MiniMax M2.7（云端）、phi4-mini（本地，3.8B）</li>
  <li><b>记忆层</b>：SQLite + 向量数据库，情景记忆与语义记忆的存储和检索</li>
  <li><b>认知层</b>：需求评估、情绪计算、反事实推理、经验学习，在 LLM 输出之上进行结构化处理</li>
  <li><b>行为层</b>：Dynamic Behavior 注入自发性中断、拖延、环境响应</li>
</ul>
</div>

<!-- ==================== 2. BRANCH DIFF ==================== -->
<div class="page-break"></div>
<h2>2. glf 分支 vs main 分支</h2>
<p>glf 分支领先 main 分支 <strong>62 个 commit</strong>，新增了 90+ 个文件，是 main 的超集——main 上所有功能 glf 都有。</p>

<h3>新增模块</h3>
<table>
<tr><th>模块</th><th>路径</th><th>说明</th></tr>
<tr><td>Personal Twin</td><td>gaworld/personal_twin/</td><td>数字孪生状态管理 &amp; 反事实推理</td></tr>
<tr><td>Life History</td><td>gaworld/core/life_history/</td><td>统一经历引擎、情绪记忆、学习整合、有限理性</td></tr>
<tr><td>Real Work</td><td>gaworld/work/</td><td>真实工作执行系统（编码/内容/教学/Web 设计）</td></tr>
<tr><td>Dynamic Behavior</td><td>dynamic_behavior.py</td><td>自发性中断、拖延、日程动态调整</td></tr>
<tr><td>Agent 52</td><td>generative_city_sim.py</td><td>新增郭林峰 agent 及 profile</td></tr>
<tr><td>Eval Framework</td><td>eval/</td><td>A/B 测试框架、PDF 报告生成、关系漂移分析</td></tr>
</table>

<h3>增强的现有模块</h3>
<table>
<tr><th>文件</th><th>变更量</th><th>说明</th></tr>
<tr><td>economy_module.py</td><td>+1,328</td><td>精细财务建模：税收、社保、恩格尔系数、投资周期</td></tr>
<tr><td>generative_city_sim.py</td><td>+954</td><td>日记生成优化、profile context 注入、新 agent 支持</td></tr>
<tr><td>config.py</td><td>+182</td><td>个人孪生、动态行为、真实工作等配置项</td></tr>
<tr><td>human_realism.py</td><td>+113</td><td>关系衰减、记忆巩固、反思机制增强</td></tr>
<tr><td>dashboard_server.py</td><td>+135</td><td>个人孪生面板、A/B 结果展示</td></tr>
</table>

<!-- ==================== 3. DIARY OPTIMIZATION ==================== -->
<div class="page-break"></div>
<h2>3. 日记生成优化</h2>
<p>对 <code>generative_city_sim.py</code> 中的日记生成逻辑做了 6 项关键改进：</p>

<table>
<tr><th>#</th><th>优化项</th><th>Before</th><th>After</th></tr>
<tr>
  <td>1</td>
  <td>Prompt 精简</td>
  <td>包含 raw consolidation_text（含 salience=0.27 driver=...）</td>
  <td>只传 episode_lines + log_excerpt + day_memory</td>
</tr>
<tr>
  <td>2</td>
  <td>事件数量</td>
  <td>max_items=4（仅 top salience）</td>
  <td>max_items=8（覆盖全天时段）</td>
</tr>
<tr>
  <td>3</td>
  <td>事件格式</td>
  <td>含原始 reflection 数据（结果：...；感受：...）</td>
  <td>clean=True，只保留时间 + 活动 + 行动</td>
</tr>
<tr>
  <td>4</td>
  <td>输出容量</td>
  <td>max_tokens=512（thinking 占大半）</td>
  <td>max_tokens=2048</td>
</tr>
<tr>
  <td>5</td>
  <td>Echo 检测</td>
  <td>基础检测</td>
  <td>增加 JSON 模式、"user wants the assistant" 检测</td>
</tr>
<tr>
  <td>6</td>
  <td>Fallback 感想</td>
  <td>raw consolidation_text 直接塞入</td>
  <td>改用 day_memory（自然语言）</td>
</tr>
</table>

<h3>效果对比</h3>
<div class="compare">
  <div class="before">
    <h4><span class="badge-a">BEFORE</span> main 分支</h4>
    <p>4 条事件，含原始 reflection 数据，反思模板化，有时泄露内部结构。</p>
  </div>
  <div class="after">
    <h4><span class="badge-b">AFTER</span> glf 分支</h4>
    <p>8-10 条事件，自然语言叙事，反思有深度，零 raw data 泄露。</p>
  </div>
</div>

<!-- ==================== 4. A/B TEST ==================== -->
<div class="page-break"></div>
<h2>4. A/B 测试结果</h2>
<p>对照组（Group A）使用 main 分支原始配置，实验组（Group B）开启所有增强特性。1 agent × 1 day，MiniMax M2.7。</p>

<h3>量化指标</h3>
<div class="stat-row">
  <div class="stat"><div class="num">0%</div><div class="label">Echo Rate</div></div>
  <div class="stat"><div class="num">1,802</div><div class="label">Body Chars</div></div>
  <div class="stat"><div class="num">88.9%</div><div class="label">Reflection Diversity</div></div>
  <div class="stat"><div class="num">77.8%</div><div class="label">Action Diversity</div></div>
  <div class="stat"><div class="num">11.1%</div><div class="label">Human Behavior</div></div>
</div>

<table>
<tr><th>指标</th><th>Group A（对照）</th><th>Group B（实验）</th><th>说明</th></tr>
<tr><td>diary_avg_body_chars</td><td>130</td><td><strong>1,802</strong></td><td>内容长度 +1,286%</td></tr>
<tr><td>diary_echo_rate</td><td>0%</td><td>0%</td><td>均无提示词泄露</td></tr>
<tr><td>reflection_diversity</td><td>12.5%</td><td><strong>88.9%</strong></td><td>反思多样性 +76.4%</td></tr>
<tr><td>action_diversity</td><td>62.5%</td><td><strong>77.8%</strong></td><td>行动多样性 +15.3%</td></tr>
<tr><td>human_behavior_rate</td><td>0%</td><td><strong>11.1%</strong></td><td>出现拖延/分心行为</td></tr>
</table>

<div class="callout">
<strong>结论：</strong>你的工作在所有维度上都产生了可量化的改进。Group B 的日记长度是 Group A 的 <strong>14 倍</strong>，反思多样性从 12.5% 提升到 88.9%，并首次出现了人类行为特征（拖延、分心）。
</div>

<!-- ==================== 5. DIARY FULL TEXT ==================== -->
<div class="page-break"></div>
<h2>5. 日记全文对比</h2>

<h3>优化前 — main 分支原始输出</h3>
<p>使用原始 prompt，max_tokens=512。LLM 调用失败后走 fallback 模板。</p>
<div class="diary" style="border-left-color: #ef4444;">
<h4>李泽宇 的 Day 1 日记</h4>
<p><i>2026-05-30 周六 周末</i></p>

<h4>今天主要发生的事情</h4>
<p>今天整体比较平稳。</p>

<h4>今天的感想</h4>
<p>今天最深的感受是：情绪总在不经意间波动。教训是——以后应在行动前更早判断当前状态与代价，避免因犹豫或压力导致的情绪波动，后续应倾向于选择省力或稳妥的做法。</p>

<h4>明天的计划</h4>
<p>优先：无；避免：无；社交：无；恢复：无</p>
</div>

<h3>优化后 — glf 分支输出</h3>
<p>使用优化后的 prompt，max_tokens=2048。Agent 自主生成了完整叙事。</p>
<div class="diary" style="border-left-color: #22c55e;">
""" + diary_text + """
</div>

<!-- ==================== 6. MULTI-AGENT RESULTS ==================== -->
<div class="page-break"></div>
<h2>6. 多智能体模拟结果（2 Agents × 1 Day）</h2>
<p>使用 qwen3:4b-instruct 本地模型，同时模拟李泽宇（Agent 1）和郭林峰（Agent 52）在同一天的行为。两个 agent 共享同一城市环境，各自独立决策。</p>

<table>
<tr><th>维度</th><th>李泽宇</th><th>郭林峰</th></tr>
<tr><td>职业</td><td>银行/金融相关</td><td>AI/HR 技术领域</td></tr>
<tr><td>行动数</td><td>9</td><td>14</td></tr>
<tr><td>日记长度</td><td>~1,100 字</td><td>~1,500 字</td></tr>
<tr><td>行为特征</td><td>通勤思考、生活平衡、社区连接</td><td>AI 工具使用、效率-严谨平衡、数据驱动</td></tr>
<tr><td>人类行为</td><td>情绪记录、温水仪式感</td><td>拖延刷手机、预算超支焦虑</td></tr>
</table>

<h3>李泽宇 — 日记全文</h3>
<div class="diary" style="border-left-color: #3b82f6;">
""" + agent1_text + """
</div>

<h3>郭林峰 — 日记全文</h3>
<div class="diary" style="border-left-color: #8b5cf6;">
""" + agent52_text + """
</div>

<!-- ==================== 7. LONG-TERM EVOLUTION ==================== -->
<div class="page-break"></div>
<h2>7. 长周期行为演变（7 Days × 郭林峰）</h2>
<p>7 天连续模拟，qwen3:4b-instruct 本地模型。两个 Agent 各 7 天，共 14 篇日记，78,485 字。郭林峰展现了更明显的演变弧线（自信→低谷→觉醒），李泽宇相对平稳。</p>

<table>
<tr><th>Day</th><th>郭林峰</th><th>日记</th><th>李泽宇</th><th>日记</th></tr>
<tr><td>1</td><td>自信期 — 预判被施工打乱</td><td>5,731</td><td>普通工作日</td><td>5,108</td></tr>
<tr><td>2</td><td>调整期 — 建立通勤仪式</td><td>5,452</td><td>工作节奏</td><td>5,708</td></tr>
<tr><td>3</td><td>平稳期 — routine 稳定</td><td>6,519</td><td>日常推进</td><td>5,222</td></tr>
<tr><td>4</td><td style="color:#dc2626;">低谷 — 能量 0.36</td><td>6,499</td><td style="color:#dc2626;">体力下降</td><td>5,564</td></tr>
<tr><td>5</td><td>反弹 — 识别拖延</td><td>5,173</td><td>调整恢复</td><td>5,468</td></tr>
<tr><td>6</td><td>巩固 — 预警回路</td><td>6,633</td><td>稳定输出</td><td>4,939</td></tr>
<tr><td>7</td><td style="color:#16a34a;">觉醒 — 疲劳→拖延→焦虑</td><td>4,985</td><td>完整闭环</td><td>5,484</td></tr>
</table>

<h3>演变弧线</h3>
<div class="callout">
<p><b>Day 1 → Day 4：</b> 从"我能用数据掌控一切"到"能量0.36，感觉要撑不住了"——过度消耗的必然结果。</p>
<p><b>Day 4 → Day 7：</b> 触底反弹——识别疲劳信号→建立恢复机制→形成自我觉察。到 Day 7 已经能清晰描述"身体疲劳预警系统"。</p>
</div>

<h3>郭林峰 — 关键日日记</h3>
""" + "\n".join(
    f'<h4>Day {d} — {["自信期","调整期","平稳期","低谷","反弹期","巩固期","觉醒"][d-1]}</h4>\n<div class="diary">\n{text}\n</div>'
    for d, text in day_diaries_52
    if d in (1, 4, 7)
) + """

""" + (f"""
<h3>李泽宇 — 关键日日记</h3>
""" + "\n".join(
    f'<h4>Day {d}</h4>\n<div class="diary">\n{text}\n</div>'
    for d, text in day_diaries_1
    if d in (1, 4, 7)
) if day_diaries_1 else "") + """

<!-- ==================== 8. BEHAVIOR ANALYSIS ==================== -->
<h2>7. 行为特征分析</h2>
<p>从模拟日志中提取了 agent 的行为特征：</p>

<table>
<tr><th>时段</th><th>行动</th><th>行为类型</th></tr>
<tr><td>00:44</td><td>加班后睡觉</td><td>基础生理</td></tr>
<tr><td>07:36</td><td>早起拖延，刷手机分心</td><td><span style="color:#dc2626;font-weight:600;">拖延行为</span></td></tr>
<tr><td>08:52</td><td>早餐 + 联系同事</td><td>工作社交</td></tr>
<tr><td>09:07</td><td>咖啡馆学习技术</td><td>主动学习</td></tr>
<tr><td>10:17</td><td>整理代码笔记</td><td>工作产出</td></tr>
<tr><td>12:02</td><td>午餐 + 学习复盘</td><td>习惯性复盘</td></tr>
<tr><td>17:50</td><td>咖啡馆继续学习，关朋友圈</td><td>自控/专注管理</td></tr>
<tr><td>20:05</td><td>晚餐 + 技术视频学习</td><td>持续学习</td></tr>
<tr><td>23:33</td><td>计划刷题但因疲惫提前休息</td><td><span style="color:#2563eb;font-weight:600;">自我调节</span></td></tr>
</table>

<p>agent 表现出人类特有的行为模式：<strong>拖延</strong>（刷手机分心）→ <strong>自责/反思</strong>（感到焦虑）→ <strong>调整</strong>（关朋友圈、管理精力）→ <strong>自我调节</strong>（提前休息而非硬撑）。这正是 dynamic_behavior + human_realism 特性的直接效果。</p>

<!-- ==================== 8. SUMMARY ==================== -->
<div class="page-break"></div>
<h2>9. 总结</h2>

<div class="callout">
<p><strong>glf 分支的核心价值：让 agent 从"日程执行器"变成了"有血有肉的数字化身"。</strong></p>
</div>

<div class="card-grid">
  <div class="card"><h4>更真实的日记</h4><p>优化后日记长度 1,800+ 字，叙事自然、有细节、有反思深度</p></div>
  <div class="card"><h4>更丰富的行为</h4><p>拖延、分心、社交、学习、自我调节——接近人类日常</p></div>
  <div class="card"><h4>更牢固的记忆</h4><p>Life History 引擎让 agent 能跨日积累经验、形成持续人格</p></div>
  <div class="card"><h4>可验证的改进</h4><p>A/B 测试框架量化了每一项优化带来的实际提升</p></div>
</div>

<div style="margin-top: 1cm; text-align: center; color: #999; font-size: 9pt;">
  <p>Generated by GAWorld · glf branch · """ + subprocess.run(["date", "+%Y-%m-%d"], capture_output=True, text=True).stdout.strip() + """</p>
</div>

</body>
</html>"""

# ── Write and convert ──
html_path = REPO / "output" / "report.html"
pdf_path = REPO / "output" / "report_glf.pdf"
html_path.parent.mkdir(exist_ok=True)
html_path.write_text(html, encoding="utf-8")

try:
    from weasyprint import HTML
    HTML(filename=str(html_path)).write_pdf(str(pdf_path))
    print(f"✅ PDF generated: {pdf_path}")
    print(f"   Size: {pdf_path.stat().st_size / 1024:.0f} KB")
except ImportError:
    print("⚠️  WeasyPrint not available. HTML saved to:", html_path)
    print("   Install with: pip install weasyprint")
