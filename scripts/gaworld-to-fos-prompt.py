#!/usr/bin/env python3
"""GAWorld → FOS AI Scientist Prompt Generator.

Reads GAWorld simulation output and generates a structured research observation
prompt that can be pasted into FOS' AI Scientist to design a follow-up experiment.

Two modes:

  * Manual mode (``--manual STR`` or ``--manual-file PATH``) — wraps
    user-provided observation text in the FOS-expected structured format.

  * Auto mode (``--output-dir PATH``) — reads GAWorld simulation output
    files, builds a comprehensive behaviour summary, sends it to GAWorld's
    configured LLM for analysis, and wraps the LLM response for FOS.

Usage:
    python scripts/gaworld-to-fos-prompt.py --help
    python scripts/gaworld-to-fos-prompt.py --manual "Agent X did Y"
    python scripts/gaworld-to-fos-prompt.py --manual-file observations.txt
    python scripts/gaworld-to-fos-prompt.py --output-dir output/
    python scripts/gaworld-to-fos-prompt.py --output-dir output/ --hint "Look for social withdrawal"
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# GAWorld package integration (lazy)
# ---------------------------------------------------------------------------

_GAROOT: Path | None = None
"""Cached GAWorld repo root (first ancestor with gaworld/)."""


def _find_gaworld_root() -> Path | None:
    """Walk upward from this script's directory to locate the GAWorld repo root."""
    if _GAROOT is not None:
        return _GAROOT
    cursor = Path(__file__).resolve().parent  # scripts/
    for _ in range(6):  # up to 6 levels should be ample
        if (cursor / "gaworld").is_dir() and (cursor / "generative_city_sim.py").is_file():
            globals()["_GAROOT"] = cursor
            return cursor
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    return None


def _ensure_gaworld_on_path() -> None:
    """Add GAWorld repo root to ``sys.path`` so ``gaworld`` package is importable."""
    root = _find_gaworld_root()
    if root is not None and str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _call_llm_lazy(prompt: str, task: str = "fos_prompt", **kwargs: Any) -> str:
    """Import ``call_llm`` lazily and invoke it.

    Raises :class:`ImportError` if ``gaworld`` is unreachable.
    """
    _ensure_gaworld_on_path()
    from gaworld.llm.providers import call_llm  # type: ignore[import-untyped]

    return call_llm(prompt, task=task, **kwargs)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S"
SECTION_SEPARATOR = "=" * 72
SUBSECTION_SEPARATOR = "-" * 48

# ---------------------------------------------------------------------------
# Manual mode helpers
# ---------------------------------------------------------------------------


def _build_manual_prompt(observation: str, hint: str | None = None) -> str:
    """Wrap user-provided observation text for the FOS AI Scientist."""
    now = datetime.now().strftime(TIMESTAMP_FMT)
    parts = [
        SECTION_SEPARATOR,
        "FOS AI Scientist — Research Observation",
        SECTION_SEPARATOR,
        f"Generated: {now}",
        f"Source: GAWorld simulation (manual observation)",
        "",
        "---",
        "",
        "## Research Observation",
        "",
        observation.strip(),
        "",
    ]
    if hint:
        parts.extend([
            "---",
            "",
            "## Analyst Focus Hint",
            "",
            hint.strip(),
            "",
        ])
    parts.extend([
        "---",
        "",
        "## Instructions for AI Scientist",
        "",
        ("The text above describes an observation from a multi-agent simulation "
         "(GAWorld). Please analyze this observation and design a follow-up "
         "experiment. Identify the key variables, suggest a scenario structure, "
         "and propose agent roles, actions, and settings that would replicate "
         "or test this observation in a controlled simulation experiment."),
        "",
        SECTION_SEPARATOR,
    ])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Auto mode — GAWorld output readers
# ---------------------------------------------------------------------------


