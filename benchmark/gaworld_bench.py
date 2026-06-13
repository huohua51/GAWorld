#!/usr/bin/env python3
"""
GAWorld-Bench harness (v0.1)

Implements the scoring + aggregation core for GAWorld-Bench.
See ../GAWORLD_BENCH_DESIGN.md for the full design.

Implemented in v0.1:
  - Track A  (macro empirical fit, real anchors, schema-correct extractors)
  - Track C  (causal validity: known-sign + placebo + determinism)
  - Scorecard aggregation with a trust gate
  - Auto-report: every run writes results/report.md (+ timestamped archive) with
    per-track diagnosis and data-driven improvement suggestions.
  - --synthetic mode: fabricates structurally-correct fixtures so the whole
    pipeline runs without an LLM / simulation (used for verification + trial).

Track B / D / E are stubbed (return n/a) and left for v0.2+.

Usage (run from the repo-root benchmark/ folder):
    python gaworld_bench.py --synthetic
    python gaworld_bench.py --all                      # default: score real output/
    python gaworld_bench.py --track A --output-dir ../output
    # Track C, live (runs compare-event; needs an LLM provider):
    python gaworld_bench.py --track C --run --days 3 --seed 42 [--llm-provider minimax]
    # Track C, from already-produced comparison dirs:
    python gaworld_bench.py --track C --comparisons-root ../output/comparisons \\
        --placebo-dir <dir> --det-a <state.csv> --det-b <state.csv>
    python gaworld_bench.py --all --run --days 3 --seed 42
"""

import argparse
import csv
import json
import math
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # benchmark/ -> repo root
RESULTS_DIR = PROJECT_ROOT / "benchmark" / "results"
SIMULATOR = PROJECT_ROOT / "generative_city_sim.py"
COMPARISONS_OUT = PROJECT_ROOT / "output" / "comparisons"

# ── Track A: real-world anchors (城镇口径). See design doc §2 / §6. ───────────
ANCHORS = {
    "engel_coefficient": {"value": 0.288, "tol": 0.15,
                          "source": "国家统计局2024公报 (城镇28.8%)"},
    "savings_rate":      {"value": 0.35, "tol": 0.30,
                          "source": "2024 口径敏感, 区间30-43%"},
    "commute_minutes":   {"value": 34.5, "tol": 0.25,
                          "source": "2024中国主要城市通勤监测报告 (杭州)"},
    "transit_share":     {"value": 0.476, "tol": 0.25,
                          "source": "杭州市交通运输局2024"},
}

# ── Track C: known-sign interventions (metrics present in comparison_metrics.csv) ─
# Each maps an intervention dir name -> (state metric, expected delta sign).
SIGN_TESTS = [
    {"name": "traffic_restriction", "metric": "mobility_intent",   "sign": +1,
     "why": "限行→出行摩擦上升→流动意愿上升"},
    {"name": "layoff_shock",        "metric": "econ_security",     "sign": -1,
     "why": "裁员→收入骤降→经济安全感下降"},
    {"name": "layoff_shock",        "metric": "stress",            "sign": +1,
     "why": "裁员→压力上升"},
    {"name": "tax_cut",             "metric": "econ_security",     "sign": +1,
     "why": "减税→可支配收入上升→经济安全感上升"},
]
PLACEBO_EPS = 0.05      # |delta_mean| below this counts as "no effect"
DET_TOL = 1e-9          # float tolerance for determinism check

# Live-run config: maps each sign-test key -> (event-name, event-description)
# passed to `generative_city_sim.py compare-event`.
INTERVENTIONS = {
    "traffic_restriction": ("临时交通限行", "主干道限行导致通勤时间上升并影响出行决策"),
    "layoff_shock":        ("大规模裁员冲击", "部分企业裁员导致相关居民收入骤降"),
    "tax_cut":             ("个税减税", "个人所得税下调提高居民可支配收入"),
}
PLACEBO_EVENT = ("图书馆闭馆时间微调", "市图书馆闭馆时间调整10分钟，几乎不影响居民生活")

