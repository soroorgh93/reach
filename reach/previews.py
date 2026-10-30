"""Thirty-second preview tracks for the artists Qloo picked, from Deezer's public search API
(no key) with iTunes Search as fallback. Previews are streamed through this server so the
browser can run them through the entrainment chain (cross-origin media would be silenced by
Web Audio). Only the two preview CDNs are ever proxied."""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from typing import Any

ALLOWED_HOST_SUFFIXES = (".dzcdn.net", ".deezer.com", "audio-ssl.itunes.apple.com", ".mzstatic.com", ".apple.com")
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_lock = threading.Lock()
TTL = 6 * 3600


def _get_json(url: str, timeout: float = 8.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Reach/1.0 (+hackathon demo)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


_acache: dict[str, tuple[float, dict[str, Any] | None]] = {}


def deezer_artist(name: str) -> dict[str, Any] | None:
    """The Deezer artist this name means. Several artists can share a name (the Persian singer Dariush and an
    unrelated "Dariush" on Deezer): among the exact-name matches, the one with by far the most listeners."""
    key = _n(name)
    with _lock:
        hit = _acache.get(key)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
    pick = None
    try:
        data = _get_json(f"https://api.deezer.com/search/artist?q={urllib.parse.quote(name)}&limit=10")
        exact = [a for a in data.get("data", []) if _n(a.get("name") or "") == key]
        if exact:
            pick = max(exact, key=lambda a: a.get("nb_fan") or 0)
            pick = {"id": pick.get("id"), "name": pick.get("name"), "fans": pick.get("nb_fan") or 0, "namesakes": len(exact) - 1}
    except Exception:  # noqa: BLE001
        pick = None
    with _lock:
        _acache[key] = (time.time() - (TTL - 120 if pick is None else 0), pick)
    return pick


def _track(t: dict[str, Any]) -> dict[str, Any]:
    al = t.get("album") or {}
    return {"title": t.get("title"), "artist": (t.get("artist") or {}).get("name"), "artist_id": (t.get("artist") or {}).get("id"), "preview": t["preview"],
            "cover": al.get("cover_medium"), "cover_big": al.get("cover_xl") or al.get("cover_big"), "link": t.get("link"), "source": "deezer", "duration": 30}


def _deezer(artist: str, limit: int) -> list[dict[str, Any]]:
    a = deezer_artist(artist)
    if a and a.get("id"):
        # that artist's own most-played songs: never a namesake's
        try:
            top = _get_json(f"https://api.deezer.com/artist/{a['id']}/top?limit={max(limit, 10)}")
            out = [_track(t) for t in top.get("data", []) if t.get("preview")]
            if out:
                return out
        except Exception:  # noqa: BLE001
            pass
    q = urllib.parse.quote(f'artist:"{artist}"')
    data = _get_json(f"https://api.deezer.com/search?q={q}&limit={limit}&order=RANKING")
    if not data.get("data"):                       # the advanced form can come back empty in some regions: plain search
        data = _get_json(f"https://api.deezer.com/search?q={urllib.parse.quote(artist)}&limit={limit * 2}")
    out = [_track(t) for t in data.get("data", []) if t.get("preview")]
    if a and a.get("id"):
        out = [t for t in out if t.get("artist_id") in (None, a["id"])]
    return out


_ilock = threading.Lock()
_ilast = [0.0]


def _itunes_get(url: str) -> Any:
    """iTunes allows about 20 searches a minute: space them out so a burst never gets every artist refused."""
    with _ilock:
        wait = 0.35 - (time.time() - _ilast[0])
        if wait > 0:
            time.sleep(wait)
        _ilast[0] = time.time(); _irecent.append(_ilast[0])
        while _irecent and _irecent[0] < _ilast[0] - 60:
            _irecent.pop(0)
    return _get_json(url)


_irecent: list[float] = []


def itunes_busy() -> bool:
    """True when iTunes has been asked a lot in the last minute: songs to play come before title fingerprints."""
    now = time.time()
    return sum(1 for t in _irecent if t > now - 60) >= 8


def _itunes(artist: str, limit: int) -> list[dict[str, Any]]:
    q = urllib.parse.quote(artist)
    data = _itunes_get(f"https://itunes.apple.com/search?term={q}&entity=song&attribute=artistTerm&limit={limit * 3}")
    out = []
    for t in data.get("results", []):
        if not t.get("previewUrl"):
            continue
        out.append({"title": t.get("trackName"), "artist": t.get("artistName"), "preview": t["previewUrl"],
                    "cover": t.get("artworkUrl100"), "cover_big": (t.get("artworkUrl100") or "").replace("100x100bb", "600x600bb") or None,
                    "link": t.get("trackViewUrl"), "source": "itunes", "duration": 30})
    return out


def _n(s: str) -> str:
    import re, unicodedata
    s = "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^\w ]+", " ", s).split())