def _read_profiles_csv(output_dir: Path) -> list[dict[str, str]]:
    """Read ``profiles.csv`` from the output directory.

    Falls back to ``data/hangzhou_agents_state_init.csv`` in the repo root
    if ``profiles.csv`` does not exist in the output directory.

    Returns an empty list if neither file exists or cannot be parsed.
    All status messages go to stderr.
    """
    path = output_dir / "profiles.csv"
    if not path.is_file():
        print(f"[gaworld-to-fos] profiles.csv not found at {path}", file=sys.stderr)
        # Fallback: check repo root's data/ directory
        repo_root = _find_gaworld_root()
        if repo_root is not None:
            fallback = repo_root / "data" / "hangzhou_agents_state_init.csv"
            if fallback.is_file():
                print(f"[gaworld-to-fos] Using fallback profiles from {fallback}", file=sys.stderr)
                path = fallback
            else:
                print(f"[gaworld-to-fos] Fallback not found at {fallback} either", file=sys.stderr)
                return []
        else:
            print("[gaworld-to-fos] GAWorld repo root not found; cannot locate fallback profiles", file=sys.stderr)
            return []
    try:
        with path.open("r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        print(f"[gaworld-to-fos] Loaded {len(rows)} agent profiles from profiles.csv", file=sys.stderr)
        return rows
    except (csv.Error, OSError) as exc:
        print(f"[gaworld-to-fos] Failed to read profiles.csv: {exc}", file=sys.stderr)
        return []


def _load_actions(output_dir: Path, agent_id: int | str) -> list[dict[str, Any]]:
    """Read ``memory/agent_{id}_actions.json`` for a single agent.

    Handles three formats:
    * List of dicts (returned as-is).
    * Dict of lists (activity name -> list of action strings).
    * Any other dict (wrapped as a single-element list for backward compat).

    Returns an empty list if the file does not exist or cannot be parsed.
    """
    path = output_dir / "memory" / f"agent_{agent_id}_actions.json"
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Dict-of-lists format: activity name -> list of action strings
            if data and all(
                isinstance(v, list)
                and v
                and all(isinstance(s, str) for s in v)
                for v in data.values()
            ):
                result: list[dict[str, Any]] = []
                for activity, actions in data.items():
                    for action_str in actions:
                        result.append({"type": activity, "action": action_str})
                return result
            # Fallback: wrap unknown dict format
            return [data]
        return []
    except (json.JSONDecodeError, OSError):
        return []


def _read_agent_diaries(output_dir: Path, agent_id: int | str) -> list[dict[str, str]]:
    """Read all markdown diary files for an agent from ``diaries/agent_{id}/``.

    Returns a list of ``{"day": "001", "content": "..."}`` dicts.
    """
    diary_dir = output_dir / "diaries" / f"agent_{agent_id}"
    if not diary_dir.is_dir():
        return []
    entries: list[dict[str, str]] = []
    try:
        for child in sorted(diary_dir.iterdir()):
            if child.suffix.lower() in (".md", ".markdown") and child.stem.startswith("day_"):
                day_label = child.stem.replace("day_", "")
                content = child.read_text(encoding="utf-8").strip()
                entries.append({"day": day_label, "content": content})
    except OSError as exc:
        print(f"[gaworld-to-fos] Error reading diaries for agent {agent_id}: {exc}", file=sys.stderr)
    return entries


def _read_agent_memory(output_dir: Path, agent_id: int | str) -> list[str]:
    """Read ``memory/agent_{id}.json`` for a single agent.

    The file is typically a list of memory strings (qualitative context
    like init seed profiles, memory reviews, and daily consolidations).
    If it is a dict instead, return an empty list gracefully.

    Returns an empty list if the file does not exist or cannot be parsed.
    """
    path = output_dir / "memory" / f"agent_{agent_id}.json"
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return [str(item) for item in data]
        # If it's a dict, don't treat it as state; return empty gracefully
        return []
    except (json.JSONDecodeError, OSError):
        return []


def _read_state_csvs(output_dir: Path) -> list[dict[str, str]]:
    """Read all ``state/*.csv`` files from the output directory.

    These contain per-agent state trajectories. Returns concatenated rows.
    """
    state_dir = output_dir / "state"
    if not state_dir.is_dir():
        return []
    rows: list[dict[str, str]] = []
    try:
        for child in sorted(state_dir.iterdir()):
            if child.suffix.lower() == ".csv":
                with child.open("r", encoding="utf-8-sig") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        rows.append(row)
    except (csv.Error, OSError) as exc:
        print(f"[gaworld-to-fos] Error reading state CSVs: {exc}", file=sys.stderr)
    return rows


# ---------------------------------------------------------------------------
# Auto mode — aggregation & LLM analysis
# ---------------------------------------------------------------------------


def _summarise_profiles(profiles: list[dict[str, str]]) -> str:
    """Build a condensed text summary of all agent profiles.

    Includes name, age, job, personality, and values for each agent.
    """
    if not profiles:
        return "(No agent profiles available.)"
    lines: list[str] = []
    for p in profiles:
        name = p.get("name", p.get("Name", "?"))
        age = p.get("age", p.get("Age", "?"))
        job = p.get("job", p.get("Job", "?"))
        personality = p.get("personality", p.get("Personality", ""))
        values = p.get("values", p.get("Values", ""))
        daily = p.get("daily_life", p.get("Daily Life", ""))
        line = (
            f"- {name} (age {age}, {job})\n"
            f"  Personality: {personality[:200]}\n"
            f"  Values: {values[:200]}\n"
            f"  Daily life: {daily[:200]}"
        )
        lines.append(line)
    return "\n".join(lines)


def _summarise_diaries(diary_entries: list[dict[str, str]], max_agents: int = 5) -> str:
    """Build a condensed summary of diary entries across agents.

    To avoid blowing the LLM context, we cap at ``max_agents`` and truncate
    long entries.
    """
    if not diary_entries:
        return "(No diary entries available.)"
    # Group by agent (if available)
    return "\n\n".join(
        f"--- Diary (agent, day {e['day']}) ---\n{e['content'][:600]}"
        for e in diary_entries[:max_agents * 3]
    )


def _summarise_memories(memories: dict[str, list[str]]) -> str:
    """Build a condensed summary of qualitative memory entries per agent.

    ``memories`` maps agent_id -> list of memory strings.
    Shows the most recent (last) entries per agent, capped per agent.
    """
    if not memories:
        return "(No qualitative memory entries available.)"
    lines: list[str] = []
    for aid in sorted(memories.keys()):
        texts = memories[aid]
        shown = texts[-5:]  # last 5 entries per agent
        for t in shown:
            lines.append(f"- [Agent {aid}] {t[:300]}")
        if len(texts) > 5:
            lines.append(f"  (... and {len(texts) - 5} more entries for agent {aid})")
    return "\n".join(lines)


def _summarise_actions(actions: list[dict[str, Any]], max_items: int = 50) -> str:
    """Build a condensed summary of agent actions.

    Truncates to ``max_items`` entries to avoid context overflow.
    """
    if not actions:
        return "(No action records available.)"
    lines: list[str] = []
    for act in actions[:max_items]:
        time_str = act.get("time", act.get("timestamp", ""))
        activity = act.get("activity", act.get("type", ""))
        action = act.get("action", "")
        lines.append(f"- [{time_str}] {activity}: {action}")
    if len(actions) > max_items:
        lines.append(f"(... and {len(actions) - max_items} more actions)")
    return "\n".join(lines)


def _summarise_state_trajectories(state_rows: list[dict[str, str]]) -> str:
    """Build a compact summary of state trajectories."""
    if not state_rows:
        return "(No state trajectory data available.)"
    # Group by agent_id and compute simple stats
    from collections import defaultdict

    by_agent: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in state_rows:
        aid = row.get("agent_id", row.get("id", "?"))
        by_agent[aid].append(row)

    lines: list[str] = []
    for aid, entries in sorted(by_agent.items()):
        # Show first and last entry as a trajectory summary
        first = entries[0]
        last = entries[-1]
        keys = [k for k in first if k not in ("agent_id", "id", "day", "time", "timestamp")]
        deltas = []
        for k in keys:
            try:
                v0 = float(first.get(k, 0))
                v1 = float(last.get(k, 0))
                delta = v1 - v0
                deltas.append(f"{k}: {v0:.2f} → {v1:.2f} (Δ={delta:+.2f})")
            except (TypeError, ValueError):
                pass
        if deltas:
            lines.append(f"Agent {aid} ({len(entries)} samples): {'; '.join(deltas[:5])}")
    return "\n".join(lines) if lines else "(State data insufficient for summary.)"


def _build_auto_observation_prompt(
    output_dir: Path,
    hint: str | None = None,
    max_profiles: int = 10,
) -> str:
    """Build a comprehensive prompt from GAWorld output for the LLM to analyse.

    All status messaging goes to stderr. The returned string is the prompt
    to send to GAWorld's LLM.
    """
    profiles = _read_profiles_csv(output_dir)
    print(f"[gaworld-to-fos] Found {len(profiles)} profiles", file=sys.stderr)

    # Gather sample agent IDs from profiles
    sample_ids: list[str] = []
    for p in profiles[:max_profiles]:
        aid = str(p.get("id", p.get("ID", p.get("Id", ""))))
        if aid.strip() and aid not in sample_ids:
            sample_ids.append(aid)

    # Read actions, diaries, and memory entries for sample agents
    all_actions: list[dict[str, Any]] = []
    all_diaries: list[dict[str, str]] = []
    all_memories: dict[str, list[str]] = {}
    for aid in sample_ids:
        actions = _load_actions(output_dir, aid)
        all_actions.extend(actions)
        diaries = _read_agent_diaries(output_dir, aid)
        all_diaries.extend(diaries)
        memories = _read_agent_memory(output_dir, aid)
        if memories:
            all_memories[aid] = memories
        if actions:
            print(f"[gaworld-to-fos] Agent {aid}: {len(actions)} actions, {len(diaries)} diaries, {len(memories)} memory entries", file=sys.stderr)

    # Read state trajectories
    state_rows = _read_state_csvs(output_dir)
    print(f"[gaworld-to-fos] State trajectory rows: {len(state_rows)}", file=sys.stderr)

    # List output directory structure for context
    print(f"[gaworld-to-fos] Output directory: {output_dir}", file=sys.stderr)

    # Build the analysis prompt
    summary_parts = [
        "You are an AI social scientist analysing the output of a multi-agent simulation (GAWorld).",
        "Below is the data from a completed simulation run. Identify interesting behaviour patterns,",
        "formulate hypotheses, and propose an experimental design for a follow-up study.",
        "",
        SECTION_SEPARATOR,
        "SIMULATION OUTPUT DATA",
        SECTION_SEPARATOR,
        "",
        "--- Agent Profiles ---",
        _summarise_profiles(profiles[:max_profiles]),
        "",
        "--- Agent Actions (sample) ---",
        _summarise_actions(all_actions),
        "",
        "--- Agent Diaries (sample) ---",
        _summarise_diaries(all_diaries),
        "",
        "--- Qualitative Memory Entries ---",
        _summarise_memories(all_memories),
        "",
        "--- State Trajectories ---",
        _summarise_state_trajectories(state_rows),
        "",
    ]
    if hint:
        summary_parts.extend([
            "---",
            "",
            "## Analyst Focus Hint",
            "",
            hint.strip(),
            "",
        ])
    summary_parts.extend([
        "---",
        "",
        "## Task",
        "",
        ("Based on the simulation data above, please:\n"
         "1. Identify 2-4 interesting behaviour patterns or emergent phenomena.\n"
         "2. For each pattern, propose a falsifiable hypothesis.\n"
         "3. Design a follow-up experiment: suggest agent roles, experimental conditions,\n"
         "   key variables to measure, and expected outcomes.\n"
         "4. Note any limitations or confounding factors in the current data.\n"
         "\n"
         "Output your analysis in a clear structured format suitable for an experiment design."),
        "",
        SECTION_SEPARATOR,
    ])
    return "\n".join(summary_parts)


# ---------------------------------------------------------------------------
# FOS wrapping helpers
# ---------------------------------------------------------------------------


def _wrap_for_fos(analysis_text: str, output_dir: Path | None = None) -> str:
    """Wrap LLM analysis text in a FOS AI Scientist 'Analyze Research Text' block.

    This output is what the user copies into FOS → AI Scientist → "Analyze Research Text".
    """
    now = datetime.now().strftime(TIMESTAMP_FMT)
    source = str(output_dir) if output_dir else "manual observation"
    parts = [
        SECTION_SEPARATOR,
        "FOS AI Scientist — Research Observation",
        SECTION_SEPARATOR,
        f"Generated: {now}",
        f"Source: GAWorld simulation ({source})",
        "",
        "---",
        "",
        "## Research Observation",
        "",
        analysis_text.strip(),
        "",
        "---",
        "",
        "## Instructions for AI Scientist",
        "",
        ("The text above describes observations and hypotheses from a multi-agent "
         "simulation (GAWorld). Please analyze this research text and structure it "
         "into an experiment design. Extract: scenario description, participant "
         "roles, actions/decisions, experimental settings, key variables, and "
         "any assumptions or missing information. Use the FOS experiment schema."),
        "",
        SECTION_SEPARATOR,
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# English summary helpers
# ---------------------------------------------------------------------------


def _build_english_summary_prompt(
    output_dir: Path,
    max_profiles: int = 10,
) -> str:
    """Build a prompt asking the LLM to translate Chinese sim data into an English summary.

    Reads the same GAWorld simulation data as the normal FOS flow and wraps it
    in a translation/summarisation prompt for the LLM.
    """
    profiles = _read_profiles_csv(output_dir)

    sample_ids: list[str] = []
    for p in profiles[:max_profiles]:
        aid = str(p.get("id", p.get("ID", p.get("Id", ""))))
        if aid.strip() and aid not in sample_ids:
            sample_ids.append(aid)

    all_actions: list[dict[str, Any]] = []
    all_diaries: list[dict[str, str]] = []
    all_memories: dict[str, list[str]] = {}
    for aid in sample_ids:
        actions = _load_actions(output_dir, aid)
        all_actions.extend(actions[:20])  # truncate per agent
        diaries = _read_agent_diaries(output_dir, aid)
        for d in diaries[:3]:  # limit diaries per agent
            d["content"] = d["content"][:500]  # truncate content
            all_diaries.append(d)
        memories = _read_agent_memory(output_dir, aid)
        if memories:
            all_memories[aid] = memories[-3:]  # last 3 entries

    state_rows = _read_state_csvs(output_dir)

    data_str = (
        f"Agent profiles:\n{_summarise_profiles(profiles[:max_profiles])}\n\n"
        f"Sample actions:\n{_summarise_actions(all_actions, max_items=30)}\n\n"
        f"Sample diaries:\n{_summarise_diaries(all_diaries)}\n\n"
        f"Memory entries:\n{_summarise_memories(all_memories)}\n\n"
        f"State trajectories:\n{_summarise_state_trajectories(state_rows)}"
    )

    # Truncate if too long
    if len(data_str) > 7000:
        data_str = data_str[:7000] + "\n\n[data truncated]"

    prompt = (
        "You are a bilingual research assistant. Below is raw Chinese simulation "
        "output from GAWorld, a multi-agent city simulator. Please translate the "
        "following into English and produce a clear, readable summary of what happened.\n\n"
        "Key data:\n"
        "1. Agent profiles (name, age, personality, values, daily life habits)\n"
        "2. Per-agent actions across each day (activity names and action descriptions)\n"
        "3. State trajectories (emotion, stress, energy, etc.) — translate the labels "
        "and summarise changes\n"
        "4. Diary entries (first-person Chinese text → English summary)\n\n"
        "Format your output as a clean English report with sections:\n"
        "## Simulation Overview\n"
        "## Agent Profiles\n"
        "## Daily Activities by Agent\n"
        "## State Changes\n"
        "## Diary Highlights\n"
        "## Key Observations\n\n"
        f"--- RAW CHINESE DATA ---\n{data_str}"
    )
    return prompt


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a structured research observation prompt for FOS AI Scientist "
            "from GAWorld simulation output or manual observation text."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --manual \"Agent X showed reduced social interaction after policy Y\"\n"
            "  %(prog)s --manual-file observations.txt\n"
            "  %(prog)s --output-dir /path/to/gaworld/output\n"
            "  %(prog)s --output-dir output/ --hint \"Look for economic anxiety patterns\"\n"
        ),
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--manual",
        type=str,
        default=None,
        help="Manual observation text to wrap for FOS AI Scientist.",
    )
    mode.add_argument(
        "--manual-file",
        type=str,
        default=None,
        help="Path to a text file containing the observation.",
    )
    mode.add_argument(
        "--output-dir",
        "--output",
        type=str,
        default=None,
        dest="output_dir",
        help=(
            "Path to a GAWorld simulation output directory. The script reads "
            "profiles.csv, actions, diaries, and state data from this directory."
        ),
    )

    parser.add_argument(
        "--hint",
        type=str,
        default=None,
        help=(
            "Optional focus hint for the LLM analysis (auto mode only). "
            "E.g. --hint 'Look for social withdrawal patterns'"
        ),
    )

    parser.add_argument(
        "--max-profiles",
        type=int,
        default=10,
        help="Maximum number of agent profiles to include in auto mode (default: 10).",
    )

    parser.add_argument(
        "--english",
        action="store_true",
        help=( "Print an English summary of the simulation output (translates Chinese "
               "data) before the FOS prompt." ),
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.english and not args.output_dir:
        print("Error: --english requires --output-dir.", file=sys.stderr)
        sys.exit(1)

    # ---- Manual mode ----
    if args.manual is not None:
        observation = args.manual
        prompt = _build_manual_prompt(observation, hint=args.hint)
        # Final prompt goes to stdout (for piping/redirecting)
        print(prompt)
        return

    if args.manual_file is not None:
        path = Path(args.manual_file)
        if not path.is_file():
            print(f"Error: manual file not found: {path}", file=sys.stderr)
            sys.exit(1)
        observation = path.read_text(encoding="utf-8").strip()
        prompt = _build_manual_prompt(observation, hint=args.hint)
        print(prompt)
        return

    # ---- Auto mode ----
    output_dir = Path(args.output_dir)
    if not output_dir.is_dir():
        print(f"Error: output directory not found: {output_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"[gaworld-to-fos] Auto mode: reading GAWorld output from {output_dir.resolve()}", file=sys.stderr)
    print(f"[gaworld-to-fos] Hint: {args.hint or '(none)'}", file=sys.stderr)

    # Build the observation prompt for GAWorld's LLM
    observation_prompt = _build_auto_observation_prompt(
        output_dir,
        hint=args.hint,
        max_profiles=args.max_profiles,
    )

    # Call GAWorld's LLM for analysis
    print("[gaworld-to-fos] Calling GAWorld LLM for analysis...", file=sys.stderr)
    try:
        llm_analysis = _call_llm_lazy(observation_prompt, task="fos_prompt")
    except ImportError as exc:
        print(f"[gaworld-to-fos] Error: cannot import gaworld.llm.providers: {exc}", file=sys.stderr)
        print("[gaworld-to-fos] Make sure this script is run from the GAWorld repo or that the repo root is on PYTHONPATH.", file=sys.stderr)
        # Fall back to a simplified direct prompt (no LLM analysis)
        llm_analysis = (
            "[LLM analysis unavailable — gaworld package not importable.\n"
            "The raw simulation data is included below for manual review.]\n\n"
            f"{observation_prompt}"
        )
    except Exception as exc:
        print(f"[gaworld-to-fos] LLM call failed: {exc}", file=sys.stderr)
        print("[gaworld-to-fos] Including raw simulation data as fallback.", file=sys.stderr)
        llm_analysis = (
            f"[LLM analysis failed: {exc}]\n\n"
            f"Raw simulation data:\n\n{observation_prompt}"
        )

    # ---- English summary (optional) ----
    if args.english:
        print("[gaworld-to-fos] Generating English summary...", file=sys.stderr)
        english_prompt = _build_english_summary_prompt(
            output_dir,
            max_profiles=args.max_profiles,
        )
        try:
            english_summary = _call_llm_lazy(english_prompt, task="english_summary")
            print("\n" + "=" * 60)
            print("  ENGLISH SUMMARY OF SIMULATION OUTPUT")
            print("=" * 60 + "\n")
            print(english_summary)
            print("\n" + "=" * 60 + "\n")
        except Exception as e:
            print(f"[gaworld-to-fos] Warning: English summary LLM call failed: {e}", file=sys.stderr)

    # Wrap the LLM analysis for FOS
    fos_prompt = _wrap_for_fos(llm_analysis, output_dir=output_dir)

    # Final prompt goes to stdout (easy to pipe/redirect)
    print(fos_prompt)


if __name__ == "__main__":
    main()