# Keywords for classifying an existing (timestamped, Chinese-named) comparison dir.
INTERVENTION_KEYWORDS = {
    "traffic_restriction": ("限行", "交通", "traffic"),
    "layoff_shock":        ("裁员", "失业", "layoff"),
    "tax_cut":             ("减税", "个税", "tax"),
}
PLACEBO_KEYWORDS = ("图书馆", "闭馆", "placebo")


# ── small IO helpers (stdlib only; no pandas dependency) ─────────────────────
def read_csv_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _floats(rows: list[dict], col: str) -> list[float]:
    out = []
    for r in rows:
        v = r.get(col)
        if v in (None, "", "nan", "NaN"):
            continue
        try:
            out.append(float(v))
        except ValueError:
            continue
    return out


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ── Track A ──────────────────────────────────────────────────────────────────
def track_a_macro_fit(output_dir: Path) -> dict:
    """Compare aggregate sim statistics against real anchors."""
    metrics = {}
    n_samples = 0
    snap = output_dir / "economy" / "wealth_snapshot.csv"
    if snap.exists():
        rows = read_csv_rows(snap)
        n_samples = len(rows)
        for key in ("engel_coefficient", "savings_rate"):
            vals = _floats(rows, key)
            if vals:
                metrics[key] = statistics.fmean(vals)

    # commute_minutes / transit_share are optional: only scored if the sim
    # emitted the relevant files (not present in current default output).
    commute = output_dir / "state" / "commute_summary.csv"
    if commute.exists():
        vals = _floats(read_csv_rows(commute), "avg_travel_time")
        if vals:
            metrics["commute_minutes"] = statistics.fmean(vals)

    scored = {}
    for key, sim in metrics.items():
        a = ANCHORS[key]
        rel_err = abs(sim - a["value"]) / a["value"]
        s = clamp01(1 - rel_err / a["tol"])
        scored[key] = {"sim": round(sim, 4), "anchor": a["value"],
                       "rel_err": round(rel_err, 4), "score": round(s, 4),
                       "source": a["source"]}

    if not scored:
        return {"track": "A", "status": "n/a",
                "note": "no economy/wealth_snapshot.csv found"}

    s_vals = [m["score"] for m in scored.values()]
    score = statistics.fmean(s_vals)
    passed = score >= 0.6 and all(s > 0 for s in s_vals)
    return {"track": "A", "status": "ok", "score": round(score, 4),
            "pass": passed, "metrics": scored, "n_samples": n_samples}


# ── Track C ──────────────────────────────────────────────────────────────────
def _delta_mean(metrics_csv: Path, metric: str):
    for r in read_csv_rows(metrics_csv):
        if r.get("metric") == metric:
            try:
                return float(r["delta_mean"])
            except (KeyError, ValueError):
                return None
    return None


def _metrics_path(src: Path) -> Path:
    """Accept either a comparison dir or a comparison_metrics.csv path."""
    return src / "comparison_metrics.csv" if src.is_dir() else src


