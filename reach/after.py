"""After the music: one gentle next step for the rest of the day, from the same taste graph.

The session ends; what helps next is usually not more audio. A quiet walk after a stress session,
a library after a focus session, the food of the songs after a memory session. Reach asks Qloo for
places near the person's own city that people with the same favourites love, filtered to the kind
of place that suits what the session was for, and for a book in the same taste.

What is sent to Qloo: the favourites' entity ids, place category tags and the person's city. Never
their words, face, voice or mood (the goal only chooses which category tags are asked for).

Live-API facts this follows (probes by other entrants, 2026-10-16, and Qloo's docs):
  * only urn:tag:category:place:* works reliably as a venue filter; a list of tags is a union, so
    every result is re-checked against its own tags;
  * filter.location.query takes a city or neighbourhood and resolves a centroid;
  * feature.explainability says how much each favourite moved each place.
"""
from __future__ import annotations

import math
import time
import urllib.parse
from typing import Any

from .qloo import QlooClient, QlooError, ParamRefused
from .taste import favourite_ids

C = "urn:tag:category:place:"

# what kind of place suits the end of each session (category ids verified on the live API)
PLAN: dict[str, dict[str, Any]] = {
    "sleep":       {"places": ["park", "botanical_garden", "book_store", "library"], "when": "tomorrow", "food": "light"},
    "calm":        {"places": ["park", "botanical_garden", "museum", "library", "book_store"], "when": "today", "food": "slow"},
    "autism_calm": {"places": ["park", "library", "museum", "botanical_garden"], "when": "today", "food": "quiet"},
    "focus":       {"places": ["library", "coffee_shop", "book_store", "cafe"], "when": "today", "food": "light"},
    "energy":      {"places": ["park", "rock_climbing_gym", "dance_school", "yoga_studio"], "when": "today", "food": "fresh"},
    "mood":        {"places": ["park", "museum", "record_store", "live_music_venue", "cafe"], "when": "today", "food": "joy"},
    "memory":      {"places": ["museum", "cultural_center", "record_store", "park", "book_store"], "when": "today", "food": "home"},
}
# never suggested after a wellbeing session: places built around drinking, gambling or the night
AVOID = ("bar", "pub", "brewery", "brewpub", "night_club", "nightclub", "cocktail", "wine_bar", "beer", "lounge", "casino", "hookah", "strip", "liquor", "smoke", "vape", "cannabis")
CHILD_AVOID = ("live_music_venue", "jazz_club", "dance_school")
# not after a session meant to bring someone down: fright, thrill and noise
CALM_AVOID = ("haunted", "horror", "ghost", "escape_room", "amusement_park", "theme_park", "water_park", "arcade", "go_kart", "laser_tag", "shooting", "paintball", "stadium", "nightlife",
              "mystery", "fright", "scream", "zombie", "terror", "dungeon", "paranormal")       # also read in the place's own name (Winchester Mystery House)
CALM_GOALS = ("sleep", "calm", "autism_calm", "focus")

