"""Offline checks of the council (recorded Qloo fixtures, no network).  python -m unittest discover -s tests"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reach.agent import ReachCouncil, ADJACENT  # noqa: E402
from reach.group import parse_members  # noqa: E402
from reach.ledger import Ledger  # noqa: E402
from reach.mood import detect_goal  # noqa: E402
from reach.qloo import QlooClient  # noqa: E402
from reach.tour import TOUR, tour_for  # noqa: E402


def persona(pid: str) -> dict:
    return next(p for p in json.loads((ROOT / "data" / "personas.json").read_text(encoding="utf-8"))["personas"] if p["id"] == pid)


class GoalDetection(unittest.TestCase):
    def test_the_ask_wins_over_the_state(self):
        self.assertEqual(detect_goal("I'm so tired, need a boost")[0], "energy")
        self.assertEqual(detect_goal("I'm depressed, boost my energy")[0], "energy")

    def test_explicit_sleep_still_wins(self):
        self.assertEqual(detect_goal("tired and can't sleep")[0], "sleep")
        self.assertEqual(detect_goal("I'm tired")[0], "sleep")

    def test_autism_changes_the_envelope(self):
        self.assertEqual(detect_goal("my autistic son is overloaded, he loves techno")[0], "autism_calm")

    def test_every_goal_has_candidates(self):
        for goal, cands in ADJACENT.items():
            self.assertTrue(cands, goal)


class GroupParsing(unittest.TestCase):
    def test_pronouns_are_not_people(self):
        for pid in ("lena", "okafor"):
            members, _ = parse_members(persona(pid).get("sample_request", ""))
            self.assertEqual(members, [], pid)

    def test_friends_and_counts(self):
        members, n = parse_members("I'm with three friends, Sara likes Indian music and Omar wants no vocals")
        self.assertEqual([m["name"] for m in members], ["Sara", "Omar"])
        self.assertEqual(n, 3)
        self.assertEqual(members[1]["needs"], {"vocals": False})


class Council(unittest.TestCase):
    def setUp(self):
        self.client = QlooClient(offline=True)
        self.council = ReachCouncil(self.client)

    def test_energy_protocol_from_text(self):
        r = self.council.compose_once(persona("lena"), {"text": "I'm so tired, need a boost", "lang": "en", "local_hour": 14})
        self.assertIsNone(r.get("error"), r.get("detail"))
        self.assertEqual(r["session"]["protocol_id"], "energize")
        self.assertEqual(r["listener"]["goal"], "energy")
        self.assertLessEqual(max(s["bpm"] for s in r["session"]["segments"]), 84, "child sensory envelope caps tempo")

    def test_deaf_profile_routes_to_visual(self):
        prof = dict(persona("lena")); prof["id"] = "you"; prof["capacities"] = dict(prof.get("capacities", {}), hearing="none")
        r = self.council.compose_once(prof, {"text": "I can't sleep", "lang": "en", "local_hour": 23})
        self.assertIsNone(r.get("error"), r.get("detail"))
        self.assertEqual(r["session"]["protocol_id"], "visual_breath")
        self.assertEqual(r["session"]["entrainment"], "visual")
        self.assertEqual(r["session"]["breathing"]["rate_per_min"], 6)

    def test_ledger_verifies_and_breaks(self):
        r = self.council.compose_once(persona("lena"), {"text": "", "goal": "calm", "lang": "en", "local_hour": 12})
        self.assertIsNone(r.get("error"), r.get("detail"))
        self.assertTrue(Ledger.verify_entries(r["ledger"])["ok"])
        tampered = json.loads(json.dumps(r["ledger"])); tampered[3]["payload"]["tampered"] = True
        self.assertFalse(Ledger.verify_entries(tampered)["ok"])

    def test_no_taste_means_no_session(self):
        prof = {"id": "you", "name": "Nobody", "age": 30, "city": "", "favorites": [], "capacities": {"hearing": "full"}, "consent": {"taste": True}, "targets": [], "flags": [], "sensory": {}}
        r = self.council.compose_once(prof, {"text": "calm me", "lang": "en", "local_hour": 12})
        self.assertEqual(r.get("error"), "qloo_required")


class FavouritesAndCulture(unittest.TestCase):
    """Hayedeh, Dariush, Marzieh (+ Gloria Gaynor): their own songs first, then Persian picks; Turkish neighbours set aside."""
    COUNTRY = {"Hayedeh": "IR", "Dariush": "IR", "Marzieh": "IR", "Gloria Gaynor": "US", "Googoosh": "IR", "Ebi": "IR", "Viguen": "IR",
               "Kalben": "TR", "Mabel Matiz": "TR", "Nilipek.": "TR", "Donna Summer": "US", "Jay Chou": "TW", "Teresa Teng": "TW", "Eason Chan": "HK",
               "JJ Lin": "SG", "BTS": "KR", "IU": "KR", "Utada Hikaru": "JP"}

    def setUp(self):
        from reach import culture, taste
        self.culture, self.taste = culture, taste
        self._orig = culture.places
        LANG = {"IR": "fas", "US": "eng", "TR": "tur", "TW": "zho", "HK": "yue", "SG": "zho", "KR": "kor", "JP": "jpn"}
        culture.places = lambda names, budget_s=0, network=True: {n: ({"cc": self.COUNTRY[n], "country": self.COUNTRY[n], "langs": {LANG[self.COUNTRY[n]]: 1.0}} if n in self.COUNTRY else {}) for n in names}

    def tearDown(self):
        self.culture.places = self._orig

    def _fake(self, rows):
        def insights(ftype, label="", **kw):
            if ftype != "artist":
                return []
            if "culture" in label:
                return [dict(e, _source="test") for e in rows if e["name"] in ("Googoosh", "Viguen")]
            if ".fit" in label:
                return [dict(e, _source="test") for e in rows if e["name"] in ("Kalben", "Mabel Matiz", "Nilipek.")]
            return [dict(e, _source="test") for e in rows]
        c = QlooClient(offline=True); c.insights = insights
        return c

    def test_own_first_then_same_culture(self):
        names = ["Kalben", "Mabel Matiz", "Nilipek.", "Googoosh", "Ebi", "Viguen", "Donna Summer"]
        rows = [{"name": n, "entity_id": f"id-{i}", "query": {"affinity": 0.95 - i * 0.02}, "tags": []} for i, n in enumerate(names)]
        favs = [{"name": n, "type": "artist", "entity_id": f"fav-{i}"} for i, n in enumerate(["Hayedeh", "Dariush", "Marzieh", "Gloria Gaynor"])]
        prof = {"id": "you", "name": "Susan", "age": 40, "favorites": favs}
        agent = self.taste.TasteAgent(self._fake(rows))
        T = agent.read(prof, {"id": "calm_iso", "carrier": {"tags_prefer": ["acoustic", "folk"]}}, {})
        self.assertTrue(T["ok"])
        self.assertEqual([c["name"] for c in T["favourites_first"]], ["Hayedeh", "Dariush", "Marzieh", "Gloria Gaynor"])
        recs = [c["name"] for c in T["carrier"]]
        self.assertTrue(recs[0] in ("Googoosh", "Ebi", "Viguen"), recs)
        for turk in ("Kalben", "Mabel Matiz", "Nilipek."):
            self.assertNotIn(turk, recs)
        self.assertIn("Kalben", [a["name"] for a in T["set_aside"]])
        self.assertEqual(T["lens"]["dominant"], "lang:fas")

    def test_the_same_works_for_any_culture(self):
        """Chinese favourites: Mandopop picks, Korean and Japanese neighbours set aside. Nothing is listed by hand."""
        names = ["BTS", "Jay Chou", "IU", "Utada Hikaru", "Teresa Teng"]
        rows = [{"name": n, "entity_id": f"c-{i}", "query": {"affinity": 0.95 - i * 0.02}, "tags": []} for i, n in enumerate(names)]
        favs = [{"name": n, "type": "artist", "entity_id": f"f-{i}"} for i, n in enumerate(["Eason Chan", "JJ Lin", "Teresa Teng"])]
        favs = [{"name": "Jay Chou", "type": "artist", "entity_id": "f-9"}, {"name": "JJ Lin", "type": "artist", "entity_id": "f-8"}]
        T = self.taste.TasteAgent(self._fake(rows)).read({"id": "you", "favorites": favs}, {"id": "calm_iso", "carrier": {}}, {})
        recs = [c["name"] for c in T["carrier"]]
        self.assertIn("Teresa Teng", recs)
        for other in ("BTS", "IU", "Utada Hikaru"):
            self.assertNotIn(other, recs)

    def test_mixed_taste_gets_mixed_slots(self):
        names = ["Kalben", "Googoosh", "Ebi", "Viguen", "Donna Summer"]
        rows = [{"name": n, "entity_id": f"m-{i}", "query": {"affinity": 0.9 - i * 0.01}, "tags": []} for i, n in enumerate(names)]
        favs = [{"name": n, "type": "artist", "entity_id": f"fav-{i}"} for i, n in enumerate(["Hayedeh", "Dariush", "Marzieh", "Gloria Gaynor"])]
        T = self.taste.TasteAgent(self._fake(rows)).read({"id": "you", "favorites": favs}, {"id": "calm_iso", "carrier": {}}, {})
        recs = [c["name"] for c in T["carrier"]]
        self.assertIn("Donna Summer", recs, "a quarter of the favourites are American, so an American pick has a slot")
        self.assertNotIn("Kalben", recs)

    def test_skipped_artists_drop_out(self):
        names = ["Googoosh", "Ebi"]
        rows = [{"name": n, "entity_id": f"s-{i}", "query": {"affinity": 0.9}, "tags": []} for i, n in enumerate(names)]
        favs = [{"name": "Hayedeh", "type": "artist", "entity_id": "fav-0"}]
        T = self.taste.TasteAgent(self._fake(rows)).read({"id": "you", "favorites": favs}, {"id": "calm_iso", "carrier": {}}, {"fb": {"googoosh": -0.8}})
        self.assertEqual([c["name"] for c in T["carrier"]], ["Ebi"])

    def test_a_pinned_artist_leads(self):
        rows = [{"name": "Googoosh", "entity_id": "g", "query": {"affinity": 0.9}, "tags": []}]
        favs = [{"name": n, "type": "artist", "entity_id": f"fav-{i}"} for i, n in enumerate(["Hayedeh", "Dariush"])]
        T = self.taste.TasteAgent(self._fake(rows)).read({"id": "you", "favorites": favs}, {"id": "calm_iso", "carrier": {}}, {"pin": ["Dariush"]})
        self.assertEqual(T["favourites_first"][0]["name"], "Dariush")
        self.assertTrue(T["favourites_first"][0]["pinned"])


class CarefulWithNeeds(unittest.TestCase):
    def test_lively_favourites_and_sleep_get_calm_instrumental(self):
        from reach import agent as A
        from reach.dialogue import session_reply
        council = ReachCouncil(QlooClient(offline=True))
        orig = A.TasteAgent.read
        def lively(self, profile, protocol, memory=None):
            T = orig(self, profile, protocol, memory); T = dict(T); T["texture_tags"] = ["techno", "dance"]; T["tempo_bias"] = 0.3; return T
        A.TasteAgent.read = lively
        try:
            r = council.compose_once(persona("lena"), {"text": "help me sleep", "lang": "en", "local_hour": 23})
        finally:
            A.TasteAgent.read = orig
        self.assertIsNone(r.get("error"), r.get("detail"))
        self.assertTrue(r["session"].get("calm_carrier"))
        self.assertIn("calm instrumental", r["reply"])


class Conversation(unittest.TestCase):
    CTX = {"lang": "en", "favourites": ["Hayedeh", "Dariush", "Marzieh"], "carrier": ["Kalben", "Googoosh"], "src": "artists",
           "now": {"artist": "Kalben", "own": False, "because": "Hayedeh", "culture": "Turkey"}}

    def setUp(self):
        import os
        os.environ["REACH_LLM"] = "off"
        from reach.dialogue import turn
        self.turn = turn

    def test_i_said_hayedeh(self):
        r = self.turn("but I said hayedeh why another singer?", self.CTX)
        self.assertEqual(r["act"], "play"); self.assertEqual(r["artists"], ["Hayedeh"])
        self.assertIn("Kalben", r["reply"]); self.assertNotIn("Same plan", r["reply"])

    def test_why_another_singer_brings_back_favourites(self):
        r = self.turn("why another singer?", self.CTX)
        self.assertEqual(r["act"], "play"); self.assertEqual(r["artists"], ["Hayedeh", "Dariush", "Marzieh"])

    def test_persian_script_names(self):
        r = self.turn("فقط داریوش", dict(self.CTX, lang="fa"))
        self.assertEqual((r["act"], r["artists"], r["only"]), ("play", ["Dariush"], True))

    def test_negation_and_whole_words(self):
        t = self.turn
        self.assertEqual(t("why is there no Dariush?", self.CTX)["artists"], ["Dariush"])
        r = t("I don't want Kalben, play Dariush", self.CTX); self.assertEqual((r["act"], r["artists"], r["avoid"]), ("play", ["Dariush"], ["Kalben"]))
        self.assertEqual(t("هایده نه", dict(self.CTX, lang="fa"))["act"], "avoid")
        self.assertEqual(t("música para dormir", dict(self.CTX, lang="es"))["act"], "compose")
        self.assertEqual(t("آهنگ بسیار آرام", dict(self.CTX, lang="fa"))["act"], "compose")
        self.assertEqual(t("play some jazz", self.CTX)["act"], "compose")
        self.assertEqual(t("stop playing Kalben", self.CTX)["act"], "avoid")
        self.assertEqual(t("我想听周杰伦", dict(self.CTX, lang="zh", favourites=["周杰伦"]))["artists"], ["周杰伦"])

    def test_needs_go_to_the_council_and_questions_do_not(self):
        self.assertEqual(self.turn("I'm sleepy, help me sleep", self.CTX)["act"], "compose")
        self.assertEqual(self.turn("is it safe?", self.CTX)["act"], "answer")
        self.assertEqual(self.turn("podcasts about history", self.CTX)["src"], "podcast")
        self.assertEqual(self.turn("not this one", self.CTX)["act"], "avoid")


class WorldTour(unittest.TestCase):
    def test_stops_have_coordinates_and_a_local_line(self):
        self.assertGreaterEqual(len(TOUR), 10)
        for s in TOUR:
            self.assertTrue(-90 <= s["lat"] <= 90 and -180 <= s["lon"] <= 180, s["city"])
            self.assertTrue(s["local"] and s["line"] and s["genre"], s["city"])

    def test_offline_tour_degrades_cleanly(self):
        out = tour_for(QlooClient(offline=True), TOUR[0])
        self.assertEqual(out["stop"]["city"], "Rome")
        self.assertIsInstance(out["tracks"], list)


if __name__ == "__main__":
    unittest.main()
