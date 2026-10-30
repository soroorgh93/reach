"""Two needs in one session (reach/agent.py journey).  python -m unittest discover -s tests"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("REACH_OFFLINE", "1"); os.environ.setdefault("REACH_LLM", "off")

from server import app as A  # noqa: E402


class JourneyTest(unittest.TestCase):
    def test_calm_then_sleep(self):
        r = A.COUNCIL.compose_once(A.persona("lena"), {"text": "calm me, then help me sleep", "goal": "calm", "then_goal": "sleep", "lang": "en"})
        s = r["session"]
        self.assertEqual(s["journey"]["protocols"], ["calm_iso", "sleep_descent"])
        self.assertIn("→", s["protocol_name"])
        starts = [x["start_s"] for x in s["segments"]]
        self.assertEqual(starts, sorted(starts))                       # one continuous timeline
        self.assertEqual(s["segments"][-1]["hz_to"], 2.0)              # it ends where sleep ends
        self.assertLessEqual(s["gain_dbfs"], -20)                     # a child's cap survives the join

    def test_one_need_is_unchanged(self):
        s = A.COUNCIL.compose_once(A.persona("lena"), {"text": "help me sleep", "goal": "sleep", "lang": "en"})["session"]
        self.assertNotIn("journey", s)


if __name__ == "__main__":
    unittest.main()