# the food of the songs: a country's kitchen, by the words Qloo's place categories use
CUISINE: dict[str, list[str]] = {
    "IR": ["persian", "iranian"], "AF": ["afghan", "persian"], "TJ": ["persian"], "TR": ["turkish"], "AZ": ["azerbaijani", "turkish"], "AM": ["armenian"],
    "LB": ["lebanese"], "SY": ["syrian", "lebanese"], "EG": ["egyptian"], "MA": ["moroccan"], "DZ": ["algerian", "moroccan"], "TN": ["tunisian"], "IQ": ["iraqi", "middle_eastern"],
    "SA": ["middle_eastern"], "AE": ["middle_eastern"], "IL": ["israeli", "middle_eastern"], "JO": ["middle_eastern"], "PS": ["middle_eastern"], "KW": ["middle_eastern"],
    "IN": ["indian"], "PK": ["pakistani", "indian"], "BD": ["bangladeshi", "indian"], "LK": ["sri_lankan"], "NP": ["nepalese"],
    "CN": ["chinese"], "TW": ["taiwanese", "chinese"], "HK": ["cantonese", "chinese"], "JP": ["japanese"], "KR": ["korean"], "VN": ["vietnamese"], "TH": ["thai"],
    "PH": ["filipino"], "ID": ["indonesian"], "MY": ["malaysian"], "SG": ["singaporean", "malaysian"], "MM": ["burmese"], "KH": ["cambodian"], "MN": ["mongolian"],
    "MX": ["mexican"], "CO": ["colombian", "latin_american"], "VE": ["venezuelan", "latin_american"], "PE": ["peruvian"], "AR": ["argentinian", "steakhouse"], "CL": ["chilean"],
    "BR": ["brazilian"], "CU": ["cuban"], "PR": ["puerto_rican", "caribbean"], "DO": ["dominican", "caribbean"], "JM": ["jamaican", "caribbean"], "HT": ["haitian", "caribbean"],
    "SV": ["salvadoran"], "GT": ["guatemalan"], "EC": ["ecuadorian"], "BO": ["bolivian"], "UY": ["uruguayan"], "PA": ["latin_american"],
    "ES": ["spanish", "tapas"], "PT": ["portuguese"], "FR": ["french"], "IT": ["italian"], "GR": ["greek"], "DE": ["german"], "AT": ["austrian", "german"], "CH": ["swiss"],
    "GB": ["british"], "IE": ["irish"], "BE": ["belgian"], "NL": ["dutch"], "SE": ["scandinavian"], "NO": ["scandinavian"], "DK": ["scandinavian"], "FI": ["scandinavian"], "IS": ["scandinavian"],
    "PL": ["polish"], "RU": ["russian"], "UA": ["ukrainian"], "GE": ["georgian"], "HU": ["hungarian"], "CZ": ["czech"], "RO": ["romanian"], "RS": ["balkan"], "HR": ["balkan"], "BA": ["balkan"], "AL": ["balkan"], "BG": ["bulgarian"],
    "NG": ["nigerian", "african"], "GH": ["ghanaian", "african"], "SN": ["senegalese", "african"], "ET": ["ethiopian"], "ER": ["eritrean", "ethiopian"], "KE": ["kenyan", "african"],
    "ZA": ["south_african", "african"], "CM": ["african"], "CI": ["african"], "ML": ["african"], "CD": ["african"], "SO": ["somali", "african"],
    "US": ["american"], "CA": ["canadian", "american"], "AU": ["australian"], "NZ": ["new_zealand"],
}
LANG_CC = {"fas": "IR", "tur": "TR", "ara": "EG", "heb": "IL", "hin": "IN", "urd": "PK", "ben": "BD", "zho": "CN", "cmn": "CN", "yue": "HK", "jpn": "JP", "kor": "KR",
           "vie": "VN", "tha": "TH", "spa": "MX", "por": "BR", "fra": "FR", "ita": "IT", "ell": "GR", "deu": "DE", "rus": "RU", "ukr": "UA", "pol": "PL", "hye": "AM", "kat": "GE"}

_CACHE: dict[str, tuple[float, Any]] = {}
TTL = 6 * 3600


def _memo(key: str, fn):
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    v = fn()
    if v.get("ok"):                     # a failed or empty answer is asked again next time
        _CACHE[key] = (time.time(), v)
    return v


def tag_ids(e: dict[str, Any]) -> list[str]:
    return [str(t.get("tag_id") or t.get("id") or "") for t in (e.get("tags") or []) if isinstance(t, dict)]


def _slug(x: str) -> str:
    return "_".join("".join(c if c.isalnum() else " " for c in str(x).lower()).split())