def track_c_causal(sign_sources: dict[str, Path], placebo_dir: Path | None,
                   det_a: Path | None, det_b: Path | None) -> dict:
    """Causal validity: sign-correctness + placebo + determinism.

    sign_sources maps a sign-test name -> comparison dir (or metrics csv).
    """
    out = {"track": "C", "status": "ok"}

    # C1 — known-sign
    sign_results = []
    for t in SIGN_TESTS:
        src = sign_sources.get(t["name"])
        mcsv = _metrics_path(src) if src else None
        delta = _delta_mean(mcsv, t["metric"]) if mcsv and mcsv.exists() else None
        ok = delta is not None and (delta * t["sign"] > 0)
        sign_results.append({**{k: t[k] for k in ("name", "metric", "sign", "why")},
                             "delta_mean": delta, "correct": ok})
    n_eval = sum(1 for r in sign_results if r["delta_mean"] is not None)
    n_ok = sum(1 for r in sign_results if r["correct"])
    sign_score = (n_ok / n_eval) if n_eval else 0.0
    out["sign"] = {"score": round(sign_score, 4), "n_eval": n_eval,
                   "n_correct": n_ok, "tests": sign_results}

    # C2 — placebo / null event
    if placebo_dir and (placebo_dir / "comparison_metrics.csv").exists():
        rows = read_csv_rows(placebo_dir / "comparison_metrics.csv")
        deltas = _floats(rows, "delta_mean")
        within = [abs(d) < PLACEBO_EPS for d in deltas]
        placebo_score = (sum(within) / len(within)) if within else 0.0
        worst = max((abs(d) for d in deltas), default=0.0)
        out["placebo"] = {"score": round(placebo_score, 4), "eps": PLACEBO_EPS,
                          "n_metrics": len(deltas), "max_abs_delta": round(worst, 4)}
    else:
        placebo_score = None
        out["placebo"] = {"score": None, "note": "no placebo comparison provided"}

    # C3 — determinism (same seed, two baseline runs → identical trajectory)
    if det_a and det_b and det_a.exists() and det_b.exists():
        det_score, n = _determinism_score(det_a, det_b)
        out["determinism"] = {"score": round(det_score, 6), "n_points": n}
    else:
        det_score = None
        out["determinism"] = {"score": None, "note": "no baseline pair provided"}

    # aggregate (weights from design doc §2 Track C)
    parts, weights = [], []
    parts.append(sign_score);                weights.append(0.5)
    if placebo_score is not None:
        parts.append(placebo_score);         weights.append(0.25)
    if det_score is not None:
        parts.append(det_score);             weights.append(0.25)
    score = sum(p * w for p, w in zip(parts, weights)) / sum(weights)
    out["score"] = round(score, 4)
    out["pass"] = (sign_score >= 0.75) and (placebo_score is None or placebo_score >= 0.8)
    out["gate_determinism_ok"] = (det_score is None) or (det_score >= 1.0 - 1e-12)
    return out


def _determinism_score(a: Path, b: Path) -> tuple[float, int]:
    """Long-format state files: agent_id,step,metric,value. Fraction matching."""
    def index(p: Path) -> dict:
        d = {}
        for r in read_csv_rows(p):
            try:
                d[(r["agent_id"], r["step"], r["metric"])] = float(r["value"])
            except (KeyError, ValueError):
                continue
        return d
    da, db = index(a), index(b)
    keys = set(da) & set(db)
    if not keys:
        return 0.0, 0
    match = sum(1 for k in keys if math.isclose(da[k], db[k], abs_tol=DET_TOL))
    return match / len(keys), len(keys)


def resolve_from_comparisons(root: Path) -> tuple[dict[str, Path], Path | None]:
    """Classify existing comparison dirs by keyword; newest match per key wins."""
    sign_sources: dict[str, Path] = {}
    placebo: Path | None = None
    if not root.exists():
        return sign_sources, placebo
    dirs = sorted((p for p in root.iterdir()
                   if p.is_dir() and (p / "comparison_metrics.csv").exists()),
                  key=lambda p: p.stat().st_mtime)
    for d in dirs:  # newer dirs come later and overwrite older matches
        nm = d.name.lower()
        for key, kws in INTERVENTION_KEYWORDS.items():
            if any(k.lower() in nm for k in kws):
                sign_sources[key] = d
        if any(k.lower() in nm for k in PLACEBO_KEYWORDS):
            placebo = d
    return sign_sources, placebo


def _run_compare_event(name: str, desc: str, days: int, seed: int,
                       provider: str | None) -> Path | None:
    """Invoke `generative_city_sim.py compare-event`; return the new comparison dir."""
    cmd = [sys.executable, str(SIMULATOR), "compare-event",
           "--event-name", name, "--event-description", desc,
           "--event-day", "2", "--event-time", "09:00",
           "--sim-days", str(days), "--seed", str(seed)]
    if provider:
        cmd += ["--llm-provider", provider]
    print(f"[bench] compare-event: {name} (days={days}, seed={seed})")
    before = {p.name for p in COMPARISONS_OUT.glob("*")} if COMPARISONS_OUT.exists() else set()
    r = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if r.returncode != 0:
        print(f"[bench] WARN: compare-event failed for '{name}' (rc={r.returncode})")
        return None
    new = [p for p in COMPARISONS_OUT.glob("*")
           if p.is_dir() and p.name not in before]
    return max(new, key=lambda p: p.stat().st_mtime, default=None)


