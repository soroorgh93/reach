"""The cultural lens, learned from data, never written down as a list of cultures.

Why it exists. Qloo's graph is built from co-consumption, and co-consumption crosses borders: the people who
play Hayedeh and Dariush also play Turkish indie, so a texture filter can leave only the neighbours standing.
Research on music recommendation says the same thing from the other side: listening is increasingly local
(Way et al., ICWSM 2020: shared language and geography predict what people play, more so each year), the
country code alone is a weak proxy for culture (Zangerle et al., UMAP 2018), and culture should be read
through language as well as borders (Schedl et al., 2018).

So each artist gets three signals, all from open data:
  place     MusicBrainz: the artist's country (and city), resolved through its area relations
  language  a character n-gram fingerprint of the artist's own song titles (Deezer). This is how language
            identifiers such as CLD3 work: Hangul, Han, kana, Persian and Arabic letters, Cyrillic, Devanagari,
            Turkish ı ğ ş, Vietnamese tones, Spanish ñ separate themselves with no list of languages anywhere
  taste     Qloo affinity, and which of the person's favourites a pick comes from (explainability)

and the person gets a lens: the share of their favourites per country, the fingerprint of each, and how
specialised they are (one culture or many). The ranking step (taste.py) uses it the way large recommenders
do (Covington et al., RecSys 2016): Qloo generates candidates, a ranking step scores them on these signals and
on what the person actually finishes or skips, slots follow the person's own mix of cultures, and a diversity
re-rank (MMR, Carbonell & Goldstein 1998) keeps one sound from taking over.

MusicBrainz allows one request a second, so lookups run against a time budget and the rest are warmed in the
background: the first session sees most of it, every later session sees all of it.
"""
from __future__ import annotations

import math
import re
import threading
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import previews as prev
from . import tour


