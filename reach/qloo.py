"""Qloo Insights client for Reach.

Design rules (from the hackathon kit and from what the API does in practice):
  * The key lives only in the QLOO_API_KEY environment variable, server side.
  * Every parameter is checked against an allowlist per filter.type before a request
    is built, because the API silently ignores unknown parameters and a silent ignore
    is worse than a loud refusal.
  * Requests are spaced out (the hackathon tier returns 429 on bursts) and cached by
    the SHA-256 of the canonical query string.
  * GET only. No personal or clinical data ever leaves the server: only entity ids,
    tag ids, a city name and demographic buckets are sent.
  * Fixture mode: with no key, or with REACH_OFFLINE=1, recorded responses are
    served from data/fixtures.json so the demo never depends on the network.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = os.environ.get("QLOO_BASE_URL", "https://hackathon.api.qloo.com")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ENTITY_TYPES = {
    "artist", "book", "brand", "destination", "movie", "person", "place",
    "podcast", "tv_show", "video_game",
}

# Parameters accepted for every insights call.
COMMON_PARAMS = {
    "filter.type", "take", "page", "feature.explainability",
    "signal.interests.entities", "signal.interests.tags",
    "signal.demographics.age", "signal.demographics.gender", "signal.location.query", "signal.location", "signal.location.radius",
    "filter.tags", "filter.exclude.tags", "filter.popularity.min",
    "filter.exclude.entities", "operator.filter.tags", "filter.parents.types",
    "filter.query",
}
# Parameters that only make sense for some result types.
TYPE_PARAMS = {
    "urn:entity:place": {"filter.location.query", "filter.location", "filter.location.radius",
                         "filter.rating.min", "filter.price_level.max", "filter.hours"},
    "urn:entity:destination": {"filter.location.query", "filter.location", "filter.location.radius"},
    "urn:entity:movie": {"filter.content_rating", "filter.release_year.min", "filter.release_year.max"},
    "urn:entity:tv_show": {"filter.content_rating", "filter.release_year.min", "filter.release_year.max"},
    "urn:entity:book": {"filter.publication_year.min", "filter.publication_year.max"},
    "urn:entity:video_game": {"filter.release_year.min", "filter.release_year.max"},
    "urn:heatmap": {"filter.location.query", "filter.location"},
    "urn:tag": {"filter.tag.types", "filter.parents.types"},
    "urn:demographics": set(),
}


class QlooError(Exception):
    pass


class ParamRefused(QlooError):
    """Raised before any request is sent, when a parameter is not allowed for the type."""


class QlooClient:
    def __init__(self, api_key: str | None = None, offline: bool | None = None,
                 min_interval: float = 0.35, fixtures_path: Path | None = None):
        self.api_key = api_key if api_key is not None else os.environ.get("QLOO_API_KEY", "")
        env_offline = os.environ.get("REACH_OFFLINE", "") == "1"
        self.offline = bool(offline) if offline is not None else (env_offline or not self.api_key)
        self.min_interval = min_interval
        self._last_call = 0.0
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, Any] = OrderedDict()   # FIFO/LRU: the newest 512 responses stay hot
        self.cache_max = 512
        self.calls: list[dict[str, Any]] = []     # audit of every call (no key, no persona data)
        self.fixtures_path = fixtures_path or DATA_DIR / "fixtures.json"
        self._fixtures: dict[str, Any] | None = None
        self.record: dict[str, Any] | None = None  # set to a dict to record live responses

    # ---------------------------------------------------------------- fixtures
    def _fixture_for(self, key: str, label: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Exact key, then exact label, then the same entity set + type under another persona id
        (a profile edited in the Studio is "you", its favourites are still the recorded ones),
        then a protocol-filtered carrier falling back to the general carrier."""
        calls = self._load_fixtures()["calls"]
        fx = calls.get(key) or calls.get(label)
        if fx is not None:
            return fx
        want_type = str(params.get("filter.type", ""))
        ents = params.get("signal.interests.entities")
        want = set(ents if isinstance(ents, list) else str(ents or "").split(",")) - {""}
        suffix = label.split(".", 1)[1] if "." in label else label
        best = None
        for k, v in calls.items():
            path = v.get("path", "")
            if f"filter.type={want_type}" not in path:
                continue
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
            have = set(",".join(q.get("signal.interests.entities", [])).split(",")) - {""}
            if want and have == want:
                ks = k.split(".", 1)[1] if "." in k else k
                if ks == suffix:
                    return v
                if best is None and (ks.endswith("artist.general") or suffix.endswith("artist.fit")):
                    best = v
        if best is None and label.endswith(".artist.fit"):
            best = calls.get(label.split(".")[0] + ".artist.general")
        return best

    def _load_fixtures(self) -> dict[str, Any]:
        if self._fixtures is None:
            try:
                self._fixtures = json.loads(self.fixtures_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                self._fixtures = {"calls": {}}
        return self._fixtures

    # ---------------------------------------------------------------- building
    @staticmethod
    def canonical(path: str, params: dict[str, Any]) -> str:
        items = []
        for k in sorted(params):
            v = params[k]
            if v is None or v == "" or v == []:
                continue
            if isinstance(v, (list, tuple)):
                v = ",".join(str(x) for x in v)
            elif isinstance(v, bool):
                v = "true" if v else "false"
            items.append((k, str(v)))
        return path + "?" + urllib.parse.urlencode(items, safe=":,")

    @staticmethod
    def key_for(canon: str) -> str:
        return hashlib.sha256(canon.encode()).hexdigest()[:16]

    @staticmethod
    def check_params(params: dict[str, Any]) -> None:
        ftype = params.get("filter.type", "")
        allowed = COMMON_PARAMS | TYPE_PARAMS.get(ftype, set())
        bad = [k for k in params if k not in allowed]
        if bad:
            raise ParamRefused(f"parameters not allowed for {ftype or 'this call'}: {', '.join(bad)}")
        if "take" in params and not (1 <= int(params["take"]) <= 50):
            raise ParamRefused("take must be between 1 and 50")

    # ---------------------------------------------------------------- transport
    def _http_get(self, url: str) -> tuple[int, Any]:
        req = urllib.request.Request(url, headers={"X-Api-Key": self.api_key, "Accept": "application/json"})
        for attempt in range(4):
            with self._lock:
                wait = self.min_interval - (time.monotonic() - self._last_call)
                if wait > 0:
                    time.sleep(wait)
                self._last_call = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 3:
                    time.sleep(0.6 * (attempt + 1))
                    continue
                try:
                    body = json.loads(e.read().decode())
                except Exception:
                    body = {"error": str(e)}
                return e.code, body
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < 3:
                    time.sleep(0.4)
                    continue
                raise QlooError(f"network: {e}") from e
        raise QlooError("unreachable")

    def get(self, path: str, params: dict[str, Any], label: str = "") -> dict[str, Any]:
        """Return {"status", "data", "source", "key", "ms"}; source is live|cache|fixture|none."""
        if path == "/v2/insights":
            self.check_params(params)
        canon = self.canonical(path, params)
        key = self.key_for(canon)
        t0 = time.monotonic()
        if key in self._cache:
            self._cache.move_to_end(key)
            out = dict(self._cache[key]); out["source"] = "cache"
        elif self.offline:
            fx = self._fixture_for(key, label, params)
            if fx is None:
                out = {"status": 0, "data": {"results": {}}, "source": "none"}
            else:
                out = {"status": 200, "data": fx["data"], "source": "fixture"}
        else:
            status, data = self._http_get(BASE_URL + canon)
            out = {"status": status, "data": data if status == 200 else {"results": {}, "error": data}, "source": "live"}
            if status == 200:
                self._cache[key] = dict(out)
                while len(self._cache) > self.cache_max:
                    self._cache.popitem(last=False)
                if self.record is not None:
                    self.record[key] = {"label": label, "path": canon, "data": slim(data)}
        out["key"] = key
        out["path"] = canon
        out["ms"] = round((time.monotonic() - t0) * 1000)
        self.calls.append({"label": label, "key": key, "path": canon, "status": out["status"],
                           "source": out["source"], "ms": out["ms"]})
        return out

    # ---------------------------------------------------------------- helpers
    def insights(self, ftype: str, *, entities: list[str] | None = None, tags: list[str] | None = None,
                 take: int = 10, label: str = "", **extra: Any) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"filter.type": f"urn:entity:{ftype}" if ftype in ENTITY_TYPES else ftype,
                                  "take": take, "feature.explainability": True}
        if entities:
            params["signal.interests.entities"] = entities
        if tags:
            params["signal.interests.tags"] = tags
        params.update(extra)
        out = self.get("/v2/insights", params, label=label or f"insights.{ftype}")
        res = out["data"].get("results", {})
        ents = res.get("entities") or res.get("tags") or []
        for e in ents:
            e["_source"] = out["source"]
        return ents

    def search(self, query: str, types: list[str] | None = None, take: int = 5) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"query": query, "take": take}
        if types:
            params["types"] = ",".join(f"urn:entity:{t}" for t in types)
        out = self.get("/search", params, label=f"search.{query.lower()}")
        return out["data"].get("results", []) if isinstance(out["data"], dict) else []

    def resolve(self, name: str, etype: str) -> dict[str, Any] | None:
        for r in self.search(name, [etype], take=5):
            if r.get("name", "").lower().startswith(name.lower()[:6]):
                return {"name": r["name"], "entity_id": r["entity_id"], "type": etype}
        return None