def orchestrate_track_c(days: int, seed: int, provider: str | None,
                        det_a: Path | None, det_b: Path | None) -> dict:
    """Live Track C: run compare-event for each intervention + placebo, then score.

    Requires a working LLM provider; each call runs a full paired simulation.
    Determinism is only assessed if --det-a/--det-b are supplied.
    """
    sign_sources: dict[str, Path] = {}
    for key, (name, desc) in INTERVENTIONS.items():
        d = _run_compare_event(name, desc, days, seed, provider)
        if d:
            sign_sources[key] = d
    placebo_dir = _run_compare_event(*PLACEBO_EVENT, days, seed, provider)
    if not sign_sources and placebo_dir is None:
        return {"track": "C", "status": "n/a",
                "note": "live compare-event runs failed — check LLM provider / config"}
    return track_c_causal(sign_sources, placebo_dir, det_a, det_b)


# ── Scorecard ────────────────────────────────────────────────────────────────
def build_scorecard(tracks: dict) -> dict:
    implemented = {k: v for k, v in tracks.items()
                   if isinstance(v, dict) and v.get("status") == "ok"}
    composite = (statistics.fmean([v["score"] for v in implemented.values()])
                 if implemented else None)
    # trust gate: determinism failure poisons the whole card
    c = tracks.get("C", {})
    trust = "OK" if c.get("gate_determinism_ok", True) else "UNTRUSTWORTHY"
    passed = [k for k, v in implemented.items() if v.get("pass")]
    headline = (min(passed, key=lambda k: implemented[k]["score"])
                if passed else None)
    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "trust_gate": trust,
        "composite_hint": round(composite, 4) if composite is not None else None,
        "headline_track": headline,
        "tracks": tracks,
        "note": "composite is a trend hint only — read tracks separately (design §3).",
    }


def render_scorecard_md(sc: dict) -> str:
    L = ["# GAWorld-Bench Scorecard", "",
         f"- generated: {sc['generated']}",
         f"- **trust gate: {sc['trust_gate']}**",
         f"- composite hint: {sc['composite_hint']}  _(trend only, 弱证据)_",
         f"- headline (weakest passing track): {sc['headline_track']}", "",
         "| Track | 命题 | score | pass |", "|---|---|---|---|"]
    names = {"A": "宏观经验拟合", "B": "Stylized-facts", "C": "因果反事实 ⭐",
             "D": "可信度一致性", "E": "可复现/成本"}
    for k in ("A", "B", "C", "D", "E"):
        t = sc["tracks"].get(k, {})
        if t.get("status") == "ok":
            L.append(f"| {k} | {names[k]} | {t.get('score')} | "
                     f"{'PASS' if t.get('pass') else 'FAIL'} |")
        else:
            L.append(f"| {k} | {names[k]} | n/a | {t.get('note', '未实现')} |")
    c = sc["tracks"].get("C", {})
    if c.get("status") == "ok":  # coverage transparency: a 1.0 from 1/4 tests is not full validation
        sign = c.get("sign", {})
        plc = c.get("placebo", {}).get("score")
        det = c.get("determinism", {}).get("score")
        L += ["", f"- Track C 覆盖度: 符号 {sign.get('n_correct')}/{sign.get('n_eval')} "
                  f"(共 {len(SIGN_TESTS)} 项已配置) · 安慰剂 "
                  f"{'未评估' if plc is None else plc} · 确定性 "
                  f"{'未评估' if det is None else det}"]
    return "\n".join(L) + "\n"


def save_scorecard(sc: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "scorecard.json").write_text(
        json.dumps(sc, indent=2, ensure_ascii=False), encoding="utf-8")
    (RESULTS_DIR / "scorecard.md").write_text(
        render_scorecard_md(sc), encoding="utf-8")
    print(f"[bench] wrote {RESULTS_DIR/'scorecard.json'}")
    print(f"[bench] wrote {RESULTS_DIR/'scorecard.md'}")