def suffixes(e: dict[str, Any]) -> list[str]:
    """The place's own categories ("park", "persian_restaurant"), whichever way Qloo spells its tags:
    a full id (urn:tag:category:place:park), or a type (urn:tag:category:place) with a name ("Park")."""
    out = []
    for t in (e.get("tags") or []):
        if not isinstance(t, dict):
            continue
        tid = str(t.get("tag_id") or t.get("id") or "")
        typ = str(t.get("type") or "")
        if tid.startswith("urn:tag:category:place:") or tid.startswith("urn:tag:genre:place:"):
            out.append(tid.rsplit(":", 1)[-1])
        elif typ.startswith("urn:tag:category:place") or typ.startswith("urn:tag:genre:place"):
            if t.get("name"):
                out.append(_slug(t["name"]))
    return list(dict.fromkeys(x for x in out if x and x not in ("place", "places")))


# which kinds of place suit the end of each session. Qloo's own categories for the person's taste are ranked
# inside these; the list is a suitability rule (a calm session does not end in a nightclub), not a recommendation.
_QUIET = ["park", "city_park", "botanical_garden", "garden", "nature_preserve", "hiking_area", "beach", "lake", "museum", "art_museum", "history_museum",
          "library", "book_store", "used_book_store", "tea_house", "spa", "yoga_studio", "meditation_center", "aquarium", "observatory", "planetarium",
          "cultural_center", "art_gallery", "scenic_spot", "tourist_attraction", "historical_landmark", "monument", "community_garden"]
SUITS: dict[str, list[str]] = {
    "sleep": _QUIET, "calm": _QUIET, "autism_calm": [k for k in _QUIET if k not in ("tourist_attraction", "historical_landmark", "monument")] + ["zoo", "playground"],
    "focus": ["library", "coffee_shop", "cafe", "book_store", "used_book_store", "coworking_space", "tea_house", "museum", "park", "botanical_garden"],
    "energy": ["park", "city_park", "hiking_area", "beach", "rock_climbing_gym", "gym", "fitness_center", "dance_school", "dance_studio", "yoga_studio",
               "swimming_pool", "sports_complex", "skate_park", "bowling_alley", "trampoline_park", "ice_skating_rink", "record_store", "live_music_venue"],
    "mood": ["park", "city_park", "museum", "art_museum", "art_gallery", "record_store", "live_music_venue", "concert_hall", "book_store", "comedy_club",
             "botanical_garden", "cultural_center", "market", "flea_market", "theater", "performing_arts_theater", "beach", "tourist_attraction"],
    "memory": ["museum", "history_museum", "art_museum", "cultural_center", "record_store", "park", "book_store", "used_book_store", "concert_hall", "theater",
               "historical_landmark", "monument", "market", "botanical_garden", "art_gallery", "tourist_attraction"],
}
FOODISH = {"restaurant", "cafe", "coffee_shop", "bakery", "tea_house", "dessert_shop", "ice_cream_shop", "juice_bar", "deli", "bistro", "diner", "brunch",
           "breakfast_restaurant", "food_court", "patisserie", "creperie", "noodle_shop", "dumpling_restaurant", "bagel_shop", "donut_shop", "sandwich_shop"}


def kitchens(e: dict[str, Any]) -> list[str]:
    """The cuisines a place is tagged with in Qloo: mexican_restaurant -> mexican."""
    out = []
    for s_ in suffixes(e):
        if s_.endswith("_restaurant") and s_ not in ("fast_food_restaurant", "family_restaurant", "fine_dining_restaurant", "breakfast_restaurant"):
            out.append(s_[: -len("_restaurant")])
    return out


def is_food(e: dict[str, Any]) -> bool:
    sx = set(suffixes(e))
    return bool(sx & FOODISH) or any(x.endswith("_restaurant") for x in sx)


