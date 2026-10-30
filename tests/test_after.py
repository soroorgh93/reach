"""After the music (reach/after.py), offline with a stand-in Qloo client.  python -m unittest discover -s tests"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reach import after as A  # noqa: E402

FAV = [{"name": "Hayedeh", "type": "artist", "entity_id": "11111111-aaaa"}, {"name": "Dariush", "type": "artist", "entity_id": "22222222-bbbb"}]


def place(name, cats, aff, fav="11111111", lat=37.33, lon=-121.89):
    return {"name": name, "entity_id": name.lower().replace(" ", "-"), "query": {"affinity": aff, "explainability": {"signal.interests.entities": [{"entity_id": fav, "score": 0.5}]}},
            "tags": [{"tag_id": "urn:tag:category:place:" + c} for c in cats], "properties": {"geocode": {"latitude": lat, "longitude": lon}, "address": "1 St"}}


class FakeQloo:
    offline = False

    def __init__(self, places=None, food=None, books=None):
        self.places, self.food, self.books = places or [], food or [], books or []
        self.seen: list[dict] = []

    def get(self, path, params, label=""):
        self.seen.append(dict(params, _label=label))
        rows = self.food if ".food." in label else self.places
        tags = params.get("filter.tags", "")
        if ".food." in label and "persian_restaurant" not in tags and "restaurant" not in tags:
            rows = []
        return {"status": 200, "source": "live", "data": {"query": {"localities": {"filter": {"latitude": 37.3382, "longitude": -121.8863}}}, "results": {"entities": [dict(r) for r in rows]}}}

    def insights(self, ftype, entities=None, take=10, label="", **kw):
        self.seen.append({"filter.type": ftype, "_label": label, "signal.interests.entities": entities})
        return [dict(b) for b in self.books]


class AfterTest(unittest.TestCase):
    def setUp(self):
        A._CACHE.clear()

    def prof(self, **kw):
        p = {"id": "t", "city": "San Jose", "age": 30, "favorites": FAV}
        p.update(kw)
        return p

    def test_never_suggests_a_bar(self):
        q = FakeQloo(places=[place("Quiet Park", ["park"], 0.8), place("Loud Cocktail Bar", ["cocktail_bar"], 0.99), place("Night Club X", ["night_club"], 0.97)])
        out = A.after(q, self.prof(), "calm")
        names = [p["name"] for p in out["places"]]
        self.assertEqual(names, ["Quiet Park"])

    def test_child_gets_no_live_music(self):
        q = FakeQloo(places=[place("Club Stage", ["live_music_venue"], 0.95), place("Kids Library", ["library"], 0.7)])
        out = A.after(q, self.prof(age=9), "mood")
        self.assertNotIn("Club Stage", [p["name"] for p in out["places"]])
        sent_tags = next(c for c in q.seen if ".after.places." in c.get("_label", ""))["filter.tags"]
        self.assertNotIn("live_music_venue", sent_tags)

    def test_only_ids_tags_and_city_are_sent(self):
        q = FakeQloo(places=[place("Quiet Park", ["park"], 0.8)])
        A.after(q, self.prof(), "sleep", local_hour=23)
        allowed = {"filter.type", "take", "feature.explainability", "signal.interests.entities", "filter.location.query", "filter.tags", "operator.filter.tags", "_label"}
        for call in q.seen:
            self.assertTrue(set(call) <= allowed, set(call) - allowed)
        self.assertEqual(q.seen[0]["filter.location.query"], "San Jose")

    def test_sleep_is_for_tomorrow(self):
        q = FakeQloo(places=[place("Quiet Park", ["park"], 0.8)])
        self.assertEqual(A.after(q, self.prof(), "sleep", local_hour=14)["when"], "tomorrow")
        A._CACHE.clear()
        self.assertEqual(A.after(q, self.prof(), "calm", local_hour=23)["when"], "tomorrow")
        A._CACHE.clear()
        self.assertEqual(A.after(q, self.prof(), "calm", local_hour=10)["when"], "today")

    def test_no_city_means_no_places_but_books(self):
        q = FakeQloo(places=[place("Quiet Park", ["park"], 0.8)], books=[{"name": "The Blind Owl", "entity_id": "b1", "query": {"affinity": 0.9}}])
        out = A.after(q, self.prof(city=""), "calm")
        self.assertEqual(out["places"], [])
        self.assertEqual([b["name"] for b in out["read"]], ["The Blind Owl"])
        self.assertIn("no_city", out["notes"])

    def test_distance_from_qloo_centroid(self):
        q = FakeQloo(places=[place("Near Park", ["park"], 0.8, lat=37.3382, lon=-121.8863)])
        out = A.after(q, self.prof(), "calm")
        self.assertEqual(out["places"][0]["km"], 0.0)
        self.assertEqual(out["places"][0]["because"][0]["name"], "Hayedeh")

    def test_bar_is_a_word_not_a_substring(self):
        q = FakeQloo(places=[place("Barefoot Coffee", ["coffee_shop"], 0.9), place("Embarcadero Park", ["park"], 0.8), place("The Wine Bar", ["wine_bar"], 0.95)])
        out = A.after(q, self.prof(), "focus")
        names = [p["name"] for p in out["places"] + out["food"]]
        self.assertIn("Barefoot Coffee", names); self.assertIn("Embarcadero Park", names); self.assertNotIn("The Wine Bar", names)

    def test_no_haunted_house_after_calm(self):
        q = FakeQloo(places=[place("Mystery House", ["museum", "haunted_house"], 0.95), place("Rose Garden", ["park"], 0.8)])
        self.assertEqual([p["name"] for p in A.after(q, self.prof(), "calm")["places"]], ["Rose Garden"])
        A._CACHE.clear()
        self.assertIn("Mystery House", [p["name"] for p in A.after(q, self.prof(), "memory")["places"]])

    def test_tags_given_as_type_and_name(self):
        e = {"name": "X", "tags": [{"id": "urn:tag:category:place:park", "name": "Park"}, {"type": "urn:tag:category:place", "name": "Botanical Garden"}]}
        self.assertEqual(A.suffixes(e), ["park", "botanical_garden"])

    def test_winchester_mystery_house_is_not_calm(self):
        q = FakeQloo(places=[place("Winchester Mystery House", ["museum", "tourist_attraction"], 0.97), place("Cupertino Library", ["library"], 0.8)])
        self.assertEqual([p["name"] for p in A.after(q, self.prof(), "calm")["places"]], ["Cupertino Library"])

    def test_song_spellings(self):
        from reach.previews import same_title
        for a, b in [("Gol-e Yakh", "Gole Yakh"), ("Khiali Nist", "Khiyali Nist"), ("Pol", "Pol (Remastered)"), ("Tannaz", "Tanaz")]:
            self.assertTrue(same_title(a, b), (a, b))
        for a, b in [("Love", "Love Story"), ("Madar", "Mother"), ("Hello", "Goodbye")]:
            self.assertFalse(same_title(a, b), (a, b))

    def test_namesake_artist_with_most_listeners(self):
        from reach import previews as P
        calls = []
        def fake(url, timeout=8.0):
            calls.append(url)
            if "/search/artist" in url:
                return {"data": [{"id": 1, "name": "Dariush", "nb_fan": 120}, {"id": 2, "name": "Dariush", "nb_fan": 250000}, {"id": 3, "name": "Dariush Eghbali", "nb_fan": 9}]}
            if "/artist/2/top" in url:
                return {"data": [{"title": "Ghorbat", "preview": "https://cdn.dzcdn.net/x.mp3", "artist": {"id": 2, "name": "Dariush"}, "album": {}}]}
            if "/artist/1/top" in url:
                return {"data": [{"title": "Troubled child", "preview": "https://cdn.dzcdn.net/y.mp3", "artist": {"id": 1, "name": "Dariush"}, "album": {}}]}
            return {"data": []}
        old = P._get_json; P._get_json = fake; P._cache.clear(); P._acache.clear()
        try:
            self.assertEqual([t["title"] for t in P.previews("Dariush", 4)], ["Ghorbat"])
        finally:
            P._get_json = old; P._cache.clear(); P._acache.clear()

    def test_shared_position_goes_instead_of_the_city(self):
        q = FakeQloo(places=[place("Near Park", ["park"], 0.8, lat=37.3305, lon=-121.8891)])
        out = A.after(q, self.prof(here=[37.33049, -121.88912]), "calm")
        call = q.seen[0]
        self.assertEqual(call.get("filter.location"), "POINT(-121.89 37.33)")
        self.assertNotIn("filter.location.query", call)
        self.assertLess(out["places"][0]["km"], 1.5)                # measured from the person's rounded spot
        self.assertIn("your position, rounded to about 1 km", out["sent"])

    def test_bad_position_is_ignored(self):
        q = FakeQloo(places=[place("Quiet Park", ["park"], 0.8)])
        A.after(q, self.prof(here=["x", 500]), "calm")
        self.assertEqual(q.seen[0].get("filter.location.query"), "San Jose")

    def test_qloo_decides_the_kitchens(self):
        wide = [place("Taqueria Uno", ["mexican_restaurant", "restaurant"], 0.9), place("Mofongo House", ["puerto_rican_restaurant"], 0.85), place("Rose Garden", ["park"], 0.8)]
        q = FakeQloo(places=wide, food=[place("Taqueria Uno", ["mexican_restaurant", "restaurant"], 0.9), place("Mofongo House", ["puerto_rican_restaurant"], 0.85)])
        out = A.after(q, self.prof(), "energy")
        food_call = next(c for c in q.seen if ".after.food." in c.get("_label", ""))
        self.assertIn("mexican_restaurant", food_call["filter.tags"]); self.assertIn("puerto_rican_restaurant", food_call["filter.tags"])
        self.assertEqual({f["kitchen"] for f in out["food"]}, {"mexican", "puerto rican"})
        self.assertEqual([p["name"] for p in out["places"]], ["Rose Garden"])

    def test_up_to_six_of_each(self):
        rows = [place(f"Park {i}", ["park"], 0.9 - i * 0.01) for i in range(9)] + [place(f"Cafe {i}", ["cafe"], 0.8 - i * 0.01) for i in range(9)]
        out = A.after(FakeQloo(places=rows, food=rows), self.prof(), "calm")
        self.assertEqual(len(out["places"]), 6); self.assertEqual(len(out["food"]), 6)

    def test_no_favourites(self):
        out = A.after(FakeQloo(), self.prof(favorites=[]), "calm")
        self.assertFalse(out["ok"]); self.assertEqual(out["reason"], "no_favourites")

    def test_unknown_goal_falls_back_to_calm(self):
        out = A.after(FakeQloo(places=[place("Quiet Park", ["park"], 0.8)]), self.prof(), "rm -rf")
        self.assertEqual(out["goal"], "calm")

    def test_cuisine_words_cover_many_countries(self):
        self.assertGreater(len(A.CUISINE), 90)
        self.assertEqual(A.CUISINE["IR"][0], "persian")


if __name__ == "__main__":
    unittest.main()
