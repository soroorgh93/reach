"""YouTube through the Data API (key only in the server's YOUTUBE_API_KEY, never in the browser):

  find(artist, title)      the song itself (music category), validated: the artist and a word of the
                           title must appear, and recaps, trailers, reactions or "movies 1-8" never pass
  city_video(city)         a 4K aerial / drone film of the city, and where its good part starts
  trailer(name)            the official trailer of a film or show (for the deaf "watch" list, captions on)
  calm_video()             a slow 4K nature film for the visual breathing session

Every answer is cached on disk (data/yt_cache.json): search costs 100 units of the free 10,000 a day,
so each thing is looked up once. A miss is cached for a day only, so a network hiccup heals itself.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "yt_cache.json"
_lock = threading.Lock()
BAD = re.compile(r"\b(recap|trailer|teaser|review|reaction|react|explained|ending|scene|full movie|movies? \d|tutorial|lesson|karaoke|cover by|slowed|sped up|8d|nightcore|1 hour|10 hours|compilation|podcast|interview)\b", re.I)
STOP = {"the", "a", "an", "of", "de", "la", "le", "el", "and", "y", "et", "to", "in", "on", "my", "your", "feat", "ft"}


def enabled() -> bool:
    return bool(os.environ.get("YOUTUBE_API_KEY"))


def _load() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _remember(key: str, val) -> None:
    with _lock:
        c = _load(); c[key] = {"v": val, "t": time.time()}
        CACHE.write_text(json.dumps(c, indent=1, ensure_ascii=False), encoding="utf-8")


def _recall(key: str):
    with _lock:
        hit = _load().get(key)
    if not hit or not isinstance(hit, dict) or "t" not in hit:
        return None, False
    if hit["v"] is None and time.time() - hit["t"] > 86400:
        return None, False
    return hit["v"], True


def _api(path: str, **params) -> dict | None:
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        return None
    params["key"] = key
    url = f"https://www.googleapis.com/youtube/v3/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=8) as r:
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001  quota, network: caller falls back
        return None


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[\w']+", (s or "").lower()) if len(w) > 1 and w not in STOP}


def _iso_seconds(d: str) -> int:
    m = re.fullmatch(r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    return (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)) if m else 0


def _norm(s: str) -> str:
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^\w ]+", " ", s).split())


def _has_name(name: str, text: str) -> bool:
    """The whole artist name, as words (Latin), or its consonant skeleton in Persian/Arabic script."""
    from .dialogue import _skel
    n, t = _norm(name), _norm(text)
    if n and re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", t):
        return True
    if n and len(n.replace(" ", "")) >= 6 and re.match(re.escape(n.replace(" ", "")) + r"(vevo|official|music|tv)?$", t.replace(" ", "")):
        return True                        # a channel spelled as one word: GloriaGaynorVEVO
    toks = re.findall(r"[\u0600-\u06FF]+", text or "")
    if toks:
        sk = {_skel(x) for x in toks} | {_skel(a + b) for a, b in zip(toks, toks[1:])}
        k = _skel(name)
        return bool(k) and len(k) >= 2 and k in sk
    return False


def _title_ok(title: str, text: str) -> bool:
    """Most of the song title's words are in the video title (or, in Persian script, their skeletons)."""
    from .dialogue import _skel
    tw = [w for w in _norm(title).split() if len(w) > 1 and w not in STOP]
    if not tw:
        return True
    vt = set(_norm(text).split())
    hit = sum(1 for w in tw if w in vt)
    if hit / len(tw) >= 0.5:
        return True
    toks = re.findall(r"[\u0600-\u06FF]+", text or "")
    if toks:
        sk = {_skel(x) for x in toks}
        return sum(1 for w in tw if _skel(w) in sk) / len(tw) >= 0.5
    return False


