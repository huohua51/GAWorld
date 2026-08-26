"""Tests for individual, cohort and fast-forward population projection."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaworld.population.projection import PopulationProjectionEngine, TransitionSpec


def _members() -> list[dict[str, object]]:
    return [
        {"agent_id": "low-1", "subgroup": "low", "value": 0.30},
        {"agent_id": "low-2", "subgroup": "low", "value": 0.50},
        {"agent_id": "high-1", "subgroup": "high", "value": 0.70},
        {"agent_id": "high-2", "subgroup": "high", "value": 0.90},
    ]


def _spec() -> TransitionSpec:
    return TransitionSpec(
        metric="economic_security",
        persistence=0.98,
        subgroup_drift={"low": -0.001, "high": 0.002},
        shocks={10: -0.08, 25: 0.04},
    )


def _run(tmp_path: Path, mode: str, days: int = 60) -> dict[str, object]:
    engine = PopulationProjectionEngine(str(tmp_path / f"{mode}.jsonl"), _members(), _spec(), mode)
    engine.advance_to(days)
    result = engine.finish(days)
    assert result["ok"] is True
    return result["summary"]


def test_all_modes_preserve_registered_distribution(tmp_path: Path) -> None:
    individual = _run(tmp_path, "individual")
    cohort = _run(tmp_path, "cohort")
    fast = _run(tmp_path, "fast_forward")

    for approximate in (cohort, fast):
        assert approximate["overall_mean"] == pytest.approx(individual["overall_mean"])
        assert approximate["overall_variance"] == pytest.approx(individual["overall_variance"])
        assert set(approximate["subgroups"]) == set(individual["subgroups"])
        for subgroup, expected in individual["subgroups"].items():
            actual = approximate["subgroups"][subgroup]
            assert actual["count"] == expected["count"]
            assert actual["mean"] == pytest.approx(expected["mean"])
            assert actual["variance"] == pytest.approx(expected["variance"])


def test_approximation_modes_reduce_registered_operation_cost(tmp_path: Path) -> None:
    individual = _run(tmp_path, "individual")
    cohort = _run(tmp_path, "cohort")
    fast = _run(tmp_path, "fast_forward")

    assert individual["operation_units"] == 240
    assert cohort["operation_units"] == 120
    assert fast["operation_units"] < cohort["operation_units"]


@pytest.mark.parametrize("mode", ["individual", "cohort", "fast_forward"])
def test_checkpoint_resume_matches_continuous_run(tmp_path: Path, mode: str) -> None:
    continuous = _run(tmp_path, mode)
    trace = str(tmp_path / f"resume-{mode}.jsonl")
    checkpoint = str(tmp_path / f"resume-{mode}.json")
    first = PopulationProjectionEngine(trace, _members(), _spec(), mode)
    first.advance_to(30)
    first.save_checkpoint(checkpoint)
    resumed = PopulationProjectionEngine.resume_from_checkpoint(trace, checkpoint, _members(), _spec(), mode)
    resumed.advance_to(60)
    result = resumed.finish(60)

    assert result["ok"] is True
    assert result["summary"]["overall_mean"] == pytest.approx(continuous["overall_mean"])
    assert result["summary"]["overall_variance"] == pytest.approx(continuous["overall_variance"])
    assert "checkpoint_loaded" in resumed.event_names()


def test_checkpoint_rejects_changed_population(tmp_path: Path) -> None:
    trace = str(tmp_path / "mismatch.jsonl")
    checkpoint = str(tmp_path / "mismatch.json")
    engine = PopulationProjectionEngine(trace, _members(), _spec(), "cohort")
    engine.advance_to(10)
    engine.save_checkpoint(checkpoint)
    changed = _members()
    changed[0] = {**changed[0], "value": 0.31}

    with pytest.raises(ValueError, match="population mismatch"):
        PopulationProjectionEngine.resume_from_checkpoint(trace, checkpoint, changed, _spec(), "cohort")