# ── Report + data-driven improvement suggestions ─────────────────────────────
def _report_track_a(t: dict) -> tuple[list[str], list[str]]:
    """Returns (diagnosis lines, recommendations) for Track A from its numbers."""
    lines, recs = [], []
    n = t.get("n_samples")
    if n:
        lines.append(f"样本：{n} 个 agent 快照。")
    metrics = t.get("metrics", {})
    worst = None
    for key, m in sorted(metrics.items(), key=lambda kv: kv[1]["score"]):
        mark = "✓" if m["score"] >= 0.8 else "✗"
        lines.append(f"- `{key}`: sim {m['sim']} vs 锚点 {m['anchor']} "
                     f"(误差 {m['rel_err'] * 100:.1f}%) {mark}  _{m['source']}_")
        if worst is None or m["score"] < worst[1]["score"]:
            worst = (key, m)
    if worst and worst[1]["score"] < 0.8:
        k, m = worst
        tip = ("明确口径：『住户存款/收入』口径偏高(~43%)，『可支配收入流量储蓄』口径约30-35%"
               if k == "savings_rate" else "核对该指标的仿真计算与聚合方式")
        recs.append(f"主要拖累项 `{k}`（误差 {m['rel_err'] * 100:.1f}%）：{tip}，再校准锚点/容差。")
    if n is not None and n < 10:
        recs.append(f"样本仅 {n} 个，统计不稳；增大 agent 数或延长仿真天数后再评估宏观拟合。")
    recs.append("提醒：Track A 属弱证据（验证的是写进模型的参数），强证据看 Track C。")
    return lines, recs


def _report_track_c(t: dict) -> tuple[list[str], list[str]]:
    lines, recs = [], []
    sign = t.get("sign", {})
    lines.append(f"符号覆盖：{sign.get('n_correct')}/{sign.get('n_eval')}"
                 f"（共 {len(SIGN_TESTS)} 项配置）。")
    failed = []
    for r in sign.get("tests", []):
        if r["delta_mean"] is None:
            lines.append(f"- `{r['name']}/{r['metric']}`: 无对应运行（未评估）")
        else:
            mark = "✓" if r["correct"] else "✗"
            arrow = "↑" if r["sign"] > 0 else "↓"
            lines.append(f"- `{r['name']}/{r['metric']}`: Δ={r['delta_mean']:+.4f} 期望{arrow} {mark}")
            if not r["correct"]:
                failed.append(r)
    if failed:
        mx = max(abs(r["delta_mean"]) for r in failed)
        if mx < PLACEBO_EPS:
            recs.append(f"失败项效应量极小（|Δ|≤{mx:.3f}，与安慰剂同量级）→ 符号由噪声主导，"
                        "不是『方向反了』。经济类干预改用 ≥30 天仿真，并加显著性检验（跨 seed/agent）。")
        else:
            recs.append(f"失败项效应明显（|Δ|max={mx:.3f}）却方向相反 → 检查事件→指标的因果接线是否接反。")
    if sign.get("n_eval", 0) < len(SIGN_TESTS):
        recs.append(f"符号覆盖不足（{sign.get('n_eval')}/{len(SIGN_TESTS)}）：用 `--run` 补跑缺失干预。")
    plc = t.get("placebo", {}).get("score")
    if plc is None:
        recs.append("安慰剂未评估：补一个空事件 compare-event 运行（确保生成 comparison_metrics.csv）。")
    elif plc < 0.8:
        recs.append(f"安慰剂泄漏（{plc}）：空事件也产生效应 → 排查与事件无关的漂移/随机噪声。")
    det = t.get("determinism", {}).get("score")
    if det is None:
        recs.append("确定性未评估：提供两份同 seed baseline（`--det-a/--det-b`）验证可复现性。")
    elif det < 1.0:
        recs.append(f"⚠️ 非确定（{det}）！先修随机源，否则整套结果不可信。")
    return lines, recs


