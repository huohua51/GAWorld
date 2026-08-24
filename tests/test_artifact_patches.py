"""Executor patch verification tests."""

from __future__ import annotations

import unittest

from gaworld.work.artifact_patches import verify_applied

_SPECS = [
    {"symbol": "SPEC_VERSION", "criterion_path": "spec_version", "parse": "str"},
    {"symbol": "RATE", "criterion_path": "min_return_rate", "parse": "float"},
]
_PATCHES = [
    {
        "patch_id": "patch-01",
        "path": "min_return_rate",
        "observed_value": 0.3,
        "required_value": 0.5,
        "artifact_hash_before": "sha256:dummy",
    }
]
_BEFORE = 'SPEC_VERSION = "v1"\nRATE = 0.3\n'


class TestArtifactPatches(unittest.TestCase):
    def test_value_applied(self):
        after = 'SPEC_VERSION = "v2"\nRATE = 0.5\nAPPLIED_PATCH_IDS = ["patch-01"]\n'
        out = verify_applied(before=_BEFORE, after=after, patches=_PATCHES, specs=_SPECS)
        self.assertTrue(out["applied"])
        self.assertEqual("ok", out["reason"])

    def test_version_only_is_rejected(self):
        after = 'SPEC_VERSION = "v2"\nRATE = 0.3\n'
        out = verify_applied(before=_BEFORE, after=after, patches=_PATCHES, specs=_SPECS)
        self.assertFalse(out["applied"])
        self.assertEqual("version_only_updated", out["reason"])

    def test_acknowledged_not_applied(self):
        after = 'SPEC_VERSION = "v1"\nRATE = 0.3\nAPPLIED_PATCH_IDS = ["patch-01"]\n'
        out = verify_applied(before=_BEFORE, after=after, patches=_PATCHES, specs=_SPECS)
        self.assertEqual("patch_acknowledged_not_applied", out["reason"])

    def test_wrong_value(self):
        after = 'SPEC_VERSION = "v2"\nRATE = 0.4\n'
        out = verify_applied(before=_BEFORE, after=after, patches=_PATCHES, specs=_SPECS)
        self.assertEqual("wrong_value_applied", out["reason"])

    def test_unregistered_change(self):
        after = 'SPEC_VERSION = "v2"\nRATE = 0.5\nRETURN_RATE = 0.5\n'
        out = verify_applied(before=_BEFORE, after=after, patches=_PATCHES, specs=_SPECS)
        self.assertTrue(out["applied"])
        self.assertEqual("unregistered_change", out["reason"])

    def test_string_claim_is_acknowledged(self):
        after = 'SPEC_VERSION = "v1"\nRATE = 0.3\nAPPLIED_PATCH_IDS = "patch-01"\n'
        out = verify_applied(before=_BEFORE, after=after, patches=_PATCHES, specs=_SPECS)
        self.assertEqual("patch_acknowledged_not_applied", out["reason"])

    def test_required_value_on_wrong_symbol(self):
        after = 'SPEC_VERSION = "v1"\nRATE = 0.3\nTHRESHOLD = 0.5\n'
        out = verify_applied(before=_BEFORE, after=after, patches=_PATCHES, specs=_SPECS)
        self.assertEqual("wrong_location_modified", out["reason"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
