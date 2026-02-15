import os
import tempfile
import unittest

import pandas as pd

import generative_city_sim as sim


class TestCompareEventMetrics(unittest.TestCase):
    def test_compose_rows_from_state_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_csv = os.path.join(tmpdir, "base.csv")
            event_csv = os.path.join(tmpdir, "event.csv")
            base_df = pd.DataFrame(
                [
                    {"agent_id": 1, "step": 0, "metric": "stress", "value": 0.4},
                    {"agent_id": 1, "step": 1, "metric": "stress", "value": 0.5},
                    {"agent_id": 1, "step": 0, "metric": "emotion", "value": 0.6},
                    {"agent_id": 1, "step": 1, "metric": "emotion", "value": 0.5},
                ]
            )
            event_df = pd.DataFrame(
                [
                    {"agent_id": 1, "step": 0, "metric": "stress", "value": 0.45},
                    {"agent_id": 1, "step": 1, "metric": "stress", "value": 0.7},
                    {"agent_id": 1, "step": 0, "metric": "emotion", "value": 0.55},
                    {"agent_id": 1, "step": 1, "metric": "emotion", "value": 0.4},
                ]
            )
            base_df.to_csv(base_csv, index=False)
            event_df.to_csv(event_csv, index=False)
            rows = sim._compose_comparison_rows(base_csv, event_csv)
            by_metric = {row["metric"]: row for row in rows}
            self.assertIn("stress", by_metric)
            self.assertAlmostEqual(0.2, by_metric["stress"]["delta_final"], places=6)
            self.assertAlmostEqual(-0.1, by_metric["emotion"]["delta_final"], places=6)


if __name__ == "__main__":
    unittest.main()
