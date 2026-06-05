#!/usr/bin/env python3
"""A/B Analysis: compare Group A (control) vs Group B (experiment) outputs."""
import json, os, re, sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AB_DIR = REPO / "output_ab"


def analyze_group(label, log_path, diaries_dir):
    """Extract metrics from a group's simulation output."""
    metrics = {}

    if not log_path.exists():
        return {f"{label}_error": "log not found"}

    with open(log_path) as f:
        text = f.read()

    # 1. Simulation completeness
    day_headers = re.findall(r'=+ Day (\d+) \(', text)
    metrics["days_completed"] = len(set(day_headers))
    metrics["total_lines"] = len(text.splitlines())

    # 2. Diaries
    diary_files = sorted(diaries_dir.glob("agent_*/day_*.md")) if diaries_dir.exists() else []
    metrics["diary_count"] = len(diary_files)

    # Diary quality metrics
    if diary_files:
        diary_texts = {}
        diarists = defaultdict(list)
        for f in diary_files:
            content = f.read_text(encoding="utf-8")
            m = re.search(r'Day (\d+)', f.name)
            day = int(m.group(1)) if m else 0
            # Extract agent ID
            aid = f.parent.name.replace("agent_", "")
            diarists[int(aid)].append((day, content))

        # Prompt echo rate
        echo_count = sum(
            1 for f in diary_files
            if re.search(r'The user asks|The user is asking|We need to|Thus we need', f.read_text(encoding="utf-8"))
        )
        metrics["diary_echo_count"] = echo_count
        metrics["diary_echo_rate"] = echo_count / max(len(diary_files), 1)

        # Content length (chars after stripping headings)
        body_lengths = []
        for f in diary_files:
            content = f.read_text(encoding="utf-8")
            body = re.sub(r'^#{1,3}\s*.*$', '', content, flags=re.MULTILINE)
            body_lengths.append(len(body.strip()))
        metrics["diary_avg_body_chars"] = round(sum(body_lengths) / max(len(body_lengths), 1))
        metrics["diary_min_body_chars"] = min(body_lengths) if body_lengths else 0

        # Per-agent diversity: compare diaries of same agent across days
        intra_agent_similarity = []
        for aid, entries in diarists.items():
            entries.sort(key=lambda x: x[0])
            texts = [e[1] for e in entries]
            for i in range(len(texts) - 1):
                # Simple word overlap as proxy for similarity
                words_a = set(texts[i].split())
                words_b = set(texts[i + 1].split())
                overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)
                intra_agent_similarity.append(overlap)
        metrics["diary_intra_agent_similarity"] = round(
            sum(intra_agent_similarity) / max(len(intra_agent_similarity), 1), 3
        ) if intra_agent_similarity else 0

        # Cross-agent diversity: compare day 1 diaries across agents
        day1_texts = []
        for aid, entries in diarists.items():
            for day, content in entries:
                if day == 1:
                    day1_texts.append(content)
        cross_similarity = []
        for i in range(len(day1_texts)):
            for j in range(i + 1, len(day1_texts)):
                words_a = set(day1_texts[i].split())
                words_b = set(day1_texts[j].split())
                overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)
                cross_similarity.append(overlap)
        metrics["diary_cross_agent_similarity"] = round(
            sum(cross_similarity) / max(len(cross_similarity), 1), 3
        ) if cross_similarity else 0
    else:
        metrics["diary_echo_rate"] = 0
        metrics["diary_avg_body_chars"] = 0
        metrics["diary_intra_agent_similarity"] = 0
        metrics["diary_cross_agent_similarity"] = 0

    # 3. Reflection diversity
    reflections = re.findall(r'教训：([^；\n]+)', text)
    unique_reflections = len(set(r.strip() for r in reflections))
    metrics["reflection_total"] = len(reflections)
    metrics["reflection_unique"] = unique_reflections
    metrics["reflection_diversity_ratio"] = round(
        unique_reflections / max(len(reflections), 1), 3
    )

    # 4. Activity diversity (unique act types)
    acts = re.findall(r'Act: ([^\n]+)', text)
    unique_acts = len(set(a.strip() for a in acts))
    metrics["action_total"] = len(acts)
    metrics["action_unique"] = unique_acts
    metrics["action_diversity_ratio"] = round(unique_acts / max(len(acts), 1), 3)

    # 5. Human-realistic behaviors (procrastination, distractions)
    human_behaviors = sum(
        1 for a in acts
        if any(kw in a for kw in ["刷手机", "拖延", "拖一会儿", "分心", "冲动"])
    )
    metrics["human_behavior_count"] = human_behaviors
    metrics["human_behavior_rate"] = round(human_behaviors / max(len(acts), 1), 4)

    return metrics


def main():
    print("=" * 60)
    print("A/B TEST ANALYSIS")
    print("=" * 60)

    # Try all possible diary locations
    for group_label, log_name in [("A", "ab_run_a.log"), ("B", "ab_run_b.log")]:
        log_path = AB_DIR / log_name
        diaries_dir = next(
            (d for d in [
                AB_DIR / "group_a" / "diaries",
                AB_DIR / "group_b" / "diaries",
                REPO / "output" / "diaries",
            ] if group_label.upper() in str(d) or (str(d).endswith("diaries") and not str(d).startswith("/") )),
            REPO / "output" / "diaries"
        )
        # simpler approach: find diaries from log path
        possible = [
            AB_DIR / f"group_{group_label.lower()}" / "diaries",
            REPO / "output" / "diaries",
        ]
        diaries_dir = next((p for p in possible if p.exists()), REPO / "output" / "diaries")

        metrics = analyze_group(group_label, log_path, diaries_dir)

        print(f"\n{'─' * 50}")
        print(f"  GROUP {group_label}")
        print(f"{'─' * 50}")
        for k, v in sorted(metrics.items()):
            print(f"  {k:40s} = {v}")

    print(f"\n{'=' * 60}")
    print("  LEGEND")
    print(f"{'=' * 60}")
    print("  diary_echo_rate         — prompts leaked into diary content (0=perfect)")
    print("  diary_avg_body_chars    — average diary length after removing headings")
    print("  diary_intra_agent_similarity  — same agent day-to-day similarity (lower=better)")
    print("  diary_cross_agent_similarity  — different agents same-day similarity (lower=better)")
    print("  reflection_diversity_ratio    — unique reflections / total (higher=better)")
    print("  action_diversity_ratio        — unique actions / total (higher=better)")
    print("  human_behavior_rate           — procrastination/distraction rate (higher=more real)")
    print()

    # Summary verdict
    print("INTERPRETATION:")
    print("  Group B (user's work) should show:")
    print("  • LOWER echo rate        (prompt-echo detection fix)")
    print("  • HIGHER body chars      (more substantive diary content)")
    print("  • LOWER intra/cross similarity (more personalized per agent/day)")
    print("  • HIGHER reflection diversity  (richer internal life)")
    print("  • HIGHER action diversity      (more varied behaviors)")
    print("  • HIGHER human_behavior_rate   (more realistic interruptions)")


if __name__ == "__main__":
    main()
