"""The world tour on the Earth chapter.

For each city:
  * the country (ISO-3) the globe outlines in red and the locator map fills,
  * a classic of the country (an old, loved song, searched on Deezer by artist + title, so
    Tehran plays Googoosh or Hayedeh, never whatever is global that week),
  * street and landmark photos of the city from Wikipedia (page images, freely licensed),
  * a video vibe of the place, when one is known: links the author collected, kept in
    data/tour_media.json, assigned to cities by their YouTube title (oEmbed, the official
    keyless endpoint), each with the segment to play (start, seconds) so only the good part shows,
  * what the city's audience loves now, through Qloo's location signal (signal.location.query).
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from . import previews as prev
from .qloo import QlooClient, QlooError

ROOT = Path(__file__).resolve().parent.parent
MEDIA_PATH = ROOT / "data" / "tour_media.json"
UA = {"User-Agent": "Reach/1.0 (hackathon demo; https://github.com) python-urllib", "Accept": "application/json"}

TOUR: list[dict[str, Any]] = [
    {"city": "Rome", "cc": "IT", "loved": ["Domenico Modugno", "Lucio Dalla", "Adriano Celentano", "Laura Pausini", "Eros Ramazzotti", "Andrea Bocelli", "Mina"], "country": "Italy", "iso3": "ITA", "lang": "it", "lat": 41.9028, "lon": 12.4964, "local": "Roma", "line": "Che cosa ama Roma", "genre": "italian",
     "keys": ["rome", "roma", "italy", "italia", "italian", "italiana", "🇮🇹", "amalfi", "tuscany", "venezia", "venice"],
     "classics": [["Domenico Modugno", "Nel blu dipinto di blu"], ["Lucio Dalla", "Caruso"], ["Adriano Celentano", "Azzurro"]],
     "pages": ["Trevi Fountain", "Trastevere", "Piazza Navona", "Colosseum"]},
    {"city": "Paris", "cc": "FR", "loved": ["Édith Piaf", "Charles Aznavour", "Joe Dassin", "Indila", "Zaz", "Serge Gainsbourg"], "country": "France", "iso3": "FRA", "lang": "fr", "lat": 48.8566, "lon": 2.3522, "local": "Paris", "line": "Ce que Paris aime", "genre": "french",
     "keys": ["paris", "france", "french", "français", "🇫🇷", "cityoflove", "eiffel"],
     "classics": [["Édith Piaf", "La vie en rose"], ["Charles Aznavour", "La bohème"], ["Joe Dassin", "Les Champs-Élysées"]],
     "pages": ["Montmartre", "Champs-Élysées", "Eiffel Tower", "Pont des Arts"]},
    {"city": "Istanbul", "cc": "TR", "loved": ["Barış Manço", "Sezen Aksu", "Tarkan", "Zeki Müren", "Müslüm Gürses", "Ajda Pekkan"], "country": "Türkiye", "iso3": "TUR", "lang": "tr", "lat": 41.0082, "lon": 28.9784, "local": "İstanbul", "line": "İstanbul'un sevdikleri", "genre": "turkish",
     "keys": ["istanbul", "i̇stanbul", "turkey", "türkiye", "turkiye", "turkish", "türk", "🇹🇷", "bosphorus"],
     "classics": [["Barış Manço", "Gülpembe"], ["Sezen Aksu", "Firuze"], ["Zeki Müren", "Gözlerin Doğuyor Gecelerime"]],
     "pages": ["İstiklal Avenue", "Galata Tower", "Hagia Sophia", "Bosphorus"]},
    {"city": "Tehran", "cc": "IR", "loved": ["Mohsen Chavoshi", "Googoosh", "Hayedeh", "Ebi", "Dariush", "Mohammad Reza Shajarian", "Homayoun Shajarian", "Kourosh Yaghmaei"], "country": "Iran", "iso3": "IRN", "lang": "fa", "lat": 35.6892, "lon": 51.389, "local": "تهران", "line": "آنچه تهران دوست دارد", "genre": "persian",
     "keys": ["tehran", "iran", "persian", "farsi", "تهران", "ایران", "🇮🇷", "googoosh", "hayedeh"],
     "classics": [["Googoosh", "Pol"], ["Hayedeh", "Soghati"], ["Kourosh Yaghmaei", "Gole Yakh"], ["Viguen", "Mahtab"]],
     "pages": ["Tajrish", "Azadi Tower", "Milad Tower", "Golestan Palace"]},
    {"city": "Mumbai", "cc": "IN", "loved": ["Lata Mangeshkar", "Kishore Kumar", "Arijit Singh", "Mohammed Rafi", "A. R. Rahman", "Asha Bhosle"], "country": "India", "iso3": "IND", "lang": "hi", "lat": 19.076, "lon": 72.8777, "local": "मुंबई", "line": "मुंबई को क्या पसंद है", "genre": "bollywood",
     "keys": ["mumbai", "bombay", "india", "indian", "bollywood", "hindi", "🇮🇳", "arijit", "shahrukh", "srk"],
     "classics": [["Lata Mangeshkar", "Lag Jaa Gale"], ["Kishore Kumar", "Mere Sapno Ki Rani"], ["Mohammed Rafi", "Chaudhvin Ka Chand"]],
     "pages": ["Marine Drive, Mumbai", "Gateway of India", "Chhatrapati Shivaji Terminus", "Bandra–Worli Sea Link"]},
    {"city": "Lagos", "cc": "NG", "loved": ["Fela Kuti", "Burna Boy", "Wizkid", "King Sunny Adé", "Davido"], "country": "Nigeria", "iso3": "NGA", "lang": "en", "lat": 6.5244, "lon": 3.3792, "local": "Lagos", "line": "What Lagos loves", "genre": "afrobeats",
     "keys": ["lagos", "nigeria", "naija", "afrobeat", "afrobeats", "🇳🇬"],
     "classics": [["Fela Kuti", "Water No Get Enemy"], ["King Sunny Adé", "Ja Funmi"], ["Oliver De Coque", "Identity"]],
     "pages": ["Lekki-Ikoyi Link Bridge", "Balogun Market", "Lagos Island", "Tarkwa Bay Beach"]},
    {"city": "Rio de Janeiro", "cc": "BR", "loved": ["Astrud Gilberto", "João Gilberto", "Elis Regina", "Antônio Carlos Jobim", "Jorge Ben Jor", "Caetano Veloso"], "country": "Brazil", "iso3": "BRA", "lang": "pt", "lat": -22.9068, "lon": -43.1729, "local": "Rio", "line": "O que o Rio ama", "genre": "brazilian",
     "keys": ["rio", "brazil", "brasil", "bossa", "samba", "🇧🇷", "copacabana"],
     "classics": [["Astrud Gilberto", "The Girl from Ipanema"], ["João Gilberto", "Chega de Saudade"], ["Elis Regina", "Águas de Março"]],
     "pages": ["Copacabana, Rio de Janeiro", "Escadaria Selarón", "Christ the Redeemer (statue)", "Sugarloaf Mountain"]},
    {"city": "Seoul", "cc": "KR", "loved": ["Cho Yong-pil", "IU", "BTS", "Kim Kwang-seok", "Lee Sun-hee"], "country": "South Korea", "iso3": "KOR", "lang": "ko", "lat": 37.5665, "lon": 126.978, "local": "서울", "line": "서울이 사랑하는 것", "genre": "k_pop",
     "keys": ["seoul", "korea", "korean", "k-pop", "kpop", "서울", "🇰🇷"],
     "classics": [["Cho Yong-pil", "Bounce"], ["Kim Kwang-seok", "Around Thirty"], ["Lee Sun-hee", "To J"]],
     "pages": ["Bukchon Hanok Village", "Gyeongbokgung", "Myeong-dong", "N Seoul Tower"]},
    {"city": "Tokyo", "cc": "JP", "loved": ["Kyu Sakamoto", "Mariya Takeuchi", "Misora Hibari", "Joe Hisaishi", "Hikaru Utada"], "country": "Japan", "iso3": "JPN", "lang": "ja", "lat": 35.6762, "lon": 139.6503, "local": "東京", "line": "東京が愛するもの", "genre": "j_pop",
     "keys": ["tokyo", "japan", "japanese", "東京", "日本", "🇯🇵", "shibuya", "kyoto"],
     "classics": [["Kyu Sakamoto", "Sukiyaki"], ["Mariya Takeuchi", "Plastic Love"], ["Misora Hibari", "Kawa no Nagare no Yō ni"]],
     "pages": ["Shibuya Crossing", "Sensō-ji", "Shinjuku", "Tokyo Tower"]},
    {"city": "Mexico City", "cc": "MX", "loved": ["Chavela Vargas", "Pedro Infante", "Vicente Fernández", "Luis Miguel", "Juan Gabriel"], "country": "Mexico", "iso3": "MEX", "lang": "es", "lat": 19.4326, "lon": -99.1332, "local": "CDMX", "line": "Lo que ama la Ciudad de México", "genre": "latin",
     "keys": ["mexico", "méxico", "cdmx", "mexican", "mariachi", "🇲🇽"],
     "classics": [["Chavela Vargas", "La Llorona"], ["Pedro Infante", "Cien Años"], ["Javier Solís", "Sombras"]],
     "pages": ["Zócalo", "Palacio de Bellas Artes", "Xochimilco", "Coyoacán"]},
    {"city": "Cairo", "cc": "EG", "loved": ["Umm Kulthum", "Abdel Halim Hafez", "Mohamed Mounir", "Amr Diab"], "country": "Egypt", "iso3": "EGY", "lang": "ar", "lat": 30.0444, "lon": 31.2357, "local": "القاهرة", "line": "ما تحبه القاهرة", "genre": "arabic",
     "keys": ["cairo", "egypt", "egyptian", "arabic", "arab", "القاهرة", "مصر", "🇪🇬", "middle eastern"],
     "classics": [["Umm Kulthum", "Enta Omri"], ["Abdel Halim Hafez", "Ahwak"], ["Mohamed Mounir", "Ali Sotak"]],
     "pages": ["Khan el-Khalili", "Giza pyramid complex", "Muizz Street", "Cairo Tower"]},
    {"city": "Berlin", "cc": "DE", "loved": ["Marlene Dietrich", "Nena", "Kraftwerk", "Paul Kalkbrenner"], "country": "Germany", "iso3": "DEU", "lang": "de", "lat": 52.52, "lon": 13.405, "local": "Berlin", "line": "Was Berlin liebt", "genre": "techno",
     "keys": ["berlin", "germany", "german", "deutschland", "🇩🇪"],
     "classics": [["Marlene Dietrich", "Lili Marleen"], ["Nena", "99 Luftballons"], ["Kraftwerk", "Das Model"]],
     "pages": ["Brandenburg Gate", "East Side Gallery", "Unter den Linden", "Museum Island"]},
    {"city": "Havana", "cc": "CU", "loved": ["Buena Vista Social Club", "Compay Segundo", "Celia Cruz", "Ibrahim Ferrer", "Omara Portuondo"], "country": "Cuba", "iso3": "CUB", "lang": "es", "lat": 23.1136, "lon": -82.3666, "local": "La Habana", "line": "Lo que ama La Habana", "genre": "salsa",
     "keys": ["havana", "habana", "cuba", "cuban", "🇨🇺"],
     "classics": [["Buena Vista Social Club", "Chan Chan"], ["Compay Segundo", "Chan Chan"], ["Celia Cruz", "Quimbara"]],
     "pages": ["Old Havana", "Malecón, Havana", "El Capitolio", "Plaza de la Catedral"]},
    {"city": "Madrid", "cc": "ES", "loved": ["Paco de Lucía", "Camarón de la Isla", "Rocío Jurado", "Rosalía", "Alejandro Sanz"], "country": "Spain", "iso3": "ESP", "lang": "es", "lat": 40.4168, "lon": -3.7038, "local": "Madrid", "line": "Lo que ama Madrid", "genre": "flamenco",
     "keys": ["madrid", "spain", "españa", "spanish", "flamenco", "🇪🇸", "sevilla", "andalucia"],
     "classics": [["Paco de Lucía", "Entre dos aguas"], ["Camarón de la Isla", "Volando Voy"], ["Rocío Jurado", "Como una ola"]],
     "pages": ["Gran Vía (Madrid)", "Plaza Mayor, Madrid", "Puerta del Sol", "Royal Palace of Madrid"]},
]
PUBLIC = ("city", "country", "cc", "iso3", "lang", "lat", "lon", "local", "line", "genre")

_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def _cached(key: str, ttl: float, fn):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < (ttl if hit[1] else 60):
            return hit[1]
    try:
        val = fn()
    except Exception:  # noqa: BLE001
        val = None
    with _lock:
        _cache[key] = (time.time(), val)
    return val


def _json(url: str, timeout: float = 8.0) -> Any:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def public(stop: dict[str, Any]) -> dict[str, Any]:
    return {k: stop[k] for k in PUBLIC}


# ---------------------------------------------------------------- videos (author's links, oEmbed titles)
YT_ID = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/))([A-Za-z0-9_-]{11})")


def video_id(url: str) -> str | None:
    m = YT_ID.search(url or "")
    return m.group(1) if m else (url if re.fullmatch(r"[A-Za-z0-9_-]{11}", url or "") else None)


def load_media() -> dict[str, Any]:
    try:
        return json.loads(MEDIA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"videos": []}


def save_media(m: dict[str, Any]) -> None:
    MEDIA_PATH.write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")


def oembed(vid: str) -> dict[str, Any] | None:
    def run():
        d = _json("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}"))
        return {"title": d.get("title"), "author": d.get("author_name"), "w": d.get("width"), "h": d.get("height"), "thumb": d.get("thumbnail_url")}
    return _cached("oembed:" + vid, 24 * 3600, run)


def match_city(title: str) -> str | None:
    t = (title or "").lower()
    best, score = None, 0
    for s in TOUR:
        sc = sum(len(k) for k in s["keys"] if k in t)
        if sc > score:
            best, score = s["city"], sc
    return best


def videos_for(city: str) -> list[dict[str, Any]]:
    """Videos for a city: explicit city in tour_media.json first, then any video whose YouTube
    title names the city or its country. Each video carries start and seconds (the good part)."""
    out = []
    for v in load_media().get("videos", []):
        vid = video_id(v.get("url") or v.get("id") or "")
        if not vid:
            continue
        info = oembed(vid) or {}
        c = v.get("city") or match_city(info.get("title") or v.get("note") or "")
        if c != city:
            continue
        vertical = bool(v.get("vertical")) if "vertical" in v else ("/shorts/" in (v.get("url") or "") or (info.get("h") or 0) > (info.get("w") or 1))
        out.append({"id": vid, "title": info.get("title") or v.get("note") or "", "author": info.get("author"), "start": int(v.get("start", 0)),
                    "seconds": int(v.get("seconds", 30 if vertical else 40)), "vertical": vertical, "sound": v.get("sound", True), "thumb": info.get("thumb")})
    return out


def add_video(url: str, city: str | None, start: int | None = None, seconds: int | None = None) -> dict[str, Any]:
    vid = video_id(url)
    if not vid:
        return {"ok": False, "reason": "not a YouTube link"}
    info = oembed(vid) or {}
    city = city or match_city(info.get("title") or "")
    m = load_media(); vids = [v for v in m.get("videos", []) if video_id(v.get("url") or v.get("id") or "") != vid]
    row: dict[str, Any] = {"url": url, "city": city, "note": info.get("title") or ""}
    if start is not None:
        row["start"] = int(start)
    if seconds is not None:
        row["seconds"] = int(seconds)
    vids.append(row); m["videos"] = vids; save_media(m)
    return {"ok": True, "id": vid, "city": city, "title": info.get("title")}


# ---------------------------------------------------------------- photos (Wikipedia page images)
def photos(stop: dict[str, Any]) -> list[dict[str, Any]]:
    def run():
        titles = "|".join(stop["pages"])
        d = _json("https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1&prop=pageimages|info&inprop=url&piprop=thumbnail&pithumbsize=1920&titles=" + urllib.parse.quote(titles))
        pages = (d.get("query") or {}).get("pages") or {}
        order = {t: i for i, t in enumerate(stop["pages"])}
        rows = []
        for p in pages.values():
            th = (p.get("thumbnail") or {}).get("source")
            if th:
                rows.append({"src": th, "title": p.get("title"), "page": p.get("fullurl"), "i": order.get(p.get("title"), 9)})
        rows.sort(key=lambda r: r["i"])
        return rows
    return _cached("photos:" + stop["city"], 24 * 3600, run) or []


# ---------------------------------------------------------------- a song of the country
_visits: dict[str, int] = {}


MB_PATH = ROOT / "data" / "mb_cache.json"
_mb_lock = threading.Lock()
_mb_net = threading.Lock()          # MusicBrainz asks for one request a second


def _mb_disk() -> dict:
    try:
        return json.loads(MB_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _mb_save(key: str, val: Any) -> None:
    with _mb_lock:
        disk = _mb_disk(); disk[key] = val; MB_PATH.write_text(json.dumps(disk, ensure_ascii=False, indent=0), encoding="utf-8")


def _mb_get(path: str) -> Any:
    with _mb_net:
        time.sleep(1.05)
        return _json("https://musicbrainz.org/ws/2/" + path, timeout=8)


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _area_country(area: dict) -> tuple[str | None, str | None, bool]:
    """(ISO code, country name, ok) for a MusicBrainz area: a country directly, or found by walking its
    'part of' relations upward (city -> province -> country). Cached by area id; a network failure is not."""
    if not area:
        return None, None, True
    codes = area.get("iso-3166-1-codes") or []
    if codes:
        return codes[0], area.get("name"), True
    aid = area.get("id")
    if not aid:
        return None, None, True
    key = "area:" + aid
    with _mb_lock:
        hit = _mb_disk().get(key)
    if isinstance(hit, dict):
        return hit.get("cc"), hit.get("country"), True
    cur, cc, cname = aid, None, None
    try:
        for _ in range(4):
            d = _mb_get(f"area/{cur}?fmt=json&inc=area-rels")
            if d.get("iso-3166-1-codes"):
                cc, cname = d["iso-3166-1-codes"][0], d.get("name"); break
            up = next((r["area"] for r in d.get("relations", []) if r.get("type") == "part of" and r.get("direction") == "backward" and r.get("area")), None)
            if not up:
                break
            if up.get("iso-3166-1-codes"):
                cc, cname = up["iso-3166-1-codes"][0], up.get("name"); break
            cur = up.get("id")
    except Exception:  # noqa: BLE001  network: try again another time
        return None, None, False
    _mb_save(key, {"cc": cc, "country": cname})
    return cc, cname, True


def mb_info(name: str, network: bool = True, langs: bool = True) -> dict | None:
    """Where an artist comes from, from MusicBrainz (open data, keyless, cached on disk):
    {"cc": ISO country, "country": its name, "city": the area or birthplace city when there is one}.
    {} when MusicBrainz does not know the artist; None when it could not be asked (network)."""
    key = name.lower()
    with _mb_lock:
        disk = _mb_disk()
    if key in disk:
        v = disk[key]
        v = {"cc": v} if isinstance(v, str) and v else (v if isinstance(v, dict) else {})
        if langs and network and v.get("mbid") and v.get("langs") is None:      # looked up for the tour, without languages
            v = dict(v, langs=_release_langs(v["mbid"])); _mb_save(key, v)
        return v
    if not network:
        return None
    try:
        q = name.replace('"', " ")
        d = _mb_get("artist/?fmt=json&limit=5&query=" + urllib.parse.quote(f'artist:"{q}" OR alias:"{q}"'))
    except Exception:  # noqa: BLE001
        return None
    want, out = _norm(name), {}
    for a in d.get("artists", []):
        names = {_norm(a.get("name") or ""), _norm(a.get("sort-name") or "")} | {_norm(x.get("name") or "") for x in (a.get("aliases") or [])}
        top = a is (d.get("artists") or [None])[0] and int(a.get("score", 0)) == 100
        if int(a.get("score", 0)) < 90 or (want not in names and not top):
            continue
        area, begin = a.get("area") or {}, a.get("begin-area") or {}
        cc = a.get("country"); cname = area.get("name") if area.get("type") == "Country" else None
        city = next((x.get("name") for x in (area, begin) if x.get("type") in ("City", "Municipality", "District") and x.get("name")), None)
        if not cc:
            cc, cname, ok = _area_country(area if area else begin)
            if not ok:
                return None
        if not cc and begin:
            cc, cname, ok = _area_country(begin)
            if not ok:
                return None
        if cc or a.get("id"):
            names_all = [a.get("name") or ""] + [x.get("name") or "" for x in (a.get("aliases") or [])]
            out = {"cc": cc, "country": cname, "city": city, "mbid": a.get("id"), "langs": _release_langs(a.get("id")) if langs else None,
                   "aliases": [x for x in dict.fromkeys(names_all) if x][:10]}
            break
    _mb_save(key, out)
    return out


def _release_langs(mbid: str | None) -> dict[str, float] | None:
    """The languages an artist's releases are written in (MusicBrainz text-representation, ISO 639-3),
    as shares: {"fas": 0.9, "eng": 0.1}. Language, more than borders, is what listeners share."""
    if not mbid:
        return {}
    try:
        d = _mb_get(f"release?artist={mbid}&fmt=json&limit=60")
    except Exception:  # noqa: BLE001  None, not {}: a failure is retried next time, an artist with no releases is not
        return None
    c: dict[str, int] = {}
    for r in d.get("releases", []):
        lang = (r.get("text-representation") or {}).get("language")
        if lang and lang not in ("mul", "zxx", "und", "qaa"):
            c[lang] = c.get(lang, 0) + 1
    tot = sum(c.values())
    return {k: round(v / tot, 2) for k, v in sorted(c.items(), key=lambda kv: -kv[1])[:3]} if tot else {}


def mb_country(name: str) -> str | None:
    v = mb_info(name, langs=False)
    return (v or {}).get("cc") or None


def _track_of(artist: str, title: str | None = None) -> dict | None:
    tracks = [t for t in prev.previews(artist, 8) if artist.split()[0].lower() in (t.get("artist") or "").lower()]
    if title:
        tw = title.lower()
        tracks.sort(key=lambda t: 0 if tw in (t.get("title") or "").lower() else 1)
    if not tracks:
        return None
    t = dict(tracks[0])
    t["stream"] = "/api/preview/stream?u=" + urllib.parse.quote(t["preview"], safe="")
    return t


def song_for(stop: dict[str, Any], qloo_artists: list[dict[str, Any]]) -> dict[str, Any] | None:
    """1. an artist Qloo says the city loves AND MusicBrainz places in that country;
    2. otherwise the next of the country's own loved artists (rotating, so every visit sounds new)."""
    for a in qloo_artists[:5]:
        if mb_country(a["name"]) == stop["cc"]:
            t = _track_of(a["name"])
            if t:
                t["why"] = "qloo+musicbrainz"; t["because"] = f"{stop['city']} loves {a['name']} (Qloo), from {stop['country']} (MusicBrainz)"
                return t
    n = _visits.get(stop["city"], 0); _visits[stop["city"]] = n + 1
    names = stop["loved"]; titles = {a: t for a, t in stop.get("classics", [])}
    for k in range(len(names)):
        artist = names[(n + k) % len(names)]
        t = _track_of(artist, titles.get(artist))
        if t:
            t["why"] = "loved in " + stop["country"]; t["because"] = f"a song {stop['country']} loves"
            return t
    return None