def find(artist: str, title: str) -> dict | None:
    """The song itself, or None. Strict: the artist's whole name in the video title or channel, most of the
    song title's words in the video title, never a recap, cover, reaction or someone else's upload of a
    different song. When unsure, None: the 30-second preview of the right song beats a full wrong one."""
    ck = f"song2|{artist.strip().lower()}|{title.strip().lower()}"
    v, ok = _recall(ck)
    if ok:
        if not v:
            return v
        vid = v.get("id")
        # chosen before the embed check existed, or reported unplayable since: check again (1 quota unit, not 100)
        if vid and not is_bad(vid) and (_recall(f"okvid|{vid}")[1] or vid in playable([vid])):
            _remember(f"okvid|{vid}", True)
            return v
    # syndicated + embeddable: only videos their owners allow to play on other websites (label "Topic"
    # uploads often refuse, and the player then shows "This video is unavailable")
    d = _api("search", part="snippet", type="video", maxResults=10, videoEmbeddable="true", videoSyndicated="true", videoCategoryId="10", q=f"{artist} {title}")
    if d is None:
        return None
    ok_ids = playable([(it.get("id") or {}).get("videoId") for it in d.get("items", []) if (it.get("id") or {}).get("videoId")])
    best = None
    for it in d.get("items", []):
        vid = (it.get("id") or {}).get("videoId"); sn = it.get("snippet") or {}
        vt, ch = sn.get("title", ""), sn.get("channelTitle", "")
        if not vid or BAD.search(vt) or vid not in ok_ids or is_bad(vid):
            continue
        if not (_has_name(artist, vt) or _has_name(artist, ch)):
            continue                       # not this artist
        if not _title_ok(title, vt):
            continue                       # not this song
        score = (3 if re.search(r"- topic$", ch, re.I) else 0) + (2 if re.search(r"official|vevo", f"{vt} {ch}", re.I) else 0) + (1 if _has_name(artist, ch) else 0)
        if not best or score > best[0]:
            best = (score, {"id": vid, "title": vt, "channel": ch})
    val = best[1] if best else None
    _remember(ck, val)
    return val


REGION = os.environ.get("REACH_REGION", "US")


def playable(ids: list[str]) -> set[str]:
    """The ids YouTube says will play inside another website: public, embeddable, not age-restricted,
    not blocked in the server's region. One videos.list call (1 quota unit) for all of them."""
    ids = [i for i in ids if i][:50]
    if not ids:
        return set()
    d = _api("videos", part="status,contentDetails", id=",".join(ids), maxResults=50)
    if d is None:
        return set(ids)                     # cannot check: keep them, the player falls back on its own
    out = set()
    for it in d.get("items", []):
        st, cd = it.get("status") or {}, it.get("contentDetails") or {}
        rr = cd.get("regionRestriction") or {}
        if not st.get("embeddable", True) or st.get("privacyStatus", "public") != "public":
            continue
        if (cd.get("contentRating") or {}).get("ytRating") == "ytAgeRestricted":
            continue
        if REGION in (rr.get("blocked") or []) or (rr.get("allowed") and REGION not in rr["allowed"]):
            continue
        out.add(it.get("id"))
    return out


def report_bad(vid: str) -> None:
    """The browser could not play this video: never offer it again, and forget the songs that pointed to it."""
    if not re.fullmatch(r"[\w-]{6,20}", vid or ""):
        return
    _remember(f"badvid|{vid}", True)
    with _lock:
        c = _load()
        stale = [k for k, v in c.items() if (k.startswith("song2|") or k.startswith("okvid|")) and isinstance(v, dict)
                 and ((isinstance(v.get("v"), dict) and v["v"].get("id") == vid) or k == f"okvid|{vid}")]
        for k in stale:
            c.pop(k, None)
        if stale:
            CACHE.write_text(json.dumps(c, indent=1, ensure_ascii=False), encoding="utf-8")


def is_bad(vid: str) -> bool:
    v, ok = _recall(f"badvid|{vid}")
    return bool(ok and v)


def _durations(ids: list[str]) -> dict[str, int]:
    d = _api("videos", part="contentDetails", id=",".join(ids))
    return {it["id"]: _iso_seconds((it.get("contentDetails") or {}).get("duration", "")) for it in (d or {}).get("items", [])}


