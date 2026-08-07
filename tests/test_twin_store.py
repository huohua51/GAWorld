import os
import tempfile
import unittest

from gaworld.twin import store


def _report(report_id, ts, action_tag="commute"):
    return {
        "report_id": report_id,
        "ts": ts,
        "tz_offset": 480,
        "loc": {"lat": 30.27, "lng": 120.15, "acc_m": 12, "source": "gps"},
        "grid": {"x": 0.0, "y": 0.0},
        "node_id": "home",
        "out_of_map": False,
        "action_tag": action_tag,
        "note": "",
    }


class TestTwinStore(unittest.TestCase):
    def test_append_then_load_returns_the_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = store.append_reports(7, [_report("a", 1000)], root=tmpdir)
            self.assertEqual(result["accepted"], 1)
            self.assertEqual(result["duplicates"], 0)
            loaded = store.load_reports(7, root=tmpdir)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["report_id"], "a")

    def test_duplicate_report_id_appends_only_once(self):
        # The phone resubmits its offline queue after a flaky upload; the same
        # report_id must not produce a second line.
        with tempfile.TemporaryDirectory() as tmpdir:
            store.append_reports(7, [_report("a", 1000)], root=tmpdir)
            result = store.append_reports(7, [_report("a", 1000)], root=tmpdir)
            self.assertEqual(result["accepted"], 0)
            self.assertEqual(result["duplicates"], 1)
            self.assertEqual(len(store.load_reports(7, root=tmpdir)), 1)

    def test_batch_dedupes_within_itself(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            batch = [_report("a", 1000), _report("a", 1000), _report("b", 1001)]
            result = store.append_reports(7, batch, root=tmpdir)
            self.assertEqual(result["accepted"], 2)
            self.assertEqual(result["duplicates"], 1)

    def test_snapshot_holds_the_latest_report_by_timestamp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Deliberately out of order: an offline flush can arrive late.
            store.append_reports(7, [_report("b", 2000, "work")], root=tmpdir)
            store.append_reports(7, [_report("a", 1000, "sleep")], root=tmpdir)
            snapshot = store.read_snapshot(7, root=tmpdir)
            self.assertEqual(snapshot["action_tag"], "work")
            self.assertEqual(snapshot["ts"], 2000)

    def test_agents_are_isolated_from_each_other(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store.append_reports(7, [_report("a", 1000)], root=tmpdir)
            self.assertEqual(len(store.load_reports(8, root=tmpdir)), 0)
            self.assertIsNone(store.read_snapshot(8, root=tmpdir))

    def test_load_reports_can_filter_by_timestamp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store.append_reports(
                7, [_report("a", 1000), _report("b", 2000)], root=tmpdir
            )
            recent = store.load_reports(7, root=tmpdir, since_ts=1500)
            self.assertEqual([r["report_id"] for r in recent], ["b"])

    def test_is_fresh_uses_the_ttl(self):
        snapshot = _report("a", 1000)
        self.assertTrue(store.is_fresh(snapshot, now_ts=1000 + 29 * 60, ttl_minutes=30))
        self.assertFalse(store.is_fresh(snapshot, now_ts=1000 + 31 * 60, ttl_minutes=30))
        self.assertFalse(store.is_fresh(None, now_ts=1000, ttl_minutes=30))

    def test_corrupt_line_does_not_break_loading(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store.append_reports(7, [_report("a", 1000)], root=tmpdir)
            path = os.path.join(store.agent_dir(7, root=tmpdir), "reports.jsonl")
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("{not json\n")
            loaded = store.load_reports(7, root=tmpdir)
            self.assertEqual(len(loaded), 1)


if __name__ == "__main__":
    unittest.main()