def diverse(rows: list[dict[str, Any]], kinds: set[str] | None, n: int) -> list[dict[str, Any]]:
    """Best first, but one of each kind before a second of any (a park, a library, a museum, then more)."""
    picked, seen = [], set()
    for e in rows:
        k = next((x for x in suffixes(e) if (kinds is None or x in kinds)), None) if kinds is not None else (kitchens(e) or [None])[0]
        if k not in seen:
            picked.append(e); seen.add(k)
        if len(picked) >= n:
            return picked
    for e in rows:
        if len(picked) >= n:
            break
        if e not in picked:
            picked.append(e)
    return picked


def avoided(e: dict[str, Any], child: bool = False, calm: bool = False) -> bool:
    sx = suffixes(e)
    slugs = [w for w in sx + [_slug(e.get("name") or "")] + [_slug(t.get("name") or "") for t in (e.get("tags") or []) if isinstance(t, dict)] if w]
    tokens = {tok for w in slugs for tok in w.split("_")}
    # whole words only: "bar" is a bar, never Barefoot Coffee or the Embarcadero
    def hit(items) -> bool:
        return any(i in slugs or i in tokens or any(w.endswith("_" + i) or w.startswith(i + "_") for w in slugs) for i in items)
    if hit(AVOID):
        return True
    if calm and hit(CALM_AVOID):
        return True
    return child and any(s in CHILD_AVOID for s in sx)


def _num(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def geo(e: dict[str, Any]) -> tuple[float, float] | None:
    g = (e.get("properties") or {}).get("geocode") or e.get("location") or {}
    lat = _num(g.get("latitude") if isinstance(g, dict) else None) or _num((e.get("location") or {}).get("lat"))
    lon = _num(g.get("longitude") if isinstance(g, dict) else None) or _num((e.get("location") or {}).get("lon"))
    return (lat, lon) if lat is not None and lon is not None else None


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0]); dp = p2 - p1; dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def because(e: dict[str, Any], favs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ex = ((e.get("query") or {}).get("explainability") or {}).get("signal.interests.entities") or []
    out = []
    for x in ex[:3]:
        eid = str(x.get("entity_id", ""))
        hit = next((f for f in favs if f.get("entity_id") and (f["entity_id"] == eid or f["entity_id"].startswith(eid[:8]))), None)
        if hit:
            out.append({"name": hit["name"], "score": round(float(x.get("score") or 0), 3)})
    return out


def card(e: dict[str, Any], kind: str, favs: list[dict[str, Any]], centre: tuple[float, float] | None) -> dict[str, Any]:
    p = e.get("properties") or {}
    img = p.get("image")
    img = img.get("url") if isinstance(img, dict) else img
    addr = p.get("address") or ""
    g = geo(e)
    sx = [s for s in suffixes(e) if not s.startswith("restaurant") or s == "restaurant"]
    q = urllib.parse.quote_plus(f"{e.get('name', '')} {addr}".strip())
    return {"kind": kind, "name": e.get("name"), "entity_id": e.get("entity_id"),
            "affinity": round(float((e.get("query") or {}).get("affinity") or 0), 3), "popularity": e.get("popularity"),
            "category": next((s for s in sx), None), "categories": sx[:4], "address": addr or None, "image": img,
            "rating": p.get("business_rating"), "price": p.get("price_level"),
            "lat": g[0] if g else None, "lon": g[1] if g else None, "km": round(km(centre, g), 1) if g and centre else None,
            "desc": (p.get("description") or p.get("short_description") or "")[:220] or None,
            "because": because(e, favs), "map": f"https://www.google.com/maps/search/?api=1&query={q}",
            "year": p.get("publication_year"), "source": e.get("_source")}


def _centroid(data: dict[str, Any]) -> tuple[float, float] | None:
    loc = (((data.get("query") or {}).get("localities") or {}).get("filter")) if isinstance(data, dict) else None
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, dict):
        lat = _num(loc.get("latitude") or (loc.get("location") or {}).get("lat")); lon = _num(loc.get("longitude") or (loc.get("location") or {}).get("lon"))
        if lat is not None and lon is not None:
            return lat, lon
    return None


