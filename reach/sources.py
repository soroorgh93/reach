"""Open content sources that give the session something real to carry, all keyless:
  * Deezer / iTunes search  -> artist autocomplete (worldwide catalogue) and 30-second previews
  * Internet Archive        -> full-length soundscapes and ambient albums (public domain / CC)
  * iTunes podcast search   -> podcasts, then the latest episode's audio from the RSS feed
Everything audio is streamed through this server so Web Audio can process it (see previews.py).
Each function degrades to [] on any network error; the council never depends on them.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()
TTL = 6 * 3600
UA = {"User-Agent": "Reach/1.0 (+hackathon demo)", "Accept": "application/json, text/xml, */*"}


def _cached(key: str, fn):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
    try:
        val = fn()
    except Exception:
        val = []
    with _lock:
        _cache[key] = (time.time(), val)
    return val


def _get(url: str, timeout: float = 8.0) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _json(url: str, timeout: float = 8.0) -> Any:
    return json.loads(_get(url, timeout).decode("utf-8", "replace"))


# ---------------------------------------------------------------- artist autocomplete (world catalogue)
def suggest_artists(q: str, limit: int = 6) -> list[dict[str, Any]]:
    """Deezer artist search (covers Persian, Indian, Chinese, Latin catalogues), iTunes as fallback."""
    q = q.strip()
    if len(q) < 2:
        return []

    def run():
        out = []
        try:
            data = _json(f"https://api.deezer.com/search/artist?q={urllib.parse.quote(q)}&limit={limit}")
            for a in data.get("data", []):
                out.append({"name": a.get("name"), "type": "artist", "image": a.get("picture_medium"), "source": "deezer", "fans": a.get("nb_fan")})
        except Exception:
            pass
        if not out:
            data = _json(f"https://itunes.apple.com/search?term={urllib.parse.quote(q)}&entity=musicArtist&limit={limit}")
            for a in data.get("results", []):
                out.append({"name": a.get("artistName"), "type": "artist", "image": None, "source": "itunes", "fans": None})
        return out
    return _cached("artist:" + q.lower(), run)


# ---------------------------------------------------------------- soundscapes (Internet Archive)
SOUNDSCAPES = {
    "ocean": "ocean waves", "rain": "rain sounds", "forest": "forest birds ambience", "river": "river stream water",
    "fire": "fireplace crackling", "wind": "wind ambience", "night": "night crickets", "bowls": "singing bowls meditation",
    "tanpura": "tanpura drone", "piano": "ambient piano", "drone": "ambient drone", "whale": "whale song", "thunder": "thunderstorm",
}


def soundscape(kind: str, rows: int = 6) -> list[dict[str, Any]]:
    """Full-length public recordings from the Internet Archive for a soundscape kind."""
    query = SOUNDSCAPES.get(kind, kind)

    def run():
        q = urllib.parse.quote(f'({query}) AND mediatype:audio AND format:(MP3) AND -collection:(podcasts OR librivoxaudio OR audio_bookspoetry OR oldtimeradio OR audio_religion OR etree) AND -subject:(audiobook OR librivox OR sermon OR lecture OR radio)')
        data = _json(f"https://archive.org/advancedsearch.php?q={q}&fl[]=identifier&fl[]=title&fl[]=downloads&sort[]=downloads+desc&rows={rows}&output=json", timeout=12)
        out = []
        for d in data.get("response", {}).get("docs", [])[:rows]:
            ident = d.get("identifier")
            if not ident:
                continue
            try:
                meta = _json(f"https://archive.org/metadata/{urllib.parse.quote(ident)}", timeout=12)
            except Exception:
                continue
            files = [f for f in meta.get("files", []) if str(f.get("name", "")).lower().endswith(".mp3")]
            bad = ("chapter", "part ", "book", "sermon", "lecture", "interview", "radio", "episode", "talk")
            files = [f for f in files if not any(b in str(f.get("title") or f.get("name") or "").lower() for b in bad)]
            files.sort(key=lambda f: -float(f.get("length", 0) or 0) if str(f.get("length", "0")).replace(".", "", 1).isdigit() else 0)
            for f in files[:2]:
                length = f.get("length")
                try:
                    secs = float(length) if length and ":" not in str(length) else sum(float(x) * 60 ** i for i, x in enumerate(reversed(str(length).split(":")))) if length else 0
                except ValueError:
                    secs = 0
                if secs and secs < 60:
                    continue
                url = f"https://archive.org/download/{ident}/{urllib.parse.quote(f['name'])}"
                out.append({"title": f.get("title") or f["name"].rsplit(".", 1)[0], "artist": d.get("title") or ident, "preview": url, "cover": None,
                            "source": "archive.org", "duration": int(secs) if secs else None, "kind": kind})
        return out[:rows]
    return _cached("scape:" + kind, run)


# ---------------------------------------------------------------- podcasts (iTunes + RSS)
def podcast_shows(term: str, limit: int = 3, lang: str | None = None) -> list[dict[str, Any]]:
    """Podcasts for a name or topic (iTunes), each with its latest dozen episodes (RSS)."""
    term = term.strip()
    if not term:
        return []

    def run():
        country = {"es": "ES", "fa": "US", "zh": "CN", "en": "US"}.get(lang or "en", "US")
        data = _json(f"https://itunes.apple.com/search?term={urllib.parse.quote(term)}&entity=podcast&limit={limit}&country={country}")
        out = []
        for p in data.get("results", [])[:limit]:
            feed = p.get("feedUrl")
            if not feed:
                continue
            try:
                root = ET.fromstring(_get(feed, timeout=10))
            except Exception:
                continue
            eps = []
            for item in root.iter("item"):
                enc = item.find("enclosure")
                if enc is None or not enc.get("url"):
                    continue
                dur = item.findtext("{http://www.itunes.com/dtds/podcast-1.0.dtd}duration") or ""
                eps.append({"title": (item.findtext("title") or "").strip()[:120], "artist": p.get("collectionName"), "preview": enc.get("url"),
                            "cover": p.get("artworkUrl600") or p.get("artworkUrl100"), "source": "podcast", "duration": _dur(dur), "kind": "podcast"})
                if len(eps) >= 12:
                    break
            if eps:
                ch = root.find("channel")
                desc = " ".join(x for x in ((ch.findtext("description") if ch is not None else "") or "",
                                             (ch.findtext("{http://www.itunes.com/dtds/podcast-1.0.dtd}summary") if ch is not None else "") or "") if x)
                out.append({"show": p.get("collectionName"), "genre": p.get("primaryGenreName"), "genres": p.get("genres") or [],
                            "author": p.get("artistName"), "desc": re.sub(r"<[^>]+>", " ", desc)[:1200], "episodes": eps})
        return out
    return _cached(f"shows2:{lang}:{term.lower()}:{limit}", run)


def podcast_episodes(term: str, limit: int = 3, lang: str | None = None) -> list[dict[str, Any]]:
    """The latest episode of each podcast found for a term (kept for the self-check)."""
    return [sh["episodes"][0] for sh in podcast_shows(term, limit, lang)]


def _dur(s: str) -> int | None:
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    try:
        parts = [float(x) for x in s.split(":")]
        return int(sum(v * 60 ** i for i, v in enumerate(reversed(parts))))
    except ValueError:
        return None
