"""'With others' on the start page: people with a name and a favourite typed by name.  python -m unittest discover -s tests"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("REACH_OFFLINE", "1"); os.environ.setdefault("REACH_LLM", "off")

from server import app as A  # noqa: E402
from reach.group import GroupAgent  # noqa: E402


class Stub:
    offline = False
    def __init__(self): self.asked = []
    def resolve(self, q, t="artist"):
        self.asked.append((q, t)); return {"entity_id": "E-" + q.lower(), "name": q.title()}


class GroupPeopleTest(unittest.TestCase):
    def test_a_favourite_typed_by_name_is_looked_up_in_qloo(self):
        g = GroupAgent.__new__(GroupAgent); g.client = Stub()
        prof = g._member_profile({"name": "Maman", "favorites": [{"name": "googoosh", "type": "artist", "entity_id": None}]}, {"age": 60, "city": "San Jose"})
        self.assertEqual(g.client.asked, [("googoosh", "artist")])
        self.assertEqual(prof["favorites"][0]["entity_id"], "E-googoosh")
        self.assertEqual(prof["city"], "San Jose")

    def test_a_group_request_reaches_the_council(self):
        r = A.COUNCIL.compose_once(A.persona("lena"), {"text": "a session for all of us", "lang": "en",
                                                         "group": [{"name": "Maman", "favorites": [{"name": "Googoosh", "type": "artist", "entity_id": None}], "needs": {}}]})
        self.assertFalse(r.get("error"), r.get("error"))
        self.assertTrue(r["session"].get("group"))

    def test_a_group_can_take_a_journey(self):
        r = A.COUNCIL.compose_once(A.persona("lena"), {"text": "", "lang": "en", "goal": "calm", "then_goal": "sleep",
                                                         "group": [{"name": "Maman", "favorites": [{"name": "Googoosh", "type": "artist", "entity_id": None}], "needs": {}}]})
        self.assertEqual(r["session"]["journey"]["protocols"], ["calm_iso", "sleep_descent"])
        self.assertTrue(r["session"].get("group"))


if __name__ == "__main__":
    unittest.main()