def slim(data: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields Reach reads, so fixtures stay small and hold no raw dump."""
    res = data.get("results", {})
    out: dict[str, Any] = {"results": {}}
    if "entities" in res:
        ents = []
        for e in res["entities"]:
            q = e.get("query", {}) or {}
            p = e.get("properties", {}) or {}
            ents.append({
                "name": e.get("name"), "entity_id": e.get("entity_id"), "subtype": e.get("subtype"),
                "popularity": e.get("popularity"),
                "query": {"affinity": q.get("affinity"), "explainability": q.get("explainability")},
                "tags": [{"name": t.get("name"), "tag_id": t.get("tag_id"), "type": t.get("type")}
                         for t in (e.get("tags") or [])[:12]],
                "properties": {k: p.get(k) for k in ("description", "image", "address", "release_year",
                                                      "publication_year", "business_rating", "price_level",
                                                      "geocode", "content_rating", "short_description") if k in p},
            })
        out["results"]["entities"] = ents
    if "tags" in res:
        out["results"]["tags"] = [{"name": t.get("name"), "tag_id": t.get("tag_id"), "type": t.get("type"),
                                   "query": t.get("query")} for t in res["tags"]]
    if "demographics" in res:
        out["results"]["demographics"] = res["demographics"]
    if isinstance(data.get("results"), list):
        out = {"results": [{"name": r.get("name"), "entity_id": r.get("entity_id"), "types": r.get("types")}
                           for r in data["results"]]}
    return out
