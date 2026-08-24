"""Read-only artifact facts and independent review-evidence verification.

The extractor reports what the draft actually contains. It never states
what the value ought to be. The verifier may only reject a review; it
must not generate a correct review or rewrite the artifact.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

_LOG_REASON = (
    "mismatch evidence is not supported by the current artifact"
)


@dataclass(frozen=True)
class ArtifactFact:
    fact_id: str
    artifact_hash: str
    path: str
    symbol: str
    observed_value: Any
    criterion_path: str

    def to_public_dict(self) -> dict[str, Any]:
        """Facts shown to the Reviewer: observed state only, no required value."""
        return {
            "fact_id": self.fact_id,
            "artifact_hash": self.artifact_hash,
            "path": self.path,
            "symbol": self.symbol,
            "observed_value": self.observed_value,
        }


def artifact_hash(content: str) -> str:
    digest = hashlib.sha256((content or "").encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _parse_value(raw: str, kind: str) -> Any:
    text = str(raw).strip().strip("\"'")
    if kind == "int":
        return int(float(text))
    if kind == "float":
        return float(text)
    return text


def values_equal(left: Any, right: Any) -> bool:
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return left == right


def _values_equal(left: Any, right: Any) -> bool:
    return values_equal(left, right)


def extract_facts(
    source: str,
    *,
    specs: list[dict[str, Any]],
    path: str = "main.py",
) -> list[ArtifactFact]:
    hashed = artifact_hash(source)
    facts: list[ArtifactFact] = []
    for index, spec in enumerate(specs, start=1):
        symbol = str(spec["symbol"])
        kind = str(spec.get("parse") or "str")
        match = re.search(
            rf"^{re.escape(symbol)}\s*=\s*(.+)$",
            source or "",
            re.M,
        )
        if not match:
            continue
        try:
            observed = _parse_value(match.group(1), kind)
        except (TypeError, ValueError):
            continue
        facts.append(
            ArtifactFact(
                fact_id=f"fact-{index:02d}",
                artifact_hash=hashed,
                path=path,
                symbol=symbol,
                observed_value=observed,
                criterion_path=str(spec["criterion_path"]),
            )
        )
    return facts


def verify_review(
    review: dict[str, Any] | None,
    *,
    facts: list[ArtifactFact],
    private: dict[str, Any],
    current_hash: str,
) -> dict[str, Any]:
    if not facts:
        return {"ok": False, "reason": "artifact_fact_missing"}
    if not isinstance(review, dict):
        return {"ok": False, "reason": "review_contract_invalid"}
    decision = str(review.get("decision") or "")
    mismatches = list(review.get("mismatches") or [])
    if decision not in {"approve", "revise"}:
        return {"ok": False, "reason": "review_contract_invalid"}
    if decision == "approve" and mismatches:
        return {"ok": False, "reason": "review_decision_inconsistent"}
    if decision == "revise" and not mismatches:
        return {"ok": False, "reason": "review_decision_inconsistent"}

    by_id = {item.fact_id: item for item in facts}
    required = dict(private.get("required_change") or {})
    required["spec_version"] = str(private.get("spec_version") or "")
    registered_criterion = str(private.get("criterion_id") or "")

    if any(item.artifact_hash != current_hash for item in facts):
        return {"ok": False, "reason": "artifact_fact_stale"}

    for item in mismatches:
        fact_id = str(item.get("fact_id") or "")
        if fact_id not in by_id:
            return {"ok": False, "reason": "review_evidence_not_bound"}
        fact = by_id[fact_id]
        if str(item.get("artifact_hash") or fact.artifact_hash) != current_hash:
            return {"ok": False, "reason": "artifact_fact_stale"}
        if not _values_equal(item.get("observed_value"), fact.observed_value):
            return {"ok": False, "reason": "observed_value_false"}
        criterion_id = str(item.get("criterion_id") or "")
        allowed_criterion = {registered_criterion, "spec_version", fact.criterion_path}
        if registered_criterion and criterion_id not in allowed_criterion:
            return {"ok": False, "reason": "required_value_not_registered"}
        required_value = item.get("required_value")
        want = required.get(fact.criterion_path)
        if want is None:
            return {"ok": False, "reason": "required_value_not_registered"}
        if not _values_equal(required_value, want):
            return {"ok": False, "reason": "required_value_not_registered"}
        operator = str(item.get("operator") or "equals")
        if operator != "equals":
            return {"ok": False, "reason": "review_contract_invalid"}
        if _values_equal(fact.observed_value, want):
            return {"ok": False, "reason": "mismatch_not_real"}

    if decision == "approve":
        for fact in facts:
            want = required.get(fact.criterion_path)
            if want is not None and not _values_equal(fact.observed_value, want):
                # Approve is allowed to miss a real gap; that is scored as
                # false-negative, not an evidence-binding failure.
                break
    return {"ok": True, "reason": "ok", "nack": _LOG_REASON}


def nack_payload() -> dict[str, Any]:
    return {"accepted": False, "reason": _LOG_REASON}


def facts_to_public(facts: list[ArtifactFact]) -> list[dict[str, Any]]:
    return [item.to_public_dict() for item in facts]


def dump_facts(facts: list[ArtifactFact]) -> str:
    return json.dumps(facts_to_public(facts), ensure_ascii=False)