def _where(city: str, here: tuple[float, float] | None) -> dict[str, Any]:
    """Where to look: the person's own spot when they shared it (rounded to ~1 km), else their city."""
    if here:
        return {"filter.location": f"POINT({here[1]:.2f} {here[0]:.2f})", "filter.location.radius": 6000}
    return {"filter.location.query": city}


def here_of(profile: dict[str, Any]) -> tuple[float, float] | None:
    h = profile.get("here")
    try:
        lat, lon = float(h[0]), float(h[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return round(lat, 2), round(lon, 2)                 # about 1 km: a neighbourhood, never a door


def _places(client: QlooClient, ids: list[str], city: str, tags: list[str], label: str, take: int = 20,
            here: tuple[float, float] | None = None) -> tuple[list[dict[str, Any]], tuple[float, float] | None, str]:
    params: dict[str, Any] = {"filter.type": "urn:entity:place", "take": take, "feature.explainability": True,
                              "signal.interests.entities": ids, **_where(city, here)}
    if tags:
        params["filter.tags"] = ",".join(tags); params["operator.filter.tags"] = "union"
    try:
        out = client.get("/v2/insights", params, label=label)
    except (QlooError, ParamRefused):
        return [], None, "error"
    data = out.get("data") or {}
    res = data.get("results") or {}
    ents = res.get("entities") if isinstance(res, dict) else None
    ents = ents or []
    if not ents and here and city:
        return _places(client, ids, city, tags, label + ".city", take, None)
    for e in ents:
        e["_source"] = out.get("source")
    return ents, (here if here else _centroid(data)), out.get("source") or "none"


def cultures(profile: dict[str, Any], lens: dict[str, Any] | None) -> list[tuple[str, str]]:
    """(favourite, country code) for the person's own artists, most shared first."""
    from . import tour
    favs = [f for f in profile.get("favorites", []) if f.get("type") == "artist" and f.get("name")]
    out: list[tuple[str, str]] = []
    for f in favs[:8]:
        info = tour.mb_info(f["name"], network=False) or {}
        cc = info.get("cc")
        if not cc:
            langs = info.get("langs") or {}
            top = max(langs, key=langs.get) if isinstance(langs, dict) and langs else None
            cc = LANG_CC.get(top or "")
        if cc:
            out.append((f["name"], cc))
    counts: dict[str, int] = {}
    for _, cc in out:
        counts[cc] = counts.get(cc, 0) + 1
    out.sort(key=lambda x: -counts[x[1]])
    return out


def after(client: QlooClient, profile: dict[str, Any], goal: str, local_hour: int | None = None, lens: dict[str, Any] | None = None) -> dict[str, Any]:
    goal = goal if goal in PLAN else "calm"
    plan = PLAN[goal]
    favs = profile.get("favorites", [])
    ids = favourite_ids(profile)[:8]
    city = str(profile.get("city") or "").strip()[:60]
    here = here_of(profile)
    age = int(profile.get("age") or 30)
    child = age < 13
    when = "tomorrow" if plan["when"] == "tomorrow" or (local_hour is not None and (local_hour >= 21 or local_hour < 5)) else "today"
    sent = ["entity ids", "place category tags"] + (["your position, rounded to about 1 km"] if here else [f"your city ({city})"] if city else [])
    base = {"goal": goal, "when": when, "city": city or None, "sent": sent, "places": [], "food": [], "read": [], "mode": "fixture" if client.offline else "live"}
    if not ids:
        return {**base, "ok": False, "reason": "no_favourites"}
    pid = profile.get("id", "p")

    def run() -> dict[str, Any]:
        out = dict(base); notes: list[str] = []
        centre = None
        calm = goal in CALM_GOALS
        ok_kinds = set(SUITS.get(goal, SUITS["calm"])) - (set(CHILD_AVOID) if child else set())
        if city or here:
            # 1. what this taste loves near them, with no category filter: Qloo decides the kinds of place
            wide, centre, _ = _places(client, ids, city, [], f"{pid}.after.wide", take=50, here=here)
            # 2. the kinds of place that suit what the session was for, ranked by the same taste
            tags = [C + t for t in plan["places"] if not (child and t in CHILD_AVOID)]
            fit, c2, _ = _places(client, ids, city, tags, f"{pid}.after.places.{goal}", take=25, here=here)
            centre = centre or c2
            # 3. kitchens: the ones Qloo's own results for this taste are tagged with; after a memory session,
            #    the kitchen of the songs (the favourites' countries) first
            origin: list[dict[str, str]] = []
            food_tags: list[str] = []
            if goal == "memory":
                for fav, cc in cultures(profile, lens)[:3]:
                    for word in CUISINE.get(cc, [])[:2]:
                        if C + f"{word}_restaurant" not in food_tags:
                            food_tags.append(C + f"{word}_restaurant")
                        origin.append({"tag": word, "fav": fav})
            seen_k: dict[str, float] = {}
            for e in wide:
                for k in kitchens(e):
                    seen_k[k] = seen_k.get(k, 0) + float((e.get("query") or {}).get("affinity") or 0)
            for k in sorted(seen_k, key=lambda k: -seen_k[k])[:4]:
                if C + f"{k}_restaurant" not in food_tags:
                    food_tags.append(C + f"{k}_restaurant")
            if not food_tags:
                food_tags = [C + "restaurant", C + "cafe", C + "bakery"]
            food, c3, _ = _places(client, ids, city, food_tags, f"{pid}.after.food.{goal}", take=25, here=here)
            centre = centre or c3
            # merge and sort into places and tables
            pool: dict[str, dict[str, Any]] = {}
            for e in fit + wide + food:
                k = str(e.get("entity_id") or e.get("name"))
                if k not in pool or float((e.get("query") or {}).get("affinity") or 0) > float((pool[k].get("query") or {}).get("affinity") or 0):
                    pool[k] = e
            aff = lambda e: -float((e.get("query") or {}).get("affinity") or 0)
            places_c, food_c = [], []
            for e in sorted(pool.values(), key=aff):
                if avoided(e, child, calm):
                    continue
                if is_food(e):
                    food_c.append(e)
                elif set(suffixes(e)) & ok_kinds:
                    places_c.append(e)
            out["places"] = [card(e, "place", favs, centre) for e in diverse(places_c, ok_kinds, 6)]
            out["food"] = [card(e, "food", favs, centre) for e in diverse(food_c, None, 6)]
            for f in out["food"]:
                ks = kitchens({"tags": [{"id": C + c} for c in (f.get("categories") or [])]}) or []
                hits = [o for o in origin if o["tag"] in ks]
                by = {b["name"] for b in f.get("because") or []}
                if hits:
                    hit = next((o for o in hits if o["fav"] in by), hits[0]); f["kitchen"] = hit["tag"].replace("_", " "); f["close_to"] = hit["fav"]
                elif ks:
                    f["kitchen"] = ks[0].replace("_", " ")
            if not out["food"]:
                notes.append("no_food")
        else:
            notes.append("no_city")
        # 4. a page: books from the same taste (no location needed)
        try:
            books = client.insights("book", entities=ids, take=10, label=f"{pid}.after.read")
        except (QlooError, ParamRefused):
            books = []
        out["read"] = [card(e, "read", favs, None) for e in books[:4]]
        out["centre"] = {"lat": centre[0], "lon": centre[1]} if centre else None
        out["notes"] = notes
        out["ok"] = bool(out["places"] or out["food"] or out["read"])
        if not out["ok"]:
            out["reason"] = "no_city" if "no_city" in notes and not out["read"] else "no_results"
        return out

    key = f"{pid}|{','.join(sorted(ids))}|{city.lower()}|{here}|{goal}|{when}|{int(child)}|{client.offline}"
    return _memo(key, run)
