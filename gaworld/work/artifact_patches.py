"""Independent verification that an Executor actually applied a typed patch.

The verifier may only reject a false application. It must not rewrite the
artifact or tell the Executor the correct value.
"""

from __future__ import annotations

import json
import re
from typing import Any

from gaworld.work.artifact_facts import artifact_hash, extract_facts, values_equal

_ALLOWED_NEW = {"APPLIED_PATCH_IDS", "ARTIFACT_HASH_AFTER", "ARTIFACT_SPEC_VERSION"}
_CLAIM_REASON = "patch was not applied to the current artifact"


def parse_executor_claim(source: str) -> dict[str, Any]:
    ids: list[str] = []
    match = re.search(r"APPLIED_PATCH_IDS\s*=\s*(\[[^\]]*\]|[\"'][^\"']+[\"'])", source or "")
    if match:
        raw = match.group(1).replace("'", '"')
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = []
        if isinstance(payload, str):
            ids = [payload]
        elif isinstance(payload, list):
            ids = [str(item) for item in payload]
    spec = None
    spec_match = re.search(r'ARTIFACT_SPEC_VERSION\s*=\s*["\'](v\d+)["\']', source or "")
    if spec_match:
        spec = spec_match.group(1)
    else:
        spec_match = re.search(r'SPEC_VERSION\s*=\s*["\'](v\d+)["\']', source or "")
        if spec_match:
            spec = spec_match.group(1)
    hashed = None
    hash_match = re.search(r'ARTIFACT_HASH_AFTER\s*=\s*["\']([^"\']+)["\']', source or "")
    if hash_match:
        hashed = hash_match.group(1)
    return {
        "applied_patch_ids": ids,
        "artifact_spec_version": spec,
        "artifact_hash_after": hashed,
    }


def _top_level_names(source: str) -> set[str]:
    return set(re.findall(r"^([A-Z_][A-Z0-9_]*)\s*=", source or "", re.M))


def _values(source: str, specs: list[dict[str, Any]]) -> dict[str, Any]:
    facts = extract_facts(source or "", specs=specs)
    return {item.criterion_path: item.observed_value for item in facts}


def verify_applied(
    *,
    before: str,
    after: str,
    patches: list[dict[str, Any]],
    specs: list[dict[str, Any]],
) -> dict[str, Any]:
    if not patches:
        return {"ok": False, "reason": "patch_not_read", "applied": False, "applied_ids": []}
    if not after:
        return {"ok": False, "reason": "artifact_test_failed", "applied": False, "applied_ids": []}

    before_vals = _values(before, specs)
    after_vals = _values(after, specs)
    claim = parse_executor_claim(after)
    before_hash = artifact_hash(before)
    after_hash = artifact_hash(after)
    claimed_ids = set(claim.get("applied_patch_ids") or [])
    extra_names = _top_level_names(after) - _top_level_names(before) - _ALLOWED_NEW

    applied_ids: list[str] = []
    value_hits = 0
    for patch in patches:
        path = str(patch.get("path") or "")
        want = patch.get("required_value")
        got = after_vals.get(path)
        if path and values_equal(got, want):
            applied_ids.append(str(patch.get("patch_id") or path))
            value_hits += 1

    patched_paths = {str(item.get("path") or "") for item in patches}
    other_value_changed = False
    for path, got in after_vals.items():
        if path in patched_paths or path == "spec_version":
            continue
        if path in before_vals and not values_equal(got, before_vals[path]):
            other_value_changed = True

    version_after = after_vals.get("spec_version")
    version_before = before_vals.get("spec_version")
    version_only = (
        value_hits == 0
        and version_after != version_before
        and str(version_after) == "v2"
    )
    all_applied = value_hits == len(patches) and not extra_names and not other_value_changed

    if extra_names and value_hits == len(patches):
        reason = "unregistered_change"
    elif extra_names and value_hits < len(patches):
        reason = "wrong_location_modified"
    elif other_value_changed and value_hits < len(patches):
        reason = "wrong_location_modified"
    elif value_hits == 0 and any(
        path in after_vals
        and not values_equal(after_vals.get(path), before_vals.get(path))
        and not values_equal(after_vals.get(path), patch.get("required_value"))
        for patch in patches
        for path in [str(patch.get("path") or "")]
        if path
    ):
        reason = "wrong_value_applied"
    elif version_only:
        reason = "version_only_updated"
    elif value_hits == 0 and claimed_ids:
        reason = "patch_acknowledged_not_applied"
    elif value_hits == 0 and after_hash == before_hash:
        reason = "patch_not_read"
    elif value_hits == 0:
        reason = "patch_not_read"
    elif extra_names:
        reason = "unregistered_change"
    elif other_value_changed:
        reason = "wrong_location_modified"
    else:
        reason = "ok"

    return {
        "ok": all_applied,
        "reason": reason,
        "applied": value_hits == len(patches),
        "applied_ids": applied_ids,
        "claim": claim,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "after_values": after_vals,
        "nack": _CLAIM_REASON,
    }
