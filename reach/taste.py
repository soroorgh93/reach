"""The Taste agent: reads the person's cultural taste through Qloo and turns it into
(a) a carrier playlist of artists that fit the protocol, (b) a texture profile the music
engine can play, and (c) a cultural lens. Reach cannot compose without this: if Qloo
returns nothing usable the council refuses to proceed, by design.

What is sent to Qloo: entity ids of favourites, genre tag ids, the city, an age bucket.
Never the request text, mood, face or voice.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from . import culture
from .qloo import QlooClient, QlooError, ParamRefused

GENRE_URN = "urn:tag:genre:music:"

# Qloo artist tag words -> engine palette. First match wins; order is by specificity.
PALETTE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("piano", "pianist"), "piano"),
    (("classical", "orchestral", "symphon", "strings", "cinematic", "score"), "strings"),
    (("latin", "reggaeton", "salsa", "bachata", "flamenco", "bossa", "cumbia", "spanish"), "nylon"),
    (("jazz", "soul", "r&b", "rnb", "neo soul", "funk", "motown"), "epiano"),
    (("folk", "acoustic", "singer-songwriter", "singer songwriter", "country", "americana", "bluegrass"), "plucked"),
    (("electronic", "synth", "edm", "house", "techno", "ambient", "chillwave", "lo-fi", "lo fi", "idm"), "synth"),
    (("children", "kids", "family", "lullaby", "disney", "soundtrack"), "bells"),
    (("rock", "indie", "alternative", "pop", "punk"), "guitar"),
    (("hip hop", "hip-hop", "rap", "trap"), "synth"),
    (("world", "african", "afrobeat", "indian", "middle east", "persian", "arabic", "asian", "k-pop", "kpop", "j-pop"), "plucked"),
]
MOOD_WORDS = {"warm": 0.3, "intimate": 0.25, "melancholic": -0.4, "melancholy": -0.4, "dark": -0.3, "bright": 0.3, "uplifting": 0.4,
              "energetic": 0.35, "gentle": 0.2, "soothing": 0.3, "dreamy": 0.15, "aggressive": -0.5, "intense": -0.1, "playful": 0.3,
              "romantic": 0.2, "sad": -0.4, "calm": 0.3, "relaxing": 0.3, "epic": 0.1, "haunting": -0.2, "nostalgic": 0.0}
TEMPO_WORDS = {"energetic": 0.3, "upbeat": 0.3, "danceable": 0.3, "fast": 0.3, "slow": -0.3, "ambient": -0.3, "relaxing": -0.3, "mellow": -0.2, "chill": -0.2, "ballad": -0.2}


def favourite_ids(profile: dict[str, Any]) -> list[str]:
    return [f["entity_id"] for f in profile.get("favorites", []) if f.get("entity_id")]


def _aff(e: dict[str, Any]) -> float:
    q = e.get("query") or {}
    return float(q.get("affinity") or 0.0)


MUSIC_WORDS = ("rock", "pop", "jazz", "folk", "piano", "soul", "indie", "ambient", "electronic", "classical", "latin", "singer", "songwriter",
               "acoustic", "guitar", "vocal", "melodic", "intimate", "warm", "blues", "country", "hip hop", "hip-hop", "rap", "r&b", "metal", "punk",
               "orchestral", "cinematic", "synth", "house", "techno", "lo-fi", "lo fi", "chill", "relax", "calm", "dream", "dark", "bright", "energetic",
               "gentle", "soothing", "lullaby", "children", "kids", "soundtrack", "world", "reggae", "gospel", "funk", "disco", "ballad", "instrumental",
               "experimental", "alternative", "dance", "trap", "drill", "afro", "k-pop", "j-pop", "flamenco", "bossa", "salsa", "cumbia", "tango",
               "opera", "choral", "strings", "harp", "bell", "voice", "tenor", "alto", "soprano", "baritone", "emotional", "romantic", "melanchol",
               "uplifting", "nostalg", "introspective", "authentic", "poetic", "storytelling", "lyrical", "mellow", "upbeat", "slow", "fast", "haunting",
               "atmospheric", "ethereal", "minimal", "epic", "playful", "spiritual", "sacred", "meditat", "new age", "trance", "psychedelic", "grunge")


def _tags(e: dict[str, Any]) -> list[str]:
    """Tag names that describe music (genre, mood, instrument, style); related-artist names are dropped."""
    out = []
    for t in (e.get("tags") or []):
        name = str(t.get("name", "")).lower().strip()
        ttype = str(t.get("type", "") or "")
        if not name:
            continue
        if ttype and any(k in ttype for k in ("genre", "style", "mood", "instrument", "theme", "descriptor", "audience", "character")):
            out.append(name); continue
        if " " not in name or any(w in name for w in MUSIC_WORDS):
            out.append(name)
    return out


def palette_from_tags(tag_names: list[str]) -> tuple[str, dict[str, int]]:
    votes: dict[str, int] = {}
    for name in tag_names:
        for words, pal in PALETTE_RULES:
            if any(w in name for w in words):
                votes[pal] = votes.get(pal, 0) + 1
                break
    if not votes:
        return "piano", votes
    return max(votes, key=votes.get), votes


def slim(e: dict[str, Any], favs: list[dict[str, Any]]) -> dict[str, Any]:
    p = e.get("properties") or {}
    q = e.get("query") or {}
    ex = (q.get("explainability") or {}).get("signal.interests.entities") or []
    because = []
    for x in ex[:3]:
        eid = str(x.get("entity_id", ""))
        hit = next((f for f in favs if f.get("entity_id") and f["entity_id"].startswith(eid[:8])), None)
        because.append({"name": hit["name"] if hit else eid[:8], "score": round(float(x.get("score", 0)), 3)})
    img = p.get("image")
    return {"name": e.get("name"), "entity_id": e.get("entity_id"), "affinity": round(_aff(e), 3), "popularity": e.get("popularity"),
            "image": img.get("url") if isinstance(img, dict) else img, "tags": _tags(e)[:6], "because": because, "source": e.get("_source")}


class TasteAgent:
    def __init__(self, client: QlooClient):
        self.client = client
        self.calls: list[dict[str, Any]] = []
        self._lens: dict[str, Any] | None = None
        self._prof: dict[str, dict[str, Any]] = {}
        self._t0: float | None = None

    def _budget(self, total: float = 6.0) -> float:
        """Seconds left for open-data lookups in this council run (MusicBrainz is one request a second)."""
        import time as _t
        if self._t0 is None:
            self._t0 = _t.monotonic()
        return max(0.0, total - (_t.monotonic() - self._t0))

    def _profiles(self, names: list[str]) -> dict[str, dict[str, Any]]:
        need = [n for n in dict.fromkeys(names) if n and n not in self._prof]
        if need:
            self._prof.update(culture.profiles(need, budget_s=self._budget(), network=not self.client.offline))
        return {n: self._prof.get(n, {}) for n in names}

    def lens(self, profile: dict[str, Any]) -> dict[str, Any]:
        """The cultural lens of the person's own artists (computed once per council run)."""
        if self._lens is None:
            names = [f["name"] for f in profile.get("favorites", []) if f.get("type") == "artist" and f.get("name")]
            P = self._profiles(names)
            self._lens = culture.lens(names, P, culture.Lang({n: P[n].get("grams") or ({}, {}) for n in names}))
        return self._lens

    def rank_cultural(self, pools: dict[str, list[dict[str, Any]]], favs: list[dict[str, Any]], lens: dict[str, Any], exclude: set[str],
                      feedback: dict[str, float] | None = None, explore: bool = False, k: int = 8) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """The ranking step. Qloo generated the candidates (its general picks, the texture-fitted ones, and
        the ones its location signal finds in the person's culture); here each is scored on
          Qloo affinity + texture fit + the culture of the person's own artists (MusicBrainz place, and
          the language of the artist's titles) + what the person finished or skipped before,
        then the slots are shared out in proportion to the person's own mix of cultures (three Persian
        favourites and one American: six Persian picks and two American), a candidate from a culture none of
        their artists come from is set aside when the person is a specialist (most favourites in one culture),
        and a diversity re-rank (MMR) keeps the list from repeating one sound."""
        merged: dict[str, dict[str, Any]] = {}
        for src, rows in pools.items():
            for e in rows:
                nm = e.get("name")
                if not nm or e.get("entity_id") in exclude or culture.norm(nm) in exclude:
                    continue
                m = merged.setdefault(culture.norm(nm), {"e": e, "src": set()})
                m["src"].add(src)
                if _aff(e) > _aff(m["e"]):
                    m["e"] = e
        # what gets a full profile: every pick from the cultural pool, then the strongest of the rest
        ranked = sorted(merged.values(), key=lambda m: -_aff(m["e"]))
        rows = [m for m in ranked if "culture" in m["src"]][:12]
        rows += [m for m in ranked if m not in rows][: max(0, 22 - len(rows))]
        fav_names = [f["name"] for f in favs if f.get("type") == "artist" and f.get("name")]
        P = self._profiles(fav_names + [m["e"]["name"] for m in rows])
        culture.warm([m["e"]["name"] for m in rows if not P.get(m["e"]["name"], {}).get("cc")])
        lang = culture.Lang({n: (P[n].get("grams") or ({}, {})) for n in P})
        L = culture.lens(fav_names, P, lang)
        lens.update({"groups": L.get("groups"), "specialist": L.get("specialist")})
        counts, total = L.get("counts", {}), max(1, L.get("total", len(fav_names) or 1))
        # strict only when Reach knows where nearly all of the person's artists come from and most share one culture
        specialist = L.get("coverage", 0) >= 0.75 and L.get("share", 0) >= 0.6 and not explore
        of = L.get("of") or {}
        fb = {str(a).lower(): float(v) for a, v in (feedback or {}).items()}
        kept, aside = [], []
        for m in rows:
            e = m["e"]; nm = e["name"]
            grp, lsim, place = culture.match(nm, P.get(nm, {}), L, lang)
            cc = (P.get(nm) or {}).get("cc")
            f = max(-1.0, min(1.0, fb.get(nm.lower(), 0.0)))
            if f <= -0.6:
                aside.append({"name": nm, "culture": cc, "why": "skipped"}); continue
            foreign = place == 0.0                     # only when the data says so; an unknown artist is never foreign
            if foreign and specialist:
                aside.append({"name": nm, "culture": cc, "why": "culture"}); continue
            rel = _aff(e) + (0.10 if "fit" in m["src"] else 0) + (0.12 if "culture" in m["src"] else 0) \
                + 0.30 * (lsim or 0.0) + 0.25 * (place or 0.0) + 0.30 * f - (0.08 if foreign else 0.0)
            if grp is None:                            # culture unknown: it belongs with the favourite Qloo says it comes from
                b = next((x["name"] for x in slim(e, favs).get("because", []) if of.get(x["name"])), None)
                grp = of.get(b) if b else None
            c = slim(e, favs); c.update({"score": round(rel, 3), "culture": cc, "culture_name": (P.get(nm) or {}).get("country") or cc,
                                          "lang_sim": lsim, "via": sorted(m["src"]), "assigned": grp, "feedback": round(f, 2)})
            kept.append(c)
        # slots per culture, in proportion to the person's own artists (largest remainder)
        quota: dict[str, int] = {}
        if counts:
            # every favourite gets its share of the slots; favourites not yet looked up share an open pool
            raw = {cc: k * n / total for cc, n in counts.items()}
            raw[None] = k * (total - sum(counts.values())) / total
            quota = {cc: int(v) for cc, v in raw.items()}
            for cc in sorted(raw, key=lambda x: -(raw[x] - int(raw[x])))[: k - sum(quota.values())]:
                quota[cc] += 1
        # MMR: relevance minus similarity to what is already chosen (language of titles, same country)
        lam = 0.18 if specialist else 0.32
        def similar(a: dict, b: dict) -> float:
            s = lang.sim(a["name"], lang.group([b["name"]])) or 0.0
            return max(s, 0.5 if a.get("assigned") is None and b.get("assigned") is None and a.get("culture") and a.get("culture") == b.get("culture") else 0.0)
        chosen: list[dict] = []; pool = kept[:]
        while pool and len(chosen) < k:
            def ok(c: dict) -> bool:
                if not quota:
                    return True
                q = c.get("assigned") if c.get("assigned") in quota else None
                return sum(1 for x in chosen if (x.get("assigned") if x.get("assigned") in quota else None) == q) < quota.get(q, 0)
            eligible = [c for c in pool if ok(c)] or pool
            best = max(eligible, key=lambda c: c["score"] - lam * max((similar(c, x) for x in chosen), default=0.0))
            chosen.append(best); pool.remove(best)
        return chosen, aside

    def _insights(self, ftype: str, label: str, **params: Any) -> list[dict[str, Any]]:
        try:
            ents = self.client.insights(ftype, label=label, **params)
        except (ParamRefused, QlooError) as e:
            self.calls.append({"label": label, "error": str(e)})
            return []
        self.calls.append({"label": label, "n": len(ents), "source": ents[0]["_source"] if ents else "none"})
        return ents

    def read(self, profile: dict[str, Any], protocol: dict[str, Any], memory: dict[str, Any] | None = None) -> dict[str, Any]:
        """memory: {"liked": [entity ids], "disliked": [entity ids]} from the person's own feedback."""
        pid = profile.get("id", "p")
        favs = profile.get("favorites", [])
        memory = memory or {}
        liked = [x for x in memory.get("liked", []) if isinstance(x, str)][:8]
        disliked = [x for x in memory.get("disliked", []) if isinstance(x, str)][:16]
        ids = favourite_ids(profile) + [x for x in liked if x not in favourite_ids(profile)]
        gtags = [t for t in profile.get("favorite_tags", []) if isinstance(t, str) and t.startswith("urn:tag:")] + [f["tag"] for f in favs if f.get("type") == "genre" and f.get("tag")]
        if not ids and not gtags:
            return {"ok": False, "reason": "no favourites resolved to Qloo entities", "carrier": [], "palette": "piano"}
        carrier_pref = protocol.get("carrier", {})
        prefer = [GENRE_URN + t for t in carrier_pref.get("tags_prefer", [])]
        avoid = [GENRE_URN + t for t in carrier_pref.get("tags_avoid", [])]
        if memory.get("instrumental"):
            prefer = [GENRE_URN + "instrumental", GENRE_URN + "ambient", GENRE_URN + "classical", GENRE_URN + "post_rock", GENRE_URN + "jazz"] + prefer
        age = profile.get("age") or 30
        common: dict[str, Any] = {"entities": ids or None, "tags": gtags or None, "take": 12}
        if avoid:
            common["filter.exclude.tags"] = ",".join(avoid)
        if disliked:
            common["filter.exclude.entities"] = ",".join(disliked)

        if carrier_pref.get("visual"):
            # visual carrier: films and shows the person would watch, child-rated for children
            extra = {"filter.content_rating": "G,PG,TV-Y,TV-Y7,TV-G,TV-PG"} if age < 13 else {}
            shows = self._insights("movie", f"{pid}.visual.movie", entities=ids, take=8, **extra) + self._insights("tv_show", f"{pid}.visual.tv", entities=ids, take=6, **extra)
            if not shows:
                # no films or shows recorded for these favourites: the general carrier (artists) still names the taste the light follows
                shows = self._insights("artist", f"{pid}.artist.general", entities=ids, take=12)
            if not shows:
                return {"ok": False, "reason": "Qloo returned no films, shows or artists for these favourites", "carrier": [], "palette": "pad", "calls": self.calls}
            carrier = [slim(e, favs) for e in sorted(shows, key=_aff, reverse=True)][:8]
            affs = [c["affinity"] for c in carrier if c["affinity"] > 0]; n = len(affs); k = 6.0
            return {"ok": True, "carrier": carrier, "favourites_first": [], "palette": "pad", "palette_votes": {}, "mood_bias": 0.0, "tempo_bias": -0.2,
                    "texture_tags": sorted({t for e in shows for t in _tags(e)})[:8], "fit_rate": 1.0, "strength": round((n * float(np.mean(affs)) + k * 0.86) / (n + k) if affs else 0.86, 4),
                    "data_weight": round(n / (n + k), 3), "demographics": [], "source": carrier[0]["source"] if carrier else "none",
                    "sent": ["entity ids", f"age bucket {'child' if age < 13 else 'adult'}"], "calls": self.calls, "visual": True}
        # 1. carrier artists that fit the protocol's texture (union of preferred genres), then unfiltered fallback
        fitted = self._insights("artist", f"{pid}.{protocol['id']}.artist.fit", **common,
                                **({"filter.tags": ",".join(prefer), "operator.filter.tags": "union"} if prefer else {}))
        general = self._insights("artist", f"{pid}.artist.general", entities=ids or None, tags=gtags or None, take=12, **({"filter.exclude.entities": ",".join(disliked)} if disliked else {}))
        # the person's own artists lead, always (asked-for names first), then Qloo's picks in their culture
        pins = [x for x in memory.get("pin", []) if isinstance(x, str) and x.strip()][:4]
        fav_artists = [f for f in favs if f.get("type") == "artist" and f.get("name")]
        lens = self.lens(profile)
        cultural = []
        if ids and lens.get("dominant") and lens.get("city") and lens.get("share", 0) >= 0.5:
            cultural = self._insights("artist", f"{pid}.artist.culture.{lens['dominant'].lower()}", entities=ids, take=15,
                                      **{"signal.location.query": lens["city"], **({"filter.exclude.entities": ",".join(disliked)} if disliked else {})})
        # 2. texture profile: the tags Qloo attaches to what this person loves
        tagrows = self._insights("urn:tag", f"{pid}.tags.music", entities=ids or None, tags=gtags or None, take=20, **{"filter.tag.types": "urn:tag:genre:music,urn:tag:style:music,urn:tag:mood:music"}) if ids else []
        if not tagrows and ids:
            tagrows = self._insights("urn:tag", f"{pid}.tags.any", entities=ids, take=20)
        # 3. cultural lens: demographics of the favourites' audience
        demo = self._insights("urn:demographics", f"{pid}.demographics", entities=ids, take=5) if ids else []

        pool = fitted + general + cultural
        if not pool:
            return {"ok": False, "reason": "Qloo returned no artists for these favourites", "carrier": [], "palette": "piano", "calls": self.calls}
        exclude = set(ids) | {culture.norm(f["name"]) for f in fav_artists} | {culture.norm(p) for p in pins}
        carrier, set_aside = self.rank_cultural({"culture": cultural, "general": general, "fit": fitted}, favs, lens, exclude,
                                                feedback=memory.get("fb") if isinstance(memory.get("fb"), dict) else None, explore=bool(memory.get("explore")))
        carrier = carrier[:8]
        own = []
        for nm in pins:
            f = next((x for x in fav_artists if culture.norm(x["name"]) == culture.norm(nm)), None)
            own.append({"name": f["name"] if f else nm, "entity_id": (f or {}).get("entity_id"), "own": bool(f), "pinned": True, "image": (f or {}).get("image"),
                        "culture": lens["of"].get(f["name"]) if f else None})
        for f in fav_artists:
            if not any(culture.norm(o["name"]) == culture.norm(f["name"]) for o in own):
                own.append({"name": f["name"], "entity_id": f.get("entity_id"), "own": True, "image": f.get("image"), "culture": lens["of"].get(f["name"])})
        all_tag_names = [t for e in pool for t in _tags(e)] + [str(t.get("name", "")).lower() for t in tagrows if t.get("name")]
        palette, votes = palette_from_tags(all_tag_names)
        mood_bias = float(np.mean([MOOD_WORDS[w] for n in all_tag_names for w in MOOD_WORDS if w in n] or [0.0]))
        tempo_bias = float(np.mean([TEMPO_WORDS[w] for n in all_tag_names for w in TEMPO_WORDS if w in n] or [0.0]))
        affs = [c["affinity"] for c in carrier if c.get("affinity", 0) > 0]
        # empirical-Bayes shrinkage of the carrier strength toward the artist-domain prior (0.88 on this tier)
        n = len(affs); k = 6.0
        strength = (n * float(np.mean(affs)) + k * 0.88) / (n + k) if affs else 0.88
        fit_rate = len(fitted) / 12 if prefer else 1.0
        return {
            "ok": True, "carrier": carrier, "favourites_first": own[:6], "lens": {k: lens.get(k) for k in ("dominant", "name", "cc", "share", "of", "city", "specialist", "counts")},
            "set_aside": set_aside[:6], "pinned": pins,
            "palette": palette, "palette_votes": votes, "mood_bias": round(mood_bias, 3), "tempo_bias": round(tempo_bias, 3),
            "texture_tags": sorted(set(all_tag_names), key=all_tag_names.count, reverse=True)[:10],
            "fit_rate": round(fit_rate, 2), "strength": round(strength, 4), "data_weight": round(n / (n + k), 3),
            "demographics": demo[:3] if demo else [],
            "source": carrier[0]["source"] if carrier else (pool[0].get("_source") if pool else "none"),
            "sent": ["entity ids", "genre tag ids", f"age bucket {'child' if age < 13 else 'adult'}"] + ([f"a place for the cultural lens ({lens['city']})"] if cultural else []) + (["liked/disliked artist ids"] if liked or disliked else []),
            "memory_used": {"liked": len(liked), "disliked": len(disliked)},
            "calls": self.calls,
        }