# ---------------------------------------------------------------- what the city loves now (Qloo)
def _slim(e: dict[str, Any]) -> dict[str, Any]:
    props = e.get("properties") or {}
    img = props.get("image") if isinstance(props, dict) else None
    return {"name": e.get("name"), "entity_id": e.get("entity_id"), "affinity": (e.get("query") or {}).get("affinity"),
            "image": img.get("url") if isinstance(img, dict) else None}


def qloo_loves(client: QlooClient, stop: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    try:
        ents = client.insights("artist", take=8, label=f"tour.{stop['city']}", **{"signal.location.query": stop["city"]})
        if ents:
            return [_slim(e) for e in ents if e.get("name")], "qloo location signal"
    except QlooError:
        pass
    try:
        ents = client.insights("artist", take=8, label=f"tour.genre.{stop['genre']}", **{"filter.tags": "urn:tag:genre:music:" + stop["genre"]})
        if ents:
            return [_slim(e) for e in ents if e.get("name")], "qloo genre tag"
    except QlooError:
        pass
    return [], "none"


def tour_for(client: QlooClient, stop: dict[str, Any]) -> dict[str, Any]:
    from . import fullsong
    artists, how = qloo_loves(client, stop)
    song = song_for(stop, artists)
    if song and fullsong.enabled():
        song["yt"] = fullsong.find(song.get("artist") or "", song.get("title") or "")
    # the film of the city: a 4K aerial found on YouTube (muted, the song plays over it), else the author's own links
    videos = []
    if fullsong.enabled():
        v = fullsong.city_video(stop["city"], stop["country"])
        if v:
            videos.append(v)
    videos += videos_for(stop["city"])
    return {"stop": public(stop), "videos": videos, "photos": photos(stop), "classic": song,
            "artists": artists[:6], "source": how, "tracks": [song] if song else []}


# ---------------------------------------------------------------- warm-up: every city ready before it is visited
_warm_started = False


def warm(client: QlooClient) -> None:
    """Once per server start, in the background: Qloo artists, MusicBrainz countries, the song, the
    photos and the city film for every stop, so a visit only reads caches."""
    global _warm_started
    if _warm_started or client.offline:
        return
    _warm_started = True

    def run():
        from . import fullsong
        for stop in TOUR:
            try:
                artists, _ = qloo_loves(client, stop)
                for a in artists[:5]:
                    mb_country(a["name"])
                for artist in stop["loved"][:2]:
                    _track_of(artist)
                photos(stop)
                if fullsong.enabled():
                    fullsong.city_video(stop["city"], stop["country"])
            except Exception:  # noqa: BLE001  a warm-up never breaks anything
                pass
    threading.Thread(target=run, daemon=True, name="tour-warm").start()
