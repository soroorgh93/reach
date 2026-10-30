"""Self-check: tests every outside source Reach depends on from THIS machine and writes a
report you can send back. Run from the reach folder with the key set:

    set PYTHONUTF8=1 / $env:PYTHONUTF8="1"
    python scripts/selfcheck.py

It prints PASS / FAIL per source and writes selfcheck_report.json next to this file.
Nothing personal is included in the report (no key, no face, no voice): only status codes,
timings, counts and the first names returned.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reach import sources, previews, fullsong
from reach.qloo import QlooClient, QlooError

report: dict = {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "python": sys.version.split()[0], "checks": []}


def check(name: str, fn):
    t0 = time.time()
    try:
        out = fn()
        ok = bool(out)
        detail = out if isinstance(out, (str, int, float)) else (out[:5] if isinstance(out, list) else out)
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"{type(e).__name__}: {e}"
    ms = round((time.time() - t0) * 1000)
    print(f"{'PASS' if ok else 'FAIL'}  {name:34s} {ms:6d} ms  {str(detail)[:110]}")
    report["checks"].append({"name": name, "ok": ok, "ms": ms, "detail": detail if isinstance(detail, (str, int, float, list, dict)) else str(detail)})


def main() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    key = os.environ.get("QLOO_API_KEY", "")
    print("Qloo key present:", bool(key))
    client = QlooClient(offline=not key)
    if key:
        check("qloo insights (artist)", lambda: [e["name"] for e in client.insights("artist", entities=["4BBEF799-A0C4-4110-AB01-39216993C312"], take=3, label="selfcheck")])
        check("qloo search 'shakira' (any type)", lambda: [f"{r.get('name')} {[t.split(':')[-1] for t in (r.get('types') or [])][:1]}" for r in client.search("shakira", None, take=5)])
        check("qloo search 'hayedeh'", lambda: [r.get("name") for r in client.search("hayedeh", None, take=5)])
        check("qloo podcast affinities", lambda: [e["name"] for e in client.insights("podcast", entities=["B4D6B6FD-7146-4E1C-AE48-B8EBD2BB71DA"], take=3, label="selfcheck.pod")])
        check("qloo movies (child-rated)", lambda: [e["name"] for e in client.insights("movie", entities=["D727CF74-F6CA-4A80-90E2-CF2F109D2315"], take=3, label="selfcheck.movie", **{"filter.content_rating": "G,PG,TV-Y,TV-Y7,TV-G,TV-PG"})])
        check("qloo genre-tag filter (ambient)", lambda: [e["name"] for e in client.insights("artist", entities=["4BBEF799-A0C4-4110-AB01-39216993C312"], take=3, label="selfcheck.tag", **{"filter.tags": "urn:tag:genre:music:ambient,urn:tag:genre:music:classical", "operator.filter.tags": "union"})])
        check("qloo location signal (Rome)", lambda: [e["name"] for e in client.insights("artist", take=4, label="selfcheck.tour", **{"signal.location.query": "Rome"})])
        check("qloo genre tag only (techno)", lambda: [e["name"] for e in client.insights("artist", tags=["urn:tag:genre:music:techno"], take=4, label="selfcheck.genre")])
        check("qloo places near a city (parks, San Jose)", lambda: [f"{e.get('name')} {__import__('reach.after', fromlist=['suffixes']).suffixes(e)[:3]}" for e in (client.get("/v2/insights", {"filter.type": "urn:entity:place", "take": 4, "signal.interests.entities": ["4BBEF799-A0C4-4110-AB01-39216993C312"], "filter.location.query": "San Jose", "filter.tags": "urn:tag:category:place:park,urn:tag:category:place:library", "operator.filter.tags": "union"}, label="selfcheck.places")["data"].get("results") or {}).get("entities", [])])
        def tag_shape():
            d = client.get("/v2/insights", {"filter.type": "urn:entity:place", "take": 1, "filter.location.query": "San Jose", "filter.tags": "urn:tag:category:place:park"}, label="selfcheck.places.shape")["data"]
            e = ((d.get("results") or {}).get("entities") or [{}])[0]
            tags = e.get("tags") or []
            return {"tag_keys": sorted({k for t in tags if isinstance(t, dict) for k in t}), "first_tags": tags[:3], "has_geocode": bool((e.get("properties") or {}).get("geocode") or e.get("location")),
                    "centroid": bool(((d.get("query") or {}).get("localities") or {}).get("filter"))}
        check("qloo place tag shape (for After the music)", tag_shape)
        check("qloo persian restaurants (San Jose)", lambda: [e.get("name") for e in (client.get("/v2/insights", {"filter.type": "urn:entity:place", "take": 4, "filter.location.query": "San Jose", "filter.tags": "urn:tag:category:place:persian_restaurant"}, label="selfcheck.food")["data"].get("results") or {}).get("entities", [])])
        check("qloo books from taste", lambda: [e["name"] for e in client.insights("book", entities=["4BBEF799-A0C4-4110-AB01-39216993C312"], take=3, label="selfcheck.book")])
        check("after the music (calm, San Jose)", lambda: (lambda d: {"places": [x["name"] for x in d["places"]], "food": [x["name"] for x in d["food"]], "read": [x["name"] for x in d["read"]], "centre": d.get("centre")})(
            __import__("reach.after", fromlist=["after"]).after(client, {"id": "selfcheck", "city": "San Jose", "age": 30, "favorites": [{"name": "Taylor Swift", "type": "artist", "entity_id": "4BBEF799-A0C4-4110-AB01-39216993C312"}]}, "calm")))
        check("qloo tag profile", lambda: [t.get("name") for t in client.insights("urn:tag", entities=["4BBEF799-A0C4-4110-AB01-39216993C312"], take=5, label="selfcheck.tags", **{"filter.tag.types": "urn:tag:genre:music,urn:tag:style:music,urn:tag:mood:music"})])
    check("deezer artist suggest 'shak'", lambda: [a["name"] for a in sources.suggest_artists("shak")])
    check("deezer artist suggest 'hayedeh'", lambda: [a["name"] for a in sources.suggest_artists("hayedeh")])
    check("deezer/itunes previews (Shakira)", lambda: [f"{t['title']} [{t['source']}]" for t in previews.previews("Shakira", 3)])
    check("internet archive soundscape (ocean)", lambda: [f"{t['title'][:40]} {t.get('duration')}s" for t in sources.soundscape("ocean", 3)])
    check("internet archive soundscape (bowls)", lambda: [f"{t['title'][:40]} {t.get('duration')}s" for t in sources.soundscape("bowls", 2)])
    check("itunes podcast + rss (Radiolab)", lambda: [f"{t['artist']}: {t['title'][:50]} {t.get('duration')}s" for t in sources.podcast_episodes("Radiolab", 1)])
    check("internet archive soundscape (rain, no speech)", lambda: [f"{t['title'][:40]} {t.get('duration')}s" for t in sources.soundscape("rain", 3)])
    check("itunes podcast meditation (es)", lambda: [f"{t['artist']}: {t['title'][:50]}" for t in sources.podcast_episodes("meditación guiada", 1, lang="es")])

    # the cultural lens: MusicBrainz place + release language, Deezer titles for the language fingerprint
    from reach import tour as _tour, culture as _culture, dialogue as _dialogue
    check("musicbrainz place + language (Hayedeh)", lambda: _tour.mb_info("Hayedeh"))
    check("musicbrainz place + language (Jay Chou)", lambda: _tour.mb_info("Jay Chou"))
    check("deezer titles for the fingerprint (Kalben)", lambda: previews.titles("Kalben", 10))
    def lens_probe():
        names = ["Hayedeh", "Dariush", "Marzieh", "Gloria Gaynor"]
        P = _culture.profiles(names + ["Googoosh", "Kalben"], budget_s=20)
        lang = _culture.Lang({n: P[n]["grams"] for n in P}); L = _culture.lens(names, P, lang)
        return {"dominant": L["dominant"], "share": L["share"], "city": L["city"],
                "Googoosh": _culture.match("Googoosh", P["Googoosh"], L, lang), "Kalben": _culture.match("Kalben", P["Kalben"], L, lang)}
    check("cultural lens (Persian favourites)", lens_probe)
    print("Conversation model:", _dialogue.status())
    if _dialogue.providers():
        check("conversation model answers", lambda: _dialogue.turn("I said Hayedeh, why another singer?", {"lang": "en", "favourites": ["Hayedeh"], "now": {"artist": "Kalben", "own": False, "because": "Hayedeh"}}))
    print("YouTube key present:", fullsong.enabled())
    if fullsong.enabled():
        check("youtube full song (Googoosh, Pol)", lambda: (fullsong.find("Googoosh", "Pol") or {}).get("title") or "")
        check("youtube refuses a wrong artist (Kalben, Kalyo Kood Padyo Mela)", lambda: "refused" if fullsong.find("Kalben", "Kalyo Kood Padyo Mela") is None else "MATCHED (bad)")
        check("youtube oembed (tour video title)", lambda: __import__("reach.tour", fromlist=["oembed"]).oembed("UnQdyUaohic") and __import__("reach.tour", fromlist=["oembed"]).oembed("UnQdyUaohic").get("title"))

    def stream_probe():
        tr = previews.previews("Shakira", 1) or sources.soundscape("rain", 1)
        if not tr:
            return "no track to probe"
        u = tr[0]["preview"]
        if not previews.allowed(u):
            return f"host not allowed: {u[:60]}"
        r = previews.open_stream(u)
        chunk = r.read(32 * 1024); r.close()
        return f"{len(chunk)} bytes, {r.headers.get('Content-Type')}"
    check("audio stream proxy (first 32 KB)", stream_probe)
    out = ROOT / "scripts" / "selfcheck_report.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    fails = [c["name"] for c in report["checks"] if not c["ok"]]
    print("\nwrote", out)
    print("FAILED:", ", ".join(fails) if fails else "none")


if __name__ == "__main__":
    main()