def generate_report(sc: dict) -> str:
    tr = sc["tracks"]
    overview = "\n".join(render_scorecard_md(sc).splitlines()[1:])  # reuse table, drop H1
    L = ["# GAWorld-Bench 运行报告", "",
         "## 结果概览", overview, "",
         "## 分项诊断与建议", ""]
    next_steps: list[str] = []
    if sc["trust_gate"] != "OK":
        next_steps.append("【信任门槛】确定性失败 → 先修随机源，结果暂不可信。")

    names = {"A": "宏观经验拟合", "C": "因果反事实 ⭐"}
    builders = {"A": _report_track_a, "C": _report_track_c}
    for k in ("C", "A"):  # core track first
        t = tr.get(k, {})
        if t.get("status") != "ok":
            continue
        verdict = "PASS" if t.get("pass") else "FAIL"
        diag, recs = builders[k](t)
        L += [f"### Track {k} — {names[k]} — {t.get('score')} {verdict}", *diag, ""]
        if recs:
            L += ["建议：", *[f"{i}. {r}" for i, r in enumerate(recs, 1)], ""]
        next_steps += [f"【Track {k}】{r}" for r in recs]

    na = [k for k in ("B", "D", "E") if tr.get(k, {}).get("status") != "ok"]
    if na:
        L += [f"### 未实现：Track {', '.join(na)}",
              "这些有效性维度尚未评估，当前结论存在盲区（见设计文档路线图 §7）。", ""]

    L += ["## 下一步（按优先级）", ""]
    L += [f"{i}. {s}" for i, s in enumerate(next_steps, 1)] or ["- 暂无（所有已实现 track 通过）。"]
    return "\n".join(L) + "\n"