def _film(ck: str, q: str, want: list[str], seconds: int = 40) -> dict | None:
    v, ok = _recall(ck)
    if ok:
        return v
    d = _api("search", part="snippet", type="video", maxResults=8, videoEmbeddable="true", videoDefinition="high", videoDuration="medium", q=q)
    if d is None:
        return None
    rows = []
    for it in d.get("items", []):
        vid = (it.get("id") or {}).get("videoId"); sn = it.get("snippet") or {}; t = sn.get("title", "")
        if vid and not re.search(r"\b(vlog|reaction|news|prank|review|tour guide talks|podcast)\b", t, re.I):
            rows.append((sum(1 for w in want if w.lower() in t.lower()), vid, t, sn.get("channelTitle")))
    rows.sort(key=lambda r: -r[0])
    if not rows:
        _remember(ck, None); return None
    durs = _durations([r[1] for r in rows[:5]])
    for _, vid, t, ch in rows[:5]:
        dur = durs.get(vid, 0)
        if dur >= 120:
            start = int(min(150, max(25, dur * 0.18)))       # past the intro and title cards
            val = {"id": vid, "title": t, "author": ch, "start": start, "seconds": seconds, "vertical": False, "sound": False}
            _remember(ck, val); return val
    _remember(ck, None)
    return None


def city_video(city: str, country: str) -> dict | None:
    return _film(f"city|{city.lower()}", f"{city} {country} 4K drone aerial", [city, "4k", "drone", "aerial"])


def calm_video() -> dict | None:
    return _film("calm|nature", "4K nature film relaxing landscapes no music", ["4k", "nature", "relax"], seconds=600)


def trailer(name: str, year: int | str | None = None, kind: str | None = None) -> dict | None:
    """The trailer of THIS film or show, or None. Strict, because a wrong film is worse than none:
    every word of the title must be in the video's title or description, and the release year too when it is
    known (so "Dance with Me" 2019, the Iranian film, never becomes a dance video or another "Dance with Me")."""
    year = str(year or "").strip()[:4]
    ck = f"trailer2|{name.strip().lower()}|{year}"
    v, ok = _recall(ck)
    if ok:
        return v
    word = "series" if kind == "tv_show" else "film"
    d = _api("search", part="snippet", type="video", maxResults=10, videoEmbeddable="true", q=f'"{name}" {year} {word} trailer'.replace("  ", " "))
    if d is None:
        return None
    nw = [w for w in _norm(name).split() if w not in STOP] or _norm(name).split()
    best = None
    for it in d.get("items", []):
        vid = (it.get("id") or {}).get("videoId"); sn = it.get("snippet") or {}
        t, desc = sn.get("title", ""), sn.get("description", "")
        text = _norm(f"{t} {desc}")
        if not vid or re.search(r"\b(reaction|review|explained|ending|recap|scene|clip|edit|fan made|dance video|tutorial|choreography)\b", t, re.I):
            continue
        if not all(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text) for w in nw):
            continue                                   # not this title
        if year and year not in f"{t} {desc}":
            continue                                   # another film with the same name
        score = (3 if re.search(r"trailer|teaser|tráiler|تریلر|تیزر|預告|预告|예고", t, re.I) else 0) + (1 if all(w in _norm(t).split() for w in nw) else 0)
        if not best or score > best[0]:
            best = (score, {"id": vid, "title": t})
    val = best[1] if best and best[0] >= 1 else None
    _remember(ck, val)
    return val


CALM_Q = {"sleep": "deep sleep music no vocals", "calm": "relaxing music stress relief no vocals", "autism_calm": "calming music for children no vocals",
          "focus": "focus music no vocals", "mood": "uplifting instrumental music"}


def calm_music(goal: str) -> list[dict]:
    """The most watched long instrumental pieces for a need (YouTube, by view count), for people whose own
    artists would not help them sleep or calm down. Up to five, never a reaction, compilation of songs or talk."""
    ck = f"calmmusic|{goal}"
    v, ok = _recall(ck)
    if ok and v is not None:
        return v
    d = _api("search", part="snippet", type="video", maxResults=12, videoEmbeddable="true", order="viewCount", videoDuration="long", q=CALM_Q.get(goal, CALM_Q["calm"]))
    if d is None:
        return []
    out = []
    for it in d.get("items", []):
        vid = (it.get("id") or {}).get("videoId"); sn = it.get("snippet") or {}; t = sn.get("title", "")
        if vid and not re.search(r"\b(reaction|review|podcast|interview|talk|asmr|lyrics|vocal|singing|news)\b", t, re.I):
            out.append({"id": vid, "title": t, "channel": sn.get("channelTitle")})
        if len(out) >= 5:
            break
    _remember(ck, out or None)
    return out
