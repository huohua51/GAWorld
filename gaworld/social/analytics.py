"""Readable outputs for the GAWorld social subsystem."""

from __future__ import annotations

import csv
import html
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from gaworld.social.schemas import SocialInteractionEvent


def _ensure_parent(path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def format_console_event(event: SocialInteractionEvent) -> str:
    """One compact line for the main simulation console."""

    return (
        f"[Social {event.day} {event.time}] "
        f"{event.source_name} -> {event.target_name} "
        f"{event.interaction_type}「{event.topic}」 "
        f"({event.motivation_type}/{event.motivation})"
    )


def write_social_timeline(events: Iterable[SocialInteractionEvent], path: str | Path) -> None:
    """Write a readable chronological event timeline."""

    event_list = list(events)
    out = _ensure_parent(path)
    lines = ["# Social Timeline", ""]
    if not event_list:
        lines.append("No social interactions were generated.")
    for event in event_list:
        lines.extend(
            [
                f"## Day {event.day} {event.time} | {event.source_name} -> {event.target_name}",
                "",
                f"- Type: `{event.interaction_type}`",
                f"- Motivation: `{event.motivation_type}` / `{event.motivation}`",
                f"- Topic: {event.topic}",
                f"- Message: {event.message}",
                f"- Reply: {event.reply}",
                f"- Effect: {event.subjective_effect}",
                (
                    "- Delta: "
                    f"emotion_source={event.emotion_delta_source:+.3f}, "
                    f"emotion_target={event.emotion_delta_target:+.3f}, "
                    f"stress_source={event.stress_delta_source:+.3f}, "
                    f"stress_target={event.stress_delta_target:+.3f}, "
                    f"trust={event.trust_delta:+.3f}, "
                    f"closeness={event.closeness_delta:+.3f}, "
                    f"friction={event.friction_delta:+.3f}"
                ),
                f"- Decision: {event.decision_reason}",
                f"- Motivation reason: {event.motivation_reason}",
                "",
            ]
        )
    out.write_text("\n".join(lines), encoding="utf-8")


def write_relationship_changes(events: Iterable[SocialInteractionEvent], path: str | Path) -> None:
    """Aggregate pair-level relationship deltas into a CSV."""

    rows_by_pair: dict[tuple[int, int], dict[str, object]] = {}
    for event in events:
        pair = tuple(sorted((event.source_id, event.target_id)))
        row = rows_by_pair.setdefault(
            pair,
            {
                "source_id": pair[0],
                "target_id": pair[1],
                "names": "",
                "interaction_count": 0,
                "trust_delta": 0.0,
                "closeness_delta": 0.0,
                "friction_delta": 0.0,
            },
        )
        row["names"] = f"{event.source_name} / {event.target_name}"
        row["interaction_count"] = int(row["interaction_count"]) + 1
        row["trust_delta"] = float(row["trust_delta"]) + event.trust_delta
        row["closeness_delta"] = float(row["closeness_delta"]) + event.closeness_delta
        row["friction_delta"] = float(row["friction_delta"]) + event.friction_delta

    out = _ensure_parent(path)
    with out.open("w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "source_id",
            "target_id",
            "names",
            "interaction_count",
            "trust_delta",
            "closeness_delta",
            "friction_delta",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(rows_by_pair.values(), key=lambda item: int(item["interaction_count"]), reverse=True):
            writer.writerow(row)


def write_daily_summary(events: Iterable[SocialInteractionEvent], path: str | Path) -> None:
    """Write a high-level Markdown summary that is easy to present."""

    event_list = list(events)
    out = _ensure_parent(path)
    lines = ["# Social Interaction Summary", ""]
    if not event_list:
        lines.append("No social interactions were generated.")
        out.write_text("\n".join(lines), encoding="utf-8")
        return

    type_counts = Counter(event.interaction_type for event in event_list)
    motivation_type_counts = Counter(event.motivation_type for event in event_list)
    motivation_counts = Counter(event.motivation for event in event_list)
    agent_counts = Counter()
    topic_agents: dict[str, set[int]] = defaultdict(set)
    trust_by_pair: Counter[str] = Counter()
    friction_by_pair: Counter[str] = Counter()
    emotion_by_agent: Counter[str] = Counter()

    for event in event_list:
        agent_counts[event.source_name] += 1
        agent_counts[event.target_name] += 1
        topic_agents[event.topic].update([event.source_id, event.target_id])
        pair_name = f"{event.source_name} / {event.target_name}"
        trust_by_pair[pair_name] += event.trust_delta
        friction_by_pair[pair_name] += event.friction_delta
        emotion_by_agent[event.source_name] += event.emotion_delta_source
        emotion_by_agent[event.target_name] += event.emotion_delta_target

    lines.extend(
        [
            f"- Total interactions: {len(event_list)}",
            f"- Agents involved: {len(agent_counts)}",
            f"- Message topics: {len(topic_agents)}",
            "",
            "## Interaction Types",
            "",
        ]
    )
    for kind, count in type_counts.most_common():
        lines.append(f"- `{kind}`: {count}")

    lines.extend(["", "## Motivation Types", ""])
    for kind, count in motivation_type_counts.most_common():
        lines.append(f"- `{kind}`: {count}")

    lines.extend(["", "## Top Motivations", ""])
    for motivation, count in motivation_counts.most_common(8):
        lines.append(f"- `{motivation}`: {count}")

    lines.extend(["", "## Most Social Agents", ""])
    for name, count in agent_counts.most_common(5):
        lines.append(f"- {name}: {count} interactions")

    lines.extend(["", "## Topic Spread", ""])
    for topic, agents in sorted(topic_agents.items(), key=lambda item: len(item[1]), reverse=True)[:5]:
        lines.append(f"- {topic}: reached {len(agents)} agents")

    lines.extend(["", "## Relationship Changes", ""])
    for pair, delta in trust_by_pair.most_common(5):
        lines.append(f"- Trust increased: {pair} {delta:+.3f}")
    for pair, delta in friction_by_pair.most_common(5):
        if delta > 0:
            lines.append(f"- Friction increased: {pair} {delta:+.3f}")

    lines.extend(["", "## Emotion Changes", ""])
    for name, delta in emotion_by_agent.most_common(5):
        lines.append(f"- Emotion increased: {name} {delta:+.3f}")
    for name, delta in sorted(emotion_by_agent.items(), key=lambda item: item[1])[:5]:
        if delta < 0:
            lines.append(f"- Emotion decreased: {name} {delta:+.3f}")

    out.write_text("\n".join(lines), encoding="utf-8")


def _bar_rows(counter: Counter[str], *, max_items: int = 8) -> str:
    if not counter:
        return '<div class="empty">No data</div>'
    max_count = max(counter.values()) or 1
    rows = []
    for label, count in counter.most_common(max_items):
        width = 100 * count / max_count
        rows.append(
            '<div class="bar-row">'
            f'<span class="bar-label">{html.escape(str(label))}</span>'
            '<span class="bar-track">'
            f'<span class="bar-fill" style="width:{width:.1f}%"></span>'
            "</span>"
            f'<span class="bar-count">{count}</span>'
            "</div>"
        )
    return "\n".join(rows)


def _signed(value: float) -> str:
    return f"{value:+.3f}"


def write_dashboard(events: Iterable[SocialInteractionEvent], path: str | Path) -> None:
    """Write a self-contained HTML dashboard for social simulation results."""

    event_list = list(events)
    out = _ensure_parent(path)
    type_counts = Counter(event.interaction_type for event in event_list)
    motivation_type_counts = Counter(event.motivation_type for event in event_list)
    motivation_counts = Counter(event.motivation for event in event_list)
    agent_counts = Counter()
    topic_agents: dict[str, set[int]] = defaultdict(set)
    trust_by_pair: Counter[str] = Counter()
    friction_by_pair: Counter[str] = Counter()
    emotion_by_agent: Counter[str] = Counter()

    for event in event_list:
        agent_counts[event.source_name] += 1
        agent_counts[event.target_name] += 1
        topic_agents[event.topic].update([event.source_id, event.target_id])
        pair_name = f"{event.source_name} / {event.target_name}"
        trust_by_pair[pair_name] += event.trust_delta
        friction_by_pair[pair_name] += event.friction_delta
        emotion_by_agent[event.source_name] += event.emotion_delta_source
        emotion_by_agent[event.target_name] += event.emotion_delta_target

    topic_rows = []
    for topic, agents in sorted(topic_agents.items(), key=lambda item: len(item[1]), reverse=True)[:8]:
        topic_rows.append(
            "<tr>"
            f"<td>{html.escape(topic)}</td>"
            f"<td>{len(agents)}</td>"
            "</tr>"
        )

    relationship_rows = []
    seen_pairs = set()
    ranked_pairs = list(trust_by_pair.most_common(8))
    for pair, trust_delta in ranked_pairs:
        seen_pairs.add(pair)
        relationship_rows.append(
            "<tr>"
            f"<td>{html.escape(pair)}</td>"
            f"<td>{_signed(trust_delta)}</td>"
            f"<td>{_signed(friction_by_pair[pair])}</td>"
            "</tr>"
        )
    for pair, friction_delta in friction_by_pair.most_common(8):
        if pair in seen_pairs or friction_delta <= 0:
            continue
        relationship_rows.append(
            "<tr>"
            f"<td>{html.escape(pair)}</td>"
            f"<td>{_signed(trust_by_pair[pair])}</td>"
            f"<td>{_signed(friction_delta)}</td>"
            "</tr>"
        )
        if len(relationship_rows) >= 8:
            break

    timeline_cards = []
    for event in event_list[:80]:
        timeline_cards.append(
            '<article class="event-card">'
            '<div class="event-top">'
            f"<strong>Day {event.day} {html.escape(event.time)}</strong>"
            f"<span>{html.escape(event.interaction_type)}</span>"
            "</div>"
            f"<h3>{html.escape(event.source_name)} -> {html.escape(event.target_name)}</h3>"
            f'<p class="topic">{html.escape(event.topic)}</p>'
            f"<p>{html.escape(event.message)}</p>"
            f'<p class="reply">{html.escape(event.reply)}</p>'
            '<div class="chips">'
            f"<span>{html.escape(event.motivation_type)}</span>"
            f"<span>{html.escape(event.motivation)}</span>"
            f"<span>trust {_signed(event.trust_delta)}</span>"
            f"<span>friction {_signed(event.friction_delta)}</span>"
            "</div>"
            f'<details><summary>Why this interaction?</summary><p>{html.escape(event.motivation_reason)}</p>'
            f"<p>{html.escape(event.decision_reason)}</p></details>"
            "</article>"
        )

    content = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GAWorld Social Dashboard</title>
  <style>
    :root {{
      --bg: #f7f7f5;
      --panel: #ffffff;
      --ink: #1f2933;
      --muted: #65717e;
      --line: #dfe3e6;
      --blue: #2563eb;
      --green: #059669;
      --orange: #d97706;
      --red: #dc2626;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.5;
    }}
    header {{
      padding: 28px 36px 18px;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }}
    h1 {{ margin: 0 0 6px; font-size: 28px; }}
    header p {{ margin: 0; color: var(--muted); }}
    main {{ padding: 24px 36px 40px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(140px, 1fr));
      gap: 14px;
      margin-bottom: 20px;
    }}
    .metric, .panel, .event-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }}
    .metric {{ padding: 16px; }}
    .metric span {{ display: block; color: var(--muted); font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 28px; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      align-items: start;
    }}
    .panel {{ padding: 18px; }}
    .panel h2 {{ margin: 0 0 14px; font-size: 18px; }}
    .bar-row {{
      display: grid;
      grid-template-columns: 150px 1fr 36px;
      gap: 10px;
      align-items: center;
      margin: 9px 0;
      font-size: 13px;
    }}
    .bar-label {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--muted);
    }}
    .bar-track {{
      height: 10px;
      background: #edf1f4;
      border-radius: 999px;
      overflow: hidden;
    }}
    .bar-fill {{
      display: block;
      height: 100%;
      background: var(--blue);
      border-radius: 999px;
    }}
    .bar-count {{ text-align: right; color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; }}
    .timeline {{
      margin-top: 18px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .event-card {{ padding: 16px; }}
    .event-top {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 13px;
    }}
    .event-card h3 {{ margin: 8px 0 6px; font-size: 17px; }}
    .topic {{ color: var(--orange); margin: 0 0 10px; }}
    .reply {{ color: var(--muted); }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }}
    .chips span {{
      padding: 3px 7px;
      border-radius: 999px;
      background: #edf1f4;
      font-size: 12px;
      color: #394553;
    }}
    details {{ margin-top: 10px; color: var(--muted); font-size: 13px; }}
    summary {{ cursor: pointer; color: var(--ink); }}
    .empty {{ color: var(--muted); font-size: 13px; }}
    @media (max-width: 900px) {{
      header, main {{ padding-left: 18px; padding-right: 18px; }}
      .metrics, .grid, .timeline {{ grid-template-columns: 1fr; }}
      .bar-row {{ grid-template-columns: 110px 1fr 32px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>GAWorld Social Dashboard</h1>
    <p>社交互动、动机、消息传播和关系变化的可视化摘要。</p>
  </header>
  <main>
    <section class="metrics">
      <div class="metric"><span>Total interactions</span><strong>{len(event_list)}</strong></div>
      <div class="metric"><span>Agents involved</span><strong>{len(agent_counts)}</strong></div>
      <div class="metric"><span>Topics</span><strong>{len(topic_agents)}</strong></div>
      <div class="metric"><span>Interaction types</span><strong>{len(type_counts)}</strong></div>
    </section>
    <section class="grid">
      <div class="panel"><h2>Interaction Types</h2>{_bar_rows(type_counts)}</div>
      <div class="panel"><h2>Motivation Types</h2>{_bar_rows(motivation_type_counts)}</div>
      <div class="panel"><h2>Top Motivations</h2>{_bar_rows(motivation_counts)}</div>
      <div class="panel"><h2>Most Social Agents</h2>{_bar_rows(agent_counts)}</div>
      <div class="panel">
        <h2>Topic Spread</h2>
        <table><thead><tr><th>Topic</th><th>Reached agents</th></tr></thead><tbody>
        {''.join(topic_rows) or '<tr><td colspan="2">No data</td></tr>'}
        </tbody></table>
      </div>
      <div class="panel">
        <h2>Relationship Changes</h2>
        <table><thead><tr><th>Pair</th><th>Trust</th><th>Friction</th></tr></thead><tbody>
        {''.join(relationship_rows) or '<tr><td colspan="3">No data</td></tr>'}
        </tbody></table>
      </div>
    </section>
    <section>
      <h2>Timeline</h2>
      <div class="timeline">
        {''.join(timeline_cards) or '<div class="empty">No social interactions were generated.</div>'}
      </div>
    </section>
  </main>
</body>
</html>
"""
    out.write_text(content, encoding="utf-8")