def save_report(sc: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    md = generate_report(sc)
    (RESULTS_DIR / "report.md").write_text(md, encoding="utf-8")
    archive = RESULTS_DIR / "reports"
    archive.mkdir(exist_ok=True)
    ts = sc["generated"].replace(":", "").replace("-", "")
    (archive / f"report_{ts}.md").write_text(md, encoding="utf-8")
    print(f"[bench] wrote {RESULTS_DIR/'report.md'} (+ archive copy)")


# ── Synthetic fixtures (verification / no-LLM trial) ─────────────────────────
def make_synthetic(root: Path) -> dict:
    """Fabricate structurally-correct outputs so the pipeline runs end-to-end."""
    econ = root / "output" / "economy"; econ.mkdir(parents=True, exist_ok=True)
    # wealth_snapshot near the anchors (engel~0.29, savings~0.33) -> Track A high
    with open(econ / "wealth_snapshot.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["agent_id", "engel_coefficient", "savings_rate"])
        for i, (e, s) in enumerate([(0.31, 0.30), (0.27, 0.36), (0.30, 0.33),
                                    (0.29, 0.31), (0.28, 0.34)], 1):
            w.writerow([i, e, s])

    comps = root / "output" / "comparisons"
    # one correct-sign comparison per intervention
    fixtures = {
        "traffic_restriction": [("mobility_intent", +0.08), ("stress", +0.01)],
        "layoff_shock":        [("econ_security", -0.12), ("stress", +0.09)],
        "tax_cut":             [("econ_security", +0.06), ("mobility_intent", 0.0)],
    }
    for name, deltas in fixtures.items():
        d = comps / name; d.mkdir(parents=True, exist_ok=True)
        _write_metrics(d / "comparison_metrics.csv", deltas)
    # placebo: all deltas tiny
    placebo = comps / "placebo_library_hours"; placebo.mkdir(parents=True, exist_ok=True)
    _write_metrics(placebo / "comparison_metrics.csv",
                   [("emotion", 0.004), ("stress", -0.011), ("econ_security", 0.002),
                    ("mobility_intent", 0.008)])
    # determinism: two identical baseline state files
    st = root / "output" / "state"; st.mkdir(parents=True, exist_ok=True)
    rows = [("1", "0", "emotion", "0.50"), ("1", "1", "emotion", "0.52"),
            ("2", "0", "stress", "0.40"), ("2", "1", "stress", "0.41")]
    for fn in ("baseline_run_a.csv", "baseline_run_b.csv"):
        with open(st / fn, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["agent_id", "step", "metric", "value"])
            w.writerows(rows)
    return {"output_dir": root / "output",
            "sign_sources": {k: comps / k for k in fixtures},
            "placebo_dir": placebo, "det_a": st / "baseline_run_a.csv",
            "det_b": st / "baseline_run_b.csv"}


def _write_metrics(path: Path, deltas: list[tuple[str, float]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "baseline_mean", "event_mean", "delta_mean"])
        for m, d in deltas:
            w.writerow([m, 0.5, 0.5 + d, d])


# ── CLI ──────────────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="GAWorld-Bench harness (v0.1)")
    p.add_argument("--track", choices=["A", "C"], help="run a single track")
    p.add_argument("--all", action="store_true", help="run all implemented tracks")
    p.add_argument("--synthetic", action="store_true",
                   help="fabricate fixtures and run without LLM/sim")
    p.add_argument("--output-dir", type=Path, help="sim output dir (Track A)")
    p.add_argument("--comparisons-root", type=Path, help="Track C: read existing comparisons dir")
    p.add_argument("--placebo-dir", type=Path, help="Track C: placebo comparison dir")
    p.add_argument("--det-a", type=Path, help="Track C: baseline state file A")
    p.add_argument("--det-b", type=Path, help="Track C: baseline state file B")
    p.add_argument("--run", action="store_true",
                   help="Track C: live-run compare-event (needs an LLM provider)")
    p.add_argument("--days", type=int, default=3, help="sim days for live --run")
    p.add_argument("--seed", type=int, default=42, help="random seed for live --run")
    p.add_argument("--llm-provider", help="provider passed to compare-event (e.g. minimax)")
    args = p.parse_args()

    syn_sign_sources = None
    if args.synthetic:
        fx = make_synthetic(Path(tempfile.mkdtemp(prefix="gaworld_bench_")))
        args.output_dir = args.output_dir or fx["output_dir"]
        syn_sign_sources = fx["sign_sources"]
        args.placebo_dir = args.placebo_dir or fx["placebo_dir"]
        args.det_a = args.det_a or fx["det_a"]
        args.det_b = args.det_b or fx["det_b"]

    run_a = args.all or args.track == "A"
    run_c = args.all or args.track == "C"
    if not (run_a or run_c):
        run_a = run_c = True  # default: everything implemented

    tracks: dict = {}
    if run_a:
        out_dir = args.output_dir or (PROJECT_ROOT / "output")  # sensible default
        tracks["A"] = track_a_macro_fit(out_dir)
    if run_c:
        if syn_sign_sources is not None:
            tracks["C"] = track_c_causal(syn_sign_sources, args.placebo_dir,
                                         args.det_a, args.det_b)
        elif args.run:
            tracks["C"] = orchestrate_track_c(args.days, args.seed, args.llm_provider,
                                              args.det_a, args.det_b)
        else:
            root = args.comparisons_root or COMPARISONS_OUT  # default: scan output/comparisons
            ss, auto_placebo = resolve_from_comparisons(root)
            placebo = args.placebo_dir or auto_placebo
            if not ss and placebo is None:
                tracks["C"] = {"track": "C", "status": "n/a",
                               "note": f"在 {root} 未找到可匹配的 comparison 运行; "
                                       "用 --run 实跑或先生成 compare-event 结果"}
            else:
                tracks["C"] = track_c_causal(ss, placebo, args.det_a, args.det_b)
    tracks.setdefault("B", {"status": "n/a", "note": "未实现 (v0.3)"})
    tracks.setdefault("D", {"status": "n/a", "note": "未实现 (v0.4)"})
    tracks.setdefault("E", {"status": "n/a", "note": "确定性见 Track C; 成本未实现 (v0.2)"})

    sc = build_scorecard(tracks)
    save_scorecard(sc)
    save_report(sc)  # every run emits a report with improvement suggestions
    print("\n" + render_scorecard_md(sc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
