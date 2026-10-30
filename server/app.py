"""Reach API (Starlette + uvicorn). Serves the web app from ./web.

  GET  /api/health                     key present, Qloo reachable, mode
  GET  /api/personas                   demo profiles
  GET  /api/protocols                  protocol registry (evidence, safety)
  POST /api/session                    {persona_id | profile, request:{text, goal, face, voice, consent, lang, local_hour}}
  GET  /api/session/stream?persona=&req=<url-encoded JSON request>   SSE trace of the council
  POST /api/adapt                      {session, mood, elapsed_s} -> adjustments (ISO principle)
  POST /api/verify                     {ledger} -> hash-chain verification
  GET  /api/resolve?q=&type=           favourite -> Qloo entity id (server side; key never leaves)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_env_file(path: Path) -> None:
    """Optional local .env (git-ignored): KEY=VALUE lines for QLOO_API_KEY, YOUTUBE_API_KEY, ...
    Values already set in the environment win. Nothing here is ever logged or sent to the browser."""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and not os.environ.get(k):
                os.environ[k] = v
    except OSError:
        pass


_load_env_file(ROOT / ".env")

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse, FileResponse, Response
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from reach.agent import ReachCouncil, protocols
from reach.ledger import Ledger
from reach.qloo import QlooClient, QlooError, ENTITY_TYPES
from reach import previews as prev
from reach import sources
from reach import fullsong
from reach.tour import TOUR, tour_for, warm as tour_warm, public as tour_public, add_video, load_media, video_id, oembed, match_city
from reach.compare import compare as compare_fn
from reach.rag import retrieve
from reach import dialogue, culture
from reach import after as after_mod
from reach import mcp as mcp_mod

PERSONAS = json.loads((ROOT / "data" / "personas.json").read_text(encoding="utf-8"))["personas"]
CLIENT = QlooClient()
COUNCIL = ReachCouncil(CLIENT)
STARTED = time.time()
RESOLVED: dict[str, str] = {}
MAX_BODY = 64 * 1024


def persona(pid: str) -> dict | None:
    for p in PERSONAS:
        if p["id"] == pid:
            return json.loads(json.dumps(p))
    return None


def resolve_missing(profile: dict) -> dict:
    if CLIENT.offline:
        return profile
    for f in profile.get("favorites", []):
        if not f.get("entity_id") and f.get("name"):
            k = f"{f.get('type')}|{f['name'].lower()}"
            if k not in RESOLVED:
                try:
                    r = CLIENT.resolve(f["name"], f.get("type", "artist"))
                    RESOLVED[k] = r["entity_id"] if r else ""
                except QlooError:
                    RESOLVED[k] = ""
            if RESOLVED[k]:
                f["entity_id"] = RESOLVED[k]
    return profile


async def read_json(request: Request) -> dict:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise ValueError("body too large")
    return json.loads(raw or b"{}")


async def health(request: Request) -> Response:
    out = {"ok": True, "uptime_s": round(time.time() - STARTED), "key_present": bool(CLIENT.api_key),
           "mode": "fixture" if CLIENT.offline else "live", "protocols": len(protocols()["protocols"]),
           "fixtures": len(CLIENT._load_fixtures().get("calls", {})), "personas": len(PERSONAS), "qloo": None,
           "narrator": "template", "youtube": fullsong.enabled(), "conversation": dialogue.status(),
           "repo": os.environ.get("REACH_REPO_URL") or None, "version": "round12"}
    if not CLIENT.offline:
        try:
            r = CLIENT.get("/v2/insights", {"filter.type": "urn:entity:artist", "take": 1,
                                            "signal.interests.entities": PERSONAS[0]["favorites"][0]["entity_id"]}, label="health")
            out["qloo"] = {"status": r["status"], "ms": r["ms"], "source": r["source"]}
            out["ok"] = r["status"] == 200
        except QlooError as e:
            out["qloo"] = {"error": str(e)}; out["ok"] = False
    return JSONResponse(out)


async def personas(request: Request) -> Response:
    return JSONResponse({"personas": PERSONAS})


async def protocols_route(request: Request) -> Response:
    return JSONResponse(protocols())


def _inputs(body: dict, qp) -> tuple[dict, dict]:
    pid = body.get("persona_id") or qp.get("persona")
    prof = body.get("profile")
    if not prof and qp.get("profile"):
        prof = json.loads(qp.get("profile"))
    if not prof and pid:
        prof = persona(pid)
    if not prof or not isinstance(prof, dict):
        raise ValueError("persona_id or profile required")
    if len(json.dumps(prof)) > 8000:
        raise ValueError("profile too large")
    prof.setdefault("id", pid or "custom")
    req = body.get("request") or {}
    if not req and qp.get("req"):
        req = json.loads(qp.get("req"))
    if not isinstance(req, dict):
        raise ValueError("request must be an object")
    return resolve_missing(prof), req


async def session(request: Request) -> Response:
    try:
        prof, req = _inputs(await read_json(request), request.query_params)
    except (ValueError, json.JSONDecodeError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(COUNCIL.compose_once(prof, req))


async def stream(request: Request) -> Response:
    try:
        prof, req = _inputs({}, request.query_params)
    except (ValueError, json.JSONDecodeError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    def gen():
        for e in COUNCIL.run(prof, req, stream_delay=0.08):
            yield f"event: {e['kind']}\ndata: {json.dumps(e, default=str)}\n\n"
        yield "event: done\ndata: {}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def adapt(request: Request) -> Response:
    try:
        body = await read_json(request)
        out = ReachCouncil.adapt(body["session"], body.get("mood", {}), float(body.get("elapsed_s", 0)))
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
        return JSONResponse({"error": f"bad request: {e}"}, status_code=400)
    return JSONResponse(out)


async def verify(request: Request) -> Response:
    body = await read_json(request)
    return JSONResponse(Ledger.verify_entries(body.get("ledger", [])))


async def resolve(request: Request) -> Response:
    q = request.query_params.get("q", "").strip()[:80]
    t = request.query_params.get("type", "any")
    if not q or (t != "any" and t not in ENTITY_TYPES):
        return JSONResponse({"error": "q and a valid type required"}, status_code=400)
    if CLIENT.offline:
        return JSONResponse({"results": [], "mode": "fixture"})
    types = ["artist", "movie", "tv_show", "book", "video_game", "podcast"] if t == "any" else [t]
    try:
        res = CLIENT.search(q, types, take=6)
    except QlooError as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    out = []
    for r in res:
        rtypes = r.get("types") or []
        kind = next((k for k in types if any(f"urn:entity:{k}" == x for x in rtypes)), types[0])
        out.append({"name": r.get("name"), "entity_id": r.get("entity_id"), "type": kind})
    return JSONResponse({"results": out})


def preview_route(request: Request) -> Response:
    """GET /api/preview?artist=Name -> up to 4 thirty-second preview tracks (Deezer, then iTunes)."""
    artist = request.query_params.get("artist", "").strip()[:80]
    if not artist:
        return JSONResponse({"error": "artist required"}, status_code=400)
    try:
        limit = max(1, min(10, int(request.query_params.get("limit", "4"))))
    except ValueError:
        limit = 4
    tracks = [dict(t) for t in prev.previews(artist, limit)]
    for t in tracks:
        t["stream"] = "/api/preview/stream?u=" + __import__("urllib.parse").parse.quote(t["preview"], safe="")
    return JSONResponse({"artist": artist, "tracks": tracks})


def preview_stream(request: Request) -> Response:
    """Proxies one allow-listed preview file so Web Audio can process it as same-origin media."""
    u = request.query_params.get("u", "")
    if not prev.allowed(u):
        return JSONResponse({"error": "host not allowed"}, status_code=400)
    try:
        resp = prev.open_stream(u)
    except Exception as e:
        return JSONResponse({"error": f"upstream: {e}"}, status_code=502)
    ctype = resp.headers.get("Content-Type", "audio/mpeg")

    def gen():
        try:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            resp.close()
    return StreamingResponse(gen(), media_type=ctype, headers={"Cache-Control": "public, max-age=86400", "Accept-Ranges": "none"})


def suggest(request: Request) -> Response:
    """Autocomplete for favourites: Qloo entities (any type) merged with Deezer/iTunes artists worldwide."""
    q = request.query_params.get("q", "").strip()[:80]
    if len(q) < 2:
        return JSONResponse({"results": []})
    out: list[dict] = []
    seen: set[str] = set()
    ql = q.lower()
    # genres and moods are tags, not artists ("techno", "k-pop", "lo-fi")
    for word, tag in GENRES.items():
        if word.startswith(ql) or ql in word:
            out.append({"name": word.title() if len(word) > 3 else word.upper(), "entity_id": None, "type": "genre", "tag": "urn:tag:genre:music:" + tag, "source": "qloo"})
    # world catalogue of artists first (Deezer/iTunes): this is where Hayedeh, Pitbull and Ebru Gündeş live
    artists = sources.suggest_artists(q)
    qloo_rows: list[dict] = []
    if not CLIENT.offline:
        try:
            for r in CLIENT.search(q, None, take=8):
                rtypes = r.get("types") or []
                kind = next((k for k in ("artist", "movie", "tv_show", "book", "video_game", "podcast") if any(f"urn:entity:{k}" == x for x in rtypes)), None)
                if not kind:
                    continue      # albums, people, places: not favourites Reach uses
                qloo_rows.append({"name": r.get("name"), "entity_id": r.get("entity_id"), "type": kind, "source": "qloo"})
        except QlooError:
            pass
    # one ranked list: exact names first, popular things before obscure namesakes. "Harry Potter" the
    # book or film must beat a little-known Deezer artist called "Harry Potter".
    import math
    def closeness(name: str) -> float:
        n = (name or "").lower()
        return 1.0 if n == ql else 0.5 if n.startswith(ql) else 0.15 if ql in n else 0.0
    exact_non_artist = {(r["name"] or "").lower() for r in qloo_rows if r["type"] != "artist"}
    by_name = {(r["name"] or "").lower(): r for r in qloo_rows if r["type"] == "artist"}
    scored: list[tuple[float, dict]] = [(2.0 + closeness(r["name"]), r) for r in out]          # genres typed by name
    for i, r in enumerate(qloo_rows):
        if r["type"] == "artist" and (r["name"] or "").lower() in {(a.get("name") or "").lower() for a in artists}:
            continue                                                                        # merged with its Deezer row below
        scored.append((1.0 + closeness(r["name"]) + 0.6 * (1 - i / 8), r))
    for a in artists:
        name = a.get("name") or ""; key = name.lower()
        if key + "|artist" in seen:
            continue
        seen.add(key + "|artist")
        fans = a.get("fans") or 0; hit = by_name.get(key)
        sc = closeness(name) + min(1.1, math.log10(fans + 1) / 6.5) + (0.6 if hit else 0)
        if key in exact_non_artist and fans < 50000:
            sc -= 1.6                                                                       # a namesake, not the thing they meant
        scored.append((sc, {"name": name, "entity_id": hit["entity_id"] if hit else None, "type": "artist", "source": ("qloo+" if hit else "") + a["source"], "image": a.get("image"), "fans": fans}))
    scored.sort(key=lambda x: -x[0])
    out = []; seen2: set[str] = set()
    for _, r in scored:
        k = (r["name"] or "").lower() + "|" + r["type"]
        if k not in seen2:
            seen2.add(k); out.append(r)
    return JSONResponse({"results": out[:10], "mode": "fixture" if CLIENT.offline else "live"})


GENRES = {"techno": "techno", "house": "house", "edm": "edm", "trance": "trance", "rock": "rock", "metal": "metal", "pop": "pop", "jazz": "jazz", "classical": "classical",
          "hip hop": "hip_hop", "rap": "hip_hop", "r&b": "r_b", "soul": "soul", "blues": "blues", "folk": "folk", "country": "country", "reggae": "reggae", "reggaeton": "reggaeton",
          "latin": "latin", "salsa": "salsa", "bachata": "bachata", "flamenco": "flamenco", "k-pop": "k_pop", "j-pop": "j_pop", "c-pop": "mandopop", "bollywood": "bollywood",
          "indian classical": "indian_classical", "persian": "persian", "arabic": "arabic", "turkish": "turkish", "afrobeats": "afrobeats", "amapiano": "amapiano", "ambient": "ambient",
          "lo-fi": "lo_fi", "lofi": "lo_fi", "instrumental": "instrumental", "indie": "indie", "punk": "punk", "disco": "disco", "funk": "funk", "gospel": "gospel", "opera": "opera", "new age": "new_age",
          "meditation": "new_age", "soundtrack": "soundtrack", "anime": "anime", "electronic": "electronic", "dance": "dance", "drill": "drill", "trap": "trap", "dubstep": "dubstep", "drum and bass": "drum_and_bass"}


def soundscape_route(request: Request) -> Response:
    kind = request.query_params.get("kind", "ocean").strip()[:40]
    tracks = sources.soundscape(kind)
    for t in tracks:
        t["stream"] = "/api/preview/stream?u=" + __import__("urllib.parse").parse.quote(t["preview"], safe="")
    return JSONResponse({"kind": kind, "tracks": tracks, "kinds": list(sources.SOUNDSCAPES)})


GOAL_TOPICS = {
    "sleep": {"en": ["sleep stories", "bedtime stories for adults"], "es": ["cuentos para dormir", "relajación para dormir"], "fa": ["داستان خواب", "مدیتیشن خواب"], "zh": ["睡前故事", "助眠"]},
    "calm": {"en": ["meditation", "mindfulness"], "es": ["meditación guiada", "mindfulness"], "fa": ["مدیتیشن", "آرامش"], "zh": ["冥想", "正念"]},
    "autism_calm": {"en": ["stories for kids", "calm kids meditation"], "es": ["cuentos infantiles", "meditación para niños"], "fa": ["قصه کودکانه", "قصه شب"], "zh": ["儿童故事", "睡前故事"]},
    "focus": {"en": ["deep work", "productivity"], "es": ["productividad", "concentración"], "fa": ["تمرکز", "بهره وری"], "zh": ["专注", "效率"]},
    "energy": {"en": ["motivation", "morning motivation"], "es": ["motivación", "energía"], "fa": ["انگیزشی", "موفقیت"], "zh": ["励志", "早安"]},
    "mood": {"en": ["uplifting stories", "comedy"], "es": ["historias que inspiran", "humor"], "fa": ["داستان", "طنز"], "zh": ["治愈", "喜剧"]},
    "memory": {"en": ["history stories", "nostalgia"], "es": ["historia", "nostalgia"], "fa": ["تاریخ", "خاطره"], "zh": ["历史故事", "怀旧"]},
}


def podcast_route(request: Request) -> Response:
    """A podcast collection built for this person, shown as a choice list (one card per show):
    1. a topic they asked for ("podcasts about history"),
    2. shows about the artists they love,
    3. shows in their artists' culture and language (the cultural lens: Persian music podcasts for Hayedeh),
    4. what Qloo says this audience follows, through the same lens (location signal), then in general,
    5. shows for what they need now (the session's goal), in their language and their culture's language.
    Shows they heard recently go to the back, so a new request brings a new collection."""
    import random
    from concurrent.futures import ThreadPoolExecutor
    term = request.query_params.get("q", "").strip()[:80]
    lang = request.query_params.get("lang", "en"); goal = request.query_params.get("goal", "calm")
    heard = set(request.query_params.get("heard", "").split("|")) - {""}
    heard_shows = [x for x in request.query_params.get("shows", "").split("|") if x][:16]
    prof = None
    if request.query_params.get("profile") or request.query_params.get("persona"):
        try:
            prof, _ = _inputs({}, request.query_params)
        except (ValueError, json.JSONDecodeError) as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    from reach.taste import favourite_ids
    queries: list[tuple[str, int, str, str, str]] = []          # (term, shows, why, about, lang)
    if term:
        queries.append((term, 4, "topic", term, lang))
    lens = {}
    fav_names: list[str] = []
    if prof:
        favs = [f for f in (prof.get("favorites") or []) if f.get("name")]
        fav_names = [f["name"] for f in favs]
        ids = favourite_ids(prof)
        # what the person's artists sing and their films are: the genres Qloo attaches to them
        def genres(ftype_tags: str, label: str) -> list[str]:
            try:
                rows = CLIENT.insights("urn:tag", entities=ids, take=12, label=label, **{"filter.tag.types": ftype_tags})
            except QlooError:
                return []
            out = []
            for t in rows:
                nm = str(t.get("name") or "").strip()
                if nm and nm.lower() not in {x.lower() for x in out} and len(nm) < 40:
                    out.append(nm)
            return out
        if ids:
            if any(f.get("type") == "artist" for f in favs):
                for g in genres("urn:tag:genre:music", f"{prof.get('id', 'p')}.podcast.genres.music")[:3]:
                    queries.append((f"{g} music", 2, "genre", g, lang))
            if any(f.get("type") in ("movie", "tv_show", "book") for f in favs):
                for g in genres("urn:tag:genre:media", f"{prof.get('id', 'p')}.podcast.genres.media")[:2]:
                    queries.append((f"{g} movies", 2, "film_genre", g, lang))
        # shows about the very things they love (kept only if the show itself is about them, see below)
        for f in favs[:5]:
            queries.append((f["name"], 2, "fav", f["name"], lang))
        if ids:
            extra = {"filter.exclude.tags": "urn:tag:genre:podcast:true_crime"} if (prof.get("age") or 30) < 16 else {}
            try:
                general = CLIENT.insights("podcast", entities=ids, take=10, label=f"{prof.get('id', 'p')}.podcasts", **extra)
            except QlooError:
                general = []
            for e in general[:5]:
                if e.get("name") and e["name"] not in {q[0] for q in queries}:
                    queries.append((e["name"], 1, "qloo", "", lang))
    for t in GOAL_TOPICS.get(goal, GOAL_TOPICS["calm"]).get(lang, GOAL_TOPICS.get(goal, GOAL_TOPICS["calm"])["en"]):
        queries.append((t, 2, "goal", goal, lang))
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda q: (q, sources.podcast_shows(q[0], q[1], q[4])), queries))
    rng = random.Random()
    seen: set[str] = set(); shows = []
    import statistics, unicodedata
    def nrm(x: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFKD", x or "") if not unicodedata.combining(c)).lower()
    # never offered unless asked for by topic: news and politics, religion, true crime, business, sport
    BLOCK = ("news", "politic", "government", "true crime", "religion", "christian", "islam", "judaism", "hinduism", "buddhism", "business", "investing", "sports")
    for (q, _, why, about, _l), found in results:
        for sh in found:
            name = sh.get("show")
            if not name or name in seen or not sh.get("episodes"):
                continue
            g = " ".join([sh.get("genre") or ""] + list(sh.get("genres") or [])).lower()
            if why != "topic" and any(b in g for b in BLOCK) and not (why == "goal" and "spiritual" in g):
                continue
            durs = [e.get("duration") or 0 for e in sh["episodes"] if e.get("duration")]
            if durs and statistics.median(durs) < 9 * 60 and "music" in g:
                continue                    # a feed of songs dressed as a podcast, not a podcast
            if why == "fav" and nrm(about) not in nrm(" ".join([name, sh.get("author") or "", sh.get("desc") or ""])):
                continue                    # matched on one episode title only: not a show about this artist
            seen.add(name)
            fresh = [e for e in sh["episodes"] if f"{e['artist']}|{e['title']}" not in heard] or sh["episodes"]
            eps = fresh[:8]; rng.shuffle(eps)
            shows.append({"show": name, "cover": sh["episodes"][0].get("cover"), "genre": sh.get("genre"), "why": why, "about": about,
                          "episodes": [dict(e, because_code=why, because_about=about, show=name) for e in eps[:4]]})
    # order: asked-for topic, their artists, their culture, Qloo through their culture, their need, Qloo in general;
    # within that, shows not heard recently first
    rank = {"topic": 0, "fav": 1, "genre": 2, "film_genre": 2, "qloo": 3, "goal": 4}
    shows.sort(key=lambda x: (x["show"] in heard_shows, rank.get(x["why"], 9)))
    shows = shows[:8]
    for sh in shows:
        for t in sh["episodes"]:
            t["stream"] = "/api/preview/stream?u=" + __import__("urllib.parse").parse.quote(t["preview"], safe="")
    tracks = [sh["episodes"][0] for sh in shows]
    return JSONResponse({"q": term, "shows": shows, "tracks": tracks, "lens": lens.get("name") if lens else None})


async def compare_route(request: Request) -> Response:
    """Without Qloo: generic list vs the council's carrier, measured by affinity to this person."""
    try:
        body = await read_json(request)
        prof, _ = _inputs(body, request.query_params)
    except (ValueError, json.JSONDecodeError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(compare_fn(CLIENT, prof, body.get("goal", "calm"), body.get("carrier") or []))


def ask(request: Request) -> Response:
    q = request.query_params.get("q", "").strip()[:200]
    return JSONResponse({"q": q, "passages": retrieve(q, 3) if q else []})


def watch(request: Request) -> Response:
    """Visual carrier for people who cannot hear: films and shows from the person's taste (Qloo)."""
    try:
        prof, _ = _inputs({"profile": json.loads(request.query_params.get("profile") or "null")} if request.query_params.get("profile") else {}, request.query_params)
    except (ValueError, json.JSONDecodeError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    from reach.taste import favourite_ids, slim
    ids = favourite_ids(prof)
    out = []
    if ids:
        for kind in ("movie", "tv_show"):
            try:
                extra = {"filter.content_rating": "G,PG,TV-Y,TV-Y7,TV-G,TV-PG"} if (prof.get("age") or 30) < 13 else {}
                for e in CLIENT.insights(kind, entities=ids, take=6, label=f"{prof.get('id', 'p')}.watch.{kind}", **extra):
                    d = slim(e, prof.get("favorites", [])); d["kind"] = kind
                    pr = e.get("properties") or {}
                    d["year"] = pr.get("release_year") or str(pr.get("release_date") or "")[:4] or None
                    out.append(d)
            except QlooError:
                pass
    out.sort(key=lambda x: -(x.get("affinity") or 0))
    return JSONResponse({"items": out[:10]})


def tour(request: Request) -> Response:
    """World tour: what a city loves, through Qloo's location signal, with a playable preview.
    GET /api/tour            -> the stops
    GET /api/tour?city=Rome  -> {stop, artists, tracks, source}"""
    city = request.query_params.get("city", "").strip()
    if not city:
        tour_warm(CLIENT)
        return JSONResponse({"stops": [tour_public(t) for t in TOUR]})
    stop = next((t for t in TOUR if t["city"].lower() == city.lower()), None)
    if not stop:
        return JSONResponse({"error": "unknown city"}, status_code=404)
    return JSONResponse(tour_for(CLIENT, stop))


async def tour_media(request: Request) -> Response:
    """GET  /api/tour/media           -> every collected video with its YouTube title and the city it belongs to
    POST /api/tour/media {url, city?, start?, seconds?} -> adds a video vibe (title decides the city if none given)"""
    if request.method == "POST":
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "reason": "bad json"}, status_code=400)
        return JSONResponse(add_video(str(body.get("url", ""))[:300], body.get("city"), body.get("start"), body.get("seconds")))
    rows = []
    for v in load_media().get("videos", []):
        vid = video_id(v.get("url") or "")
        info = oembed(vid) if vid else None
        rows.append({"id": vid, "title": (info or {}).get("title"), "city": v.get("city") or match_city((info or {}).get("title") or ""), "start": v.get("start", 0), "seconds": v.get("seconds")})
    return JSONResponse({"videos": rows})


def calmvideo_route(request: Request) -> Response:
    """GET /api/calmvideo -> a 4K nature film for the visual breathing session (or {id: null})"""
    return JSONResponse(fullsong.calm_video() or {"id": None})


def trailer_route(request: Request) -> Response:
    """GET /api/trailer?name= -> the official trailer of a film or show (captions are turned on in the player)"""
    n = request.query_params.get("name", "")[:120]
    y = request.query_params.get("year", "")[:4]; k = request.query_params.get("kind", "")[:12]
    return JSONResponse((fullsong.trailer(n, y if y.isdigit() else None, k) if n else None) or {"id": None})


async def chat(request: Request) -> Response:
    """POST {text, context} -> what the message needs (act) and Reach's answer. See reach/dialogue.py."""
    try:
        body = await read_json(request)
    except (ValueError, json.JSONDecodeError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    text = str(body.get("text") or "")[:400]
    ctx = body.get("context") if isinstance(body.get("context"), dict) else {}
    ctx["lang"] = ctx.get("lang") if ctx.get("lang") in dialogue.LANGS else "en"
    pid = ctx.get("protocol_id")
    if pid:
        try:
            from reach.agent import protocol as _proto
            p = _proto(pid); ctx["protocol"] = {k: p.get(k) for k in ("id", "name", "goal", "summary", "evidence")}
        except StopIteration:
            pass
    # the names the person's artists also go by (MusicBrainz aliases, cached): 周杰倫 is Jay Chou, هایده is Hayedeh
    from reach import tour as _tour
    al = {}
    for n in (ctx.get("favourites") or [])[:12] + (ctx.get("carrier") or [])[:12]:
        info = _tour.mb_info(str(n), network=False) or {}
        for a in info.get("aliases") or []:
            if a and a.lower() != str(n).lower():
                al[a] = str(n)
    ctx["aliases"] = al
    import asyncio
    out = await asyncio.get_running_loop().run_in_executor(None, dialogue.turn, text, ctx)
    return JSONResponse(out)


def culture_route(request: Request) -> Response:
    """GET /api/culture?profile= -> the cultural lens of the person's artists. Also warms MusicBrainz for
    the artists Qloo links to them, so the first session already knows where each candidate comes from."""
    try:
        prof, _ = _inputs({}, request.query_params)
    except (ValueError, json.JSONDecodeError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    names = [f["name"] for f in prof.get("favorites", []) if f.get("type") == "artist" and f.get("name")]
    P = culture.profiles(names, budget_s=6.0, network=not CLIENT.offline)
    lens = culture.lens(names, P)
    from reach.taste import favourite_ids
    ids = favourite_ids(prof)
    if ids and not CLIENT.offline:
        try:
            cands = CLIENT.insights("artist", entities=ids, take=12, label=f"{prof.get('id', 'p')}.artist.general")
            extra = CLIENT.insights("artist", entities=ids, take=15, label=f"{prof.get('id', 'p')}.artist.culture.{(lens.get('dominant') or '').lower()}",
                                    **{"signal.location.query": lens["city"]}) if lens.get("city") and lens.get("share", 0) >= 0.5 else []
            cn = [e.get("name") for e in cands + extra if e.get("name")]
            culture.warm(cn)
            import threading
            threading.Thread(target=lambda: [prev.titles(n, 30) for n in cn], daemon=True).start()
        except QlooError:
            pass
    return JSONResponse({k: lens.get(k) for k in ("dominant", "name", "cc", "share", "of", "city", "specialist")})


def calmmusic_route(request: Request) -> Response:
    """GET /api/calmmusic?goal=sleep -> [{id, title, channel}] calm instrumental YouTube pieces (most watched)."""
    g = request.query_params.get("goal", "calm")[:20]
    return JSONResponse({"items": fullsong.calm_music(g) if fullsong.enabled() else []})


def after_route(request: Request) -> Response:
    """GET /api/after?profile=|persona=&goal=&hour= -> a place, a table and a page for after the session
    (Qloo places near the person's city, Qloo books), each with why. See reach/after.py."""
    try:
        prof, _ = _inputs({}, request.query_params)
    except (ValueError, json.JSONDecodeError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    goal = request.query_params.get("goal", "calm")[:20]
    try:
        hour = int(request.query_params.get("hour", ""))
    except ValueError:
        hour = None
    return JSONResponse(after_mod.after(CLIENT, prof, goal, hour))


def fullsong_bad_route(request: Request) -> Response:
    """POST /api/fullsong/bad?id= : the browser's player refused this video; it is never offered again."""
    fullsong.report_bad(request.query_params.get("id", "")[:20])
    return JSONResponse({"ok": True})


def fullsong_route(request: Request) -> Response:
    """GET /api/fullsong?artist=&title= -> {id, title, channel} of the YouTube video, or {id: null}"""
    a = request.query_params.get("artist", "")[:80]; t = request.query_params.get("title", "")[:120]
    hit = fullsong.find(a, t) if a and t else None
    return JSONResponse(hit or {"id": None})


async def index(request: Request) -> Response:
    return FileResponse(ROOT / "web" / "index.html")


def _bench_data() -> dict:
    try:
        return {"ran": True, **json.loads((ROOT / "data" / "bench_results.json").read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError):
        return {"ran": False}


def _public_base(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


async def mcp_route(request: Request) -> Response:
    """MCP (Streamable HTTP, JSON responses). Add https://<this server>/mcp to Claude or ChatGPT as a custom connector."""
    if request.method != "POST":
        return JSONResponse({"error": "POST JSON-RPC 2.0 to this address (Model Context Protocol)", "tools": [t["name"] for t in mcp_mod.TOOLS]},
                            status_code=405, headers={"Allow": "POST"})
    try:
        body = await read_json(request)
    except (ValueError, json.JSONDecodeError):
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}, status_code=400)
    deps = {"resolve": resolve_missing, "council": COUNCIL, "protocols": protocols, "bench": _bench_data, "base": _public_base(request),
            "after": lambda prof, need: after_mod.after(CLIENT, prof, need, None)}
    import asyncio
    loop = asyncio.get_running_loop()
    if isinstance(body, list):
        outs = [o for o in [await loop.run_in_executor(None, mcp_mod.handle, m, deps) for m in body[:10]] if o is not None]
        return JSONResponse(outs) if outs else Response(status_code=202)
    out = await loop.run_in_executor(None, mcp_mod.handle, body, deps)
    return JSONResponse(out) if out is not None else Response(status_code=202)


async def privacy_page(request: Request) -> Response:
    return FileResponse(ROOT / "web" / "privacy.html")


async def judge_page(request: Request) -> Response:
    return FileResponse(ROOT / "web" / "judge.html")


async def readme_page(request: Request) -> Response:
    """the README as a page of the site (built from README.md by scripts/make_readme_page.py)"""
    return FileResponse(ROOT / "web" / "readme.html")


def bench_route(request: Request) -> Response:
    """GET /api/bench -> the last comparison run (scripts/bench.py), aggregate numbers only, or {ran: false}."""
    f = ROOT / "data" / "bench_results.json"
    try:
        return JSONResponse({"ran": True, **json.loads(f.read_text(encoding="utf-8"))})
    except (OSError, json.JSONDecodeError):
        return JSONResponse({"ran": False})


routes = [
    Route("/api/health", health),
    Route("/api/personas", personas),
    Route("/api/protocols", protocols_route),
    Route("/api/session", session, methods=["POST"]),
    Route("/api/session/stream", stream),
    Route("/api/adapt", adapt, methods=["POST"]),
    Route("/api/verify", verify, methods=["POST"]),
    Route("/api/resolve", resolve),
    Route("/api/preview", preview_route),
    Route("/api/suggest", suggest),
    Route("/api/compare", compare_route, methods=["POST"]),
    Route("/api/ask", ask),
    Route("/api/watch", watch),
    Route("/api/tour", tour),
    Route("/api/fullsong", fullsong_route),
    Route("/api/fullsong/bad", fullsong_bad_route, methods=["POST"]),
    Route("/api/calmmusic", calmmusic_route),
    Route("/api/after", after_route),
    Route("/api/chat", chat, methods=["POST"]),
    Route("/api/culture", culture_route),
    Route("/api/calmvideo", calmvideo_route),
    Route("/api/trailer", trailer_route),
    Route("/api/tour/media", tour_media, methods=["GET", "POST"]),
    Route("/api/soundscape", soundscape_route),
    Route("/api/podcast", podcast_route),
    Route("/api/preview/stream", preview_stream),
    Route("/api/bench", bench_route),
    Route("/judge", judge_page),
    Route("/privacy", privacy_page),
    Route("/readme", readme_page),
    Route("/mcp", mcp_route, methods=["GET", "POST"]),
    Route("/", index),
    Mount("/", app=StaticFiles(directory=str(ROOT / "web")), name="web"),
]
class Squeeze:
    """gzip for text (pages, scripts, styles, JSON): three.js goes from 1.2 MB to about 250 KB. Never for the live
    streams (the council's server-sent events, MCP, audio), which must reach the browser as they are written."""
    TEXT = (".js", ".css", ".html", ".json", ".svg", ".webmanifest", ".txt", ".geojson")

    def __init__(self, app):
        self.app = app
        self.gz = GZipMiddleware(app, minimum_size=1024)

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "") if scope.get("type") == "http" else ""
        live = "stream" in path or path.startswith("/mcp") or path.startswith("/api/preview")
        last = path.rsplit("/", 1)[-1]
        if path and not live and (path.endswith(self.TEXT) or "." not in last or path.startswith("/api/")):
            return await self.gz(scope, receive, send)
        return await self.app(scope, receive, send)


app = Starlette(routes=routes, middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"]), Middleware(Squeeze)])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.app:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=False, access_log=False)