# ------------------------------------------------------------------ language fingerprints
def _letters(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").lower()
    s = re.sub(r"\(.*?\)|\[.*?\]|\bfeat\..*|\bft\..*|\bremaster.*|\blive\b.*|\bversion\b.*", " ", s)   # credits say nothing about language
    return " ".join(re.sub(r"[^\w\s]|[\d_]", " ", s).split())


def _script(ch: str) -> str:
    try:
        w = unicodedata.name(ch).split()[0]
    except ValueError:
        return "?"
    return "HAN" if w == "CJK" else w


def grams(texts: list[str]) -> tuple[Counter, Counter]:
    """(character n-grams, letters per Unicode script) of some titles. Latin-type scripts give 2- and 3-grams
    and their non-ASCII letters (ö ş ı ñ é carry the language); Han and kana, written without spaces, give
    characters and character pairs."""
    c: Counter = Counter(); sc: Counter = Counter()
    for t in texts:
        for w in _letters(t).split():
            scripts = [_script(ch) for ch in w]
            sc.update(scripts)
            if any(x in ("HAN", "HIRAGANA", "KATAKANA") for x in scripts):
                c.update(w); c.update(w[i:i + 2] for i in range(len(w) - 1)); continue
            c.update(ch for ch in w if ord(ch) > 127); c.update(ch for ch in w if ord(ch) > 127)
            w2 = f"<{w}>"
            for n in (2, 3):
                c.update(w2[i:i + n] for i in range(len(w2) - n + 1))
    return c, sc


def _unit(c: dict) -> dict[str, float]:
    n = math.sqrt(sum(v * v for v in c.values())) or 1.0
    return {k: v / n for k, v in c.items()}


def cos(a: dict[str, float] | None, b: dict[str, float] | None) -> float | None:
    if not a or not b:
        return None
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


class Lang:
    """Language similarity among the artists of one session, learned from their own titles: n-grams weighted
    by how rare they are among these artists (TF-IDF), and scripts weighted by how distinctive they are here
    (Latin is shared by almost everyone, Hangul or Han by few). Nothing is listed by hand."""
    def __init__(self, raw: dict[str, tuple[Counter, Counter]]):
        self.names = [n for n, (g, _) in raw.items() if g]
        N = max(1, len(self.names)); df: Counter = Counter(); sdf: Counter = Counter()
        for n in self.names:
            df.update(set(raw[n][0])); sdf.update(set(raw[n][1]))
        idf = {k: math.log((N + 1) / (1 + v)) + 1 for k, v in df.items()}
        self.V = {n: _unit({g: c * idf[g] for g, c in raw[n][0].items()}) for n in self.names}
        self.S = {n: {k: v / (sum(raw[n][1].values()) or 1) for k, v in raw[n][1].items()} for n in self.names}
        self.distinct = {k: 1 - v / N for k, v in sdf.items()}

    def group(self, names: list[str]) -> tuple[dict[str, float], dict[str, float]] | None:
        names = [n for n in names if n in self.V]
        if not names:
            return None
        c: Counter = Counter(); s: Counter = Counter()
        for n in names:
            c.update(self.V[n]); s.update(self.S[n])
        return _unit(c), {k: v / len(names) for k, v in s.items()}

    def sim(self, name: str, grp: tuple[dict[str, float], dict[str, float]] | None) -> float | None:
        if name not in self.V or not grp:
            return None
        ng = cos(self.V[name], grp[0]) or 0.0
        sc = sum(min(v, grp[1].get(k, 0.0)) * self.distinct.get(k, 0.0) for k, v in self.S[name].items())
        return round(max(ng, sc), 3)


def titles(name: str, network: bool = True) -> list[str]:
    """The artist's own song titles (and name), the raw material of the language fingerprint."""
    if not network:
        return []
    try:
        return (prev.titles(name, 30) or [t.get("title") or "" for t in prev.previews(name, 8)]) + [name]
    except Exception:  # noqa: BLE001
        return []


# ------------------------------------------------------------------ places
_inflight: set[str] = set()
_ilock = threading.Lock()


def _cached_info(name: str) -> tuple[bool, dict]:
    """(complete in the cache?, what the cache has). An entry made for the tour has no languages yet."""
    v = tour.mb_info(name, network=False)
    return (v is not None and not (v.get("mbid") and v.get("langs") is None)), (v or {})


def places(names: list[str], budget_s: float = 4.0, network: bool = True) -> dict[str, dict]:
    """name -> {"cc", "country", "city"} ({} when unknown). Looks up what it can within the budget and keeps
    looking in the background for the rest."""
    out: dict[str, dict] = {}
    todo = []
    for n in names:
        known, v = _cached_info(n)
        if known:
            out[n] = v
        else:
            todo.append(n)
    if todo and network:
        with _ilock:
            fresh = [n for n in todo if n.lower() not in _inflight]
            for n in fresh:
                _inflight.add(n.lower())

        def run(batch: list[str]) -> None:
            for n in batch:
                try:
                    tour.mb_info(n)
                finally:
                    with _ilock:
                        _inflight.discard(n.lower())
        import time as _time
        deadline = _time.monotonic() + max(0.0, budget_s)
        if fresh:
            threading.Thread(target=run, args=(fresh,), daemon=True).start()
        # wait for every name, ours or one another request is already looking up, until the budget runs out
        while _time.monotonic() < deadline and not all(_cached_info(n)[0] for n in todo):
            with _ilock:
                busy = any(n.lower() in _inflight for n in todo)
            if not busy:
                break
            _time.sleep(0.15)
    for n in todo:
        known, v = _cached_info(n)
        out[n] = v                      # partial is still useful: the country without the languages
    return out


def countries(names: list[str], budget_s: float = 4.0, network: bool = True) -> dict[str, str | None]:
    return {n: (v or {}).get("cc") for n, v in places(names, budget_s, network).items()}


def warm(names: list[str]) -> None:
    """Look these artists up in the background (no waiting)."""
    names = [n for n in names if n]
    if names:
        threading.Thread(target=places, args=(names, 300.0), daemon=True).start()


def profiles(names: list[str], budget_s: float = 4.0, network: bool = True) -> dict[str, dict[str, Any]]:
    """name -> {"cc", "country", "city", "grams"}: where the artist is from and how their titles read."""
    names = [n for n in dict.fromkeys(names) if n]
    if not names:
        return {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        raw = dict(zip(names, ex.map(lambda n: grams(titles(n, network)), names)))
    pl = places(names, budget_s, network)
    return {n: {**(pl.get(n) or {}), "grams": raw.get(n) or (Counter(), Counter())} for n in names}


# ------------------------------------------------------------------ the person's lens
def key_of(p: dict[str, Any]) -> str | None:
    """An artist's culture: the main language of their releases when MusicBrainz knows it, else their country."""
    langs = (p or {}).get("langs") or {}
    if langs:
        return "lang:" + max(langs, key=langs.get)
    return ("cc:" + p["cc"]) if (p or {}).get("cc") else None


def lens(fav_names: list[str], P: dict[str, dict], lang: Lang | None = None) -> dict[str, Any]:
    """The favourites' cultures, measured: {"dominant": key, "share", "counts": {key: n}, "of": {name: key},
    "ccs": countries of the favourites, "city": where Qloo's location signal should look,
    "groups": {key: language group of their titles}, "specialist": 0..1}."""
    of = {n: key_of(P.get(n) or {}) for n in fav_names}
    counts: dict[str, int] = {}
    for c in of.values():
        if c:
            counts[c] = counts.get(c, 0) + 1
    known = sum(counts.values()); total = max(1, len(fav_names))
    dom = max(counts, key=counts.get) if counts else None
    share = counts[dom] / total if dom else 0.0           # over ALL favourites: an artist not yet looked up still counts
    groups = {k: lang.group([n for n in fav_names if of.get(n) == k]) for k in counts} if lang else {}
    if len(counts) > 1:
        ps = [v / known for v in counts.values()]
        spec = 1 - (-sum(p * math.log(p) for p in ps) / math.log(len(ps)))
    else:
        spec = 1.0 if counts else 0.0
    ccs = {(P.get(n) or {}).get("cc"): of.get(n) for n in fav_names if (P.get(n) or {}).get("cc")}
    dom_names = [n for n in fav_names if of.get(n) == dom]
    cities = Counter((P.get(n) or {}).get("city") for n in dom_names if (P.get(n) or {}).get("city"))
    city, nc = (cities.most_common(1)[0] if cities else (None, 0))
    country = Counter((P.get(n) or {}).get("country") for n in dom_names if (P.get(n) or {}).get("country")).most_common(1)
    country = country[0][0] if country else None
    dom_cc = Counter((P.get(n) or {}).get("cc") for n in dom_names if (P.get(n) or {}).get("cc")).most_common(1)
    return {"dominant": dom, "share": round(share, 2), "counts": counts, "of": of, "known": known, "country": country, "cc": dom_cc[0][0] if dom_cc else None,
            "ccs": ccs, "city": city if nc >= 2 else (country or city), "groups": {k: v for k, v in groups.items() if v}, "specialist": round(spec, 2), "name": country, "total": total, "coverage": round(known / total, 2)}


def match(name: str, cand: dict[str, Any], L: dict[str, Any], lang: Lang | None) -> tuple[str | None, float | None, float | None]:
    """(the person's culture this candidate belongs to or None, title-language similarity, agreement 1/0/None).
    Agreement comes from data in this order: the language of the candidate's releases (MusicBrainz), its
    country (MusicBrainz), and the language of its song titles. A Mexican and a Colombian singer share
    Spanish, a Taiwanese and a Singaporean Mandopop singer share Mandarin, Persian and Turkish do not."""
    counts = L.get("counts") or {}
    sims = {k: lang.sim(name, g) for k, g in (L.get("groups") or {}).items()} if lang else {}
    sims = {k: v for k, v in sims.items() if v is not None}
    best = max(sims, key=sims.get) if sims else None
    k = key_of(cand)
    if k and k in counts:
        return k, sims.get(k), 1.0
    cc = cand.get("cc")
    if cc and cc in (L.get("ccs") or {}) and not (cand.get("langs")):
        g = L["ccs"][cc]; return g, sims.get(g), 1.0
    if best and sims[best] >= 0.35:
        return best, sims[best], 1.0 if not k else 0.5
    if k:
        return None, (sims.get(best) if best else None), 0.0
    return None, (sims.get(best) if best else None), None


def name_of(cc: str | None) -> str:
    return cc or ""


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()
