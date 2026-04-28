"""Tests for the concurrency primitives in :mod:`gaworld.core.runner`."""

from __future__ import annotations

import threading
import time
import unittest

from gaworld.core.runner import parallel_map, resolve_max_workers


class TestParallelMap(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual([], parallel_map(lambda x: x, []))
        self.assertEqual([], parallel_map(lambda x: x, [], max_workers=4))

    def test_serial_preserves_order(self):
        out = parallel_map(lambda x: x * 2, [3, 1, 4, 1, 5, 9, 2, 6])
        self.assertEqual([6, 2, 8, 2, 10, 18, 4, 12], out)

    def test_parallel_preserves_order(self):
        # Use a sleep that varies inversely with the input so larger
        # inputs would finish first under FIFO; result order must
        # still reflect input order.
        def slow(x):
            time.sleep(0.02 * (5 - x % 5))
            return x

        out = parallel_map(slow, [0, 1, 2, 3, 4, 5, 6, 7], max_workers=4, label="t")
        self.assertEqual([0, 1, 2, 3, 4, 5, 6, 7], out)

    def test_parallel_actually_parallel(self):
        # If we run N items each sleeping 0.05s with 4 workers, total
        # wall time should be well below N * 0.05.
        def slow(_):
            time.sleep(0.05)
            return 1

        items = list(range(8))
        start = time.monotonic()
        parallel_map(slow, items, max_workers=4)
        elapsed = time.monotonic() - start
        # 8 items / 4 workers = 2 batches × 0.05s ≈ 0.10s; allow plenty of slack.
        self.assertLess(elapsed, 0.3)

    def test_serial_falls_back_when_workers_le_1(self):
        thread_ids: set[int] = set()

        def collector(x):
            thread_ids.add(threading.get_ident())
            return x

        parallel_map(collector, list(range(4)), max_workers=1)
        self.assertEqual(1, len(thread_ids))
        # caller's thread executed everything
        self.assertIn(threading.get_ident(), thread_ids)

    def test_exception_propagates(self):
        def boom(x):
            if x == 3:
                raise RuntimeError("kaboom")
            return x

        with self.assertRaises(RuntimeError):
            parallel_map(boom, [1, 2, 3, 4], max_workers=2)


class TestResolveMaxWorkers(unittest.TestCase):
    def test_missing_block_returns_default(self):
        self.assertEqual(1, resolve_max_workers({}, key="day_routine_workers"))
        self.assertEqual(2, resolve_max_workers({}, key="day_routine_workers", default=2))

    def test_disabled_overrides_to_one(self):
        cfg = {"concurrency": {"enabled": False, "day_routine_workers": 8}}
        self.assertEqual(1, resolve_max_workers(cfg, key="day_routine_workers"))

    def test_reads_value(self):
        cfg = {"concurrency": {"enabled": True, "day_routine_workers": 4}}
        self.assertEqual(4, resolve_max_workers(cfg, key="day_routine_workers"))

    def test_invalid_value_falls_back(self):
        cfg = {"concurrency": {"enabled": True, "day_routine_workers": "abc"}}
        self.assertEqual(1, resolve_max_workers(cfg, key="day_routine_workers"))

    def test_negative_clamped_to_one(self):
        cfg = {"concurrency": {"enabled": True, "day_routine_workers": -3}}
        self.assertEqual(1, resolve_max_workers(cfg, key="day_routine_workers"))


if __name__ == "__main__":
    unittest.main()