def same_artist(want: str, got: str) -> bool:
    """The track is by the artist asked for: same name, or the name as whole words in a credit
    ("Hayedeh & Mahasti"). A search for "Kalben" must never return a Kalbeliya folk song."""
    a, b = _n(want), _n(got)
    if not a or not b:
        return False
    if a == b:
        return True
    import re
    return bool(re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", b))


def _compact(s: str) -> str:
    return "".join(_n(s).split())


def _skeleton(s: str) -> str:
    """Consonants only, doubled letters collapsed: one song in many spellings (Gol-e Yakh, Gole Yakh, Gol e Yakh;
    Khiali Nist, Khiyali Nist) has one skeleton."""
    import re
    c = re.sub(r"[aeiouy]", "", _compact(s))
    return re.sub(r"(.)\1+", r"\1", c)


def same_title(want: str, got: str) -> bool:
    """The same song: equal after spelling and punctuation are set aside, one inside the other ("Pol" in "Pol
    (Remastered)"), the same consonant skeleton, or most of the words in common."""
    import re
    def core(x: str) -> str:                       # "Pol (Remastered)", "Pol - Live" and "Pol [2004]" are Pol
        return re.split(r"\s+[-–—]\s+", re.sub(r"[\(\[].*?[\)\]]", " ", x or ""))[0]
    want, got = core(want), core(got)
    a, b = _compact(want), _compact(got)
    if not a or not b:
        return False
    short, long_ = sorted((a, b), key=len)
    if a == b or (len(short) >= 4 and short in long_ and len(short) / len(long_) >= 0.6):
        return True
    sa, sb = _skeleton(want), _skeleton(got)
    if len(sa) >= 3 and (sa == sb or (len(sa) >= 5 and sa in sb)):
        return True
    wa, wb = set(_n(want).split()), set(_n(got).split())
    return bool(wa) and len(wa & wb) / len(wa) >= 0.75 and len(wa) >= 2


def find_track(artist: str, song: str) -> dict[str, Any] | None:
    """Is this exact song in the catalogue? The artist's songs first, then a direct search for "artist song"
    (Deezer, then iTunes). Used to check songs a language model names."""
    for t in previews(artist, 10):
        if same_title(song, t.get("title") or ""):
            return t
    for title in titles(artist, 50):
        if same_title(song, title):
            return {"title": title, "artist": artist, "source": "deezer"}
    try:
        data = _get_json(f"https://api.deezer.com/search?q={urllib.parse.quote(f'{artist} {song}')}&limit=15")
        for t in data.get("data", []):
            if same_artist(artist, (t.get("artist") or {}).get("name") or "") and same_title(song, t.get("title") or ""):
                return {"title": t.get("title"), "artist": (t.get("artist") or {}).get("name"), "source": "deezer"}
    except Exception:  # noqa: BLE001
        pass
    try:
        data = _itunes_get(f"https://itunes.apple.com/search?term={urllib.parse.quote(f'{artist} {song}')}&entity=song&limit=15")
        for t in data.get("results", []):
            if same_artist(artist, t.get("artistName") or "") and same_title(song, t.get("trackName") or ""):
                return {"title": t.get("trackName"), "artist": t.get("artistName"), "source": "itunes"}
    except Exception:  # noqa: BLE001
        pass
    return None


def previews(artist: str, limit: int = 4) -> list[dict[str, Any]]:
    key = f"{artist.strip().lower()}|{limit}"
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
    tracks: list[dict[str, Any]] = []
    for fn in (_deezer, _itunes):
        try:
            got = fn(artist, limit * 2)
            tracks = [t for t in got if same_artist(artist, t.get("artist") or "")][:limit]
            if not tracks and got and any(ord(c) > 0x2FF for c in artist):
                # a name in its own script (周杰伦, هایده): the catalogue files it under another spelling. Trust it
                # only when one artist clearly owns the results.
                from collections import Counter
                top, n = Counter(t.get("artist") for t in got).most_common(1)[0]
                if top and n >= max(2, 0.6 * len(got)):
                    tracks = [t for t in got if t.get("artist") == top][:limit]
        except Exception:
            tracks = []
        if tracks:
            break
    with _lock:
        # an empty answer is usually a refused or failed request: keep it two minutes, not six hours
        _cache[key] = (time.time() - (TTL - 120 if not tracks else 0), tracks)
    return tracks


_tcache: dict[str, tuple[float, list[str]]] = {}


def titles(artist: str, limit: int = 30) -> list[str]:
    """Up to `limit` song titles of this artist (Deezer search), for the language fingerprint."""
    key = artist.strip().lower()
    with _lock:
        hit = _tcache.get(key)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
    out: list[str] = []
    try:
        a = deezer_artist(artist)
        if a and a.get("id"):
            data = _get_json(f"https://api.deezer.com/artist/{a['id']}/top?limit=50")
            out = list(dict.fromkeys(t.get("title") or "" for t in data.get("data", []) if t.get("title")))[:limit]
        if not out:
            q = urllib.parse.quote(f'artist:"{artist}"')
            data = _get_json(f"https://api.deezer.com/search?q={q}&limit=50")
            out = list(dict.fromkeys(t.get("title") or "" for t in data.get("data", []) if same_artist(artist, (t.get("artist") or {}).get("name") or "")
                                     and (not a or (t.get("artist") or {}).get("id") in (None, a.get("id")))))[:limit]
    except Exception:
        out = []
    if not out:                       # titles already fetched with the previews cost nothing
        with _lock:
            for k, (ts, tr) in _cache.items():
                if k.startswith(key + "|") and tr:
                    out = [t.get("title") or "" for t in tr]; break
    if not out and not itunes_busy():  # Deezer can come back empty in some regions: iTunes has the same catalogue
        try:
            data = _itunes_get(f"https://itunes.apple.com/search?term={urllib.parse.quote(artist)}&entity=song&attribute=artistTerm&limit=50")
            out = list(dict.fromkeys(t.get("trackName") or "" for t in data.get("results", []) if same_artist(artist, t.get("artistName") or "")))[:limit]
        except Exception:
            out = []
    with _lock:
        _tcache[key] = (time.time() - (TTL - 120 if not out else 0), out)
    return out


def allowed(url: str) -> bool:
    """https only, public hosts only (podcast enclosures live on many CDNs, so we block private ranges rather than allow-list)."""
    try:
        u = urllib.parse.urlparse(url); host = (u.hostname or "").lower()
    except ValueError:
        return False
    if u.scheme not in ("https", "http") or not host or host in ("localhost",) or host.endswith(".local") or host.endswith(".internal"):
        return False
    import ipaddress, socket
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        pass
    try:
        for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP):
            if not ipaddress.ip_address(info[4][0]).is_global:
                return False
    except socket.gaierror:
        return False
    return True


def open_stream(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Reach/1.0"})
    return urllib.request.urlopen(req, timeout=15)
