import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import selftest


class SentinelTests(unittest.TestCase):
    def test_certified_suite(self):
        os.environ.setdefault("LLM_URL", "local")
        report = selftest.run()
        failed = [item for item in report["tests"] if not item["ok"]]
        self.assertEqual(failed, [], msg="\n".join(f"{item['name']}: {item['detail']}" for item in failed))
        self.assertTrue(report["ok"])


if __name__ == "__main__":
    unittest.main()
