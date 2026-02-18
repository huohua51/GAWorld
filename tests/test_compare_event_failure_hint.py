import os
import tempfile
import unittest

import generative_city_sim as sim


class TestCompareEventFailureHint(unittest.TestCase):
    def test_extract_failure_hint_with_ollama_refused(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "run.log")
            text = "\n".join(
                [
                    "Traceback (most recent call last):",
                    "requests.exceptions.ConnectionError: HTTPConnectionPool(host='localhost', port=11434): Max retries exceeded",
                    "Connection refused",
                ]
            )
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            hint = sim._extract_run_failure_hint(path)
            self.assertIn("localhost", hint)
            self.assertIn("建议", hint)


if __name__ == "__main__":
    unittest.main()
