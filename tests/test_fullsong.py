"""Full songs only when YouTube lets them play on other sites (reach/fullsong.py).  python -m unittest discover -s tests"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reach import fullsong as F  # noqa: E402


class FullSongTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.old_cache, self.old_api = F.CACHE, F._api
        F.CACHE = Path(self.tmp.name) / "yt.json"

    def tearDown(self):
        F.CACHE, F._api = self.old_cache, self.old_api; self.tmp.cleanup()

    def fake(self, status):
        def api(path, **p):
            if path == "search":
                return {"items": [{"id": {"videoId": v}, "snippet": {"title": f"Myke Towers - Te Imagino ({v})", "channelTitle": "Myke Towers"}} for v in status]}
            if path == "videos":
                return {"items": [{"id": v, "status": {"embeddable": s != "noembed", "privacyStatus": "public"},
                                   "contentDetails": {"regionRestriction": {"blocked": ["US"]} if s == "blocked" else {},
                                                      "contentRating": {"ytRating": "ytAgeRestricted"} if s == "age" else {}}} for v, s in status.items() if v in p["id"].split(",")]}
        return api

    def test_only_playable_videos(self):
        F._api = self.fake({"vidNOEMBED1": "noembed", "vidBLOCKED1": "blocked", "vidAGE00001": "age", "vidGOOD0001": "ok"})
        self.assertEqual(F.find("Myke Towers", "Te Imagino")["id"], "vidGOOD0001")

    def test_none_playable_means_preview(self):
        F._api = self.fake({"vidNOEMBED1": "noembed", "vidBLOCKED1": "blocked"})
        self.assertIsNone(F.find("Myke Towers", "Te Imagino"))

    def test_reported_video_is_never_offered_again(self):
        F._api = self.fake({"vidGOOD0001": "ok", "vidGOOD0002": "ok"})
        first = F.find("Myke Towers", "Te Imagino")["id"]
        F.report_bad(first)
        self.assertNotEqual(F.find("Myke Towers", "Te Imagino")["id"], first)


if __name__ == "__main__":
    unittest.main()
