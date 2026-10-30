"""Engagement scoring: will this person keep doing the intervention?

Each intervention names the Qloo domain that carries its content (artist for a music
intervention, place for an activity, book for bibliotherapy...). Reach asks Qloo for the
top entities in that domain given the person's favourites, then turns affinities into a
single engagement estimate with empirical-Bayes shrinkage, so a domain where Qloo has
little to say is pulled toward the population prior instead of being trusted blindly.

A personalised PageRank over the taste graph (favourites -> recommended entities ->
interventions) gives a second, structural view of which interventions the person's taste
actually flows into; it is reported alongside the shrunk affinity and blended in.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .qloo import QlooClient, QlooError, ParamRefused
from .reachability import PROVIDER_CATEGORY

# Population prior for the mean affinity of a top-10 list, by domain (observed on the
# hackathon tier: artists cluster near 0.9, places near 0.75, books near 0.85).
DOMAIN_PRIOR = {"artist": 0.88, "book": 0.84, "movie": 0.86, "tv_show": 0.85, "podcast": 0.82,
                "video_game": 0.84, "place": 0.74, "brand": 0.80, "destination": 0.78}
SHRINK_K = 6.0          # pseudo-observations behind the prior
NEUTRAL = 0.5           # engagement when nothing can be said (no domain, no consent, no data)

# Content constraints by audience.
CHILD_OK_RATINGS = {"G", "PG", "TV-Y", "TV-Y7", "TV-G", "TV-PG"}
CHILD_EXCLUDE_TAGS = ["urn:tag:genre:podcast:true_crime", "urn:tag:genre:media:horror",
                      "urn:tag:genre:media:erotic", "urn:tag:genre:media:crime"]
CALM_PLACE_TAGS = ["urn:tag:ambience:place:dim_lighting", "urn:tag:noise_level:qloo:quiet",
                   "urn:tag:ambience:place:calm", "urn:tag:ambience:place:cozy"]


def _affinity(e: dict[str, Any]) -> float:
    q = e.get("query") or {}
    a = q.get("affinity")
    return float(a) if a is not None else 0.0


def shrink(values: list[float], prior: float, k: float = SHRINK_K) -> tuple[float, float]:
    """Empirical-Bayes shrinkage of a mean toward the prior; returns (estimate, weight on data)."""
    n = len(values)
    if n == 0:
        return prior, 0.0
    m = float(np.mean(values))
    w = n / (n + k)
    return w * m + (1 - w) * prior, w


def to_unit(mean_aff: float, domain: str) -> float:
    """Map a shrunk mean affinity to [0,1] relative to what is typical for the domain.
    Affinities live in a narrow band near the top; a logistic around the prior spreads them."""
    prior = DOMAIN_PRIOR.get(domain, 0.8)
    return 1.0 / (1.0 + math.exp(-(mean_aff - prior) / 0.035))


def content_filters(profile: dict[str, Any], domain: str) -> dict[str, Any]:
    age = profile.get("age") or 99
    extra: dict[str, Any] = {}
    if age < 13 and domain in ("movie", "tv_show"):
        extra["filter.content_rating"] = ",".join(sorted(CHILD_OK_RATINGS))
    if age < 16 and domain in ("podcast", "book", "video_game"):
        extra["filter.exclude.tags"] = ",".join(CHILD_EXCLUDE_TAGS)
    return extra


def favourite_ids(profile: dict[str, Any]) -> list[str]:
    return [f["entity_id"] for f in profile.get("favorites", []) if f.get("entity_id")]


def favourite_tags(profile: dict[str, Any]) -> list[str]:
    return list(profile.get("favorite_tags", []))


class EngagementScorer:
    def __init__(self, client: QlooClient):
        self.client = client
        self.queries: list[dict[str, Any]] = []

    def _query(self, domain: str, profile: dict[str, Any], label: str, take: int = 10, **extra: Any) -> list[dict[str, Any]]:
        ids = favourite_ids(profile)
        tags = favourite_tags(profile)
        if not ids and not tags:
            return []
        try:
            ents = self.client.insights(domain, entities=ids or None, tags=tags or None, take=take, label=label, **extra)
        except ParamRefused as e:
            self.queries.append({"label": label, "refused": str(e)})
            return []
        except QlooError as e:
            self.queries.append({"label": label, "error": str(e)})
            return []
        self.queries.append({"label": label, "domain": domain, "n": len(ents),
                             "source": ents[0]["_source"] if ents else "none"})
        return ents

    def recommendations(self, domain: str, profile: dict[str, Any], label: str) -> list[dict[str, Any]]:
        extra = content_filters(profile, domain)
        if domain == "place":
            extra["filter.location.query"] = profile.get("city", "")
            sens = profile.get("sensory", {})
            if sens.get("noise") == "low" or sens.get("light") == "low":
                extra["filter.tags"] = ",".join(CALM_PLACE_TAGS[:2])
                extra["operator.filter.tags"] = "union"
        return self._query(domain, profile, label, **extra)

    def providers_nearby(self, provider: str, profile: dict[str, Any]) -> tuple[int | None, list[dict[str, Any]]]:
        cat = PROVIDER_CATEGORY.get(provider)
        if not cat or not profile.get("city"):
            return None, []
        try:
            ents = self.client.insights("place", entities=favourite_ids(profile) or None, take=5,
                                        label=f"{profile.get('id', 'p')}.provider.{provider}",
                                        **{"filter.location.query": profile["city"], "filter.tags": cat})
        except QlooError:
            return None, []
        if ents and ents[0]["_source"] == "none":
            return None, []
        return len(ents), ents

    def score(self, intervention: dict[str, Any], profile: dict[str, Any], use_qloo: bool = True) -> dict[str, Any]:
        domain = intervention.get("engagement_domain")
        pid = profile.get("id", "p")
        base = {"domain": domain, "score": NEUTRAL, "shrunk_affinity": None, "data_weight": 0.0,
                "entities": [], "note": ""}
        if not domain:
            base["note"] = "no cultural content to personalise"
            base["scored"] = False
            return base
        if not profile.get("consent", {}).get("taste", True):
            base["note"] = "no consent to use favourites"; base["scored"] = False
            return base
        if not use_qloo:
            base["note"] = "Qloo switched off; neutral engagement"; base["scored"] = False
            return base
        domains = ["book", "tv_show", "artist", "place"] if domain == "cross" else [domain]
        ents_all: list[dict[str, Any]] = []
        affs: list[float] = []
        units: list[float] = []
        for d in domains:
            ents = self.recommendations(d, profile, label=f"{pid}.{intervention['id']}.{d}")
            vals = [_affinity(e) for e in ents if _affinity(e) > 0]
            est, w = shrink(vals, DOMAIN_PRIOR.get(d, 0.8))
            units.append(to_unit(est, d) if vals else NEUTRAL)
            affs.append(est)
            for e in ents[:6]:
                e = dict(e); e["_domain"] = d
                ents_all.append(e)
        score = float(np.mean(units))
        n_data = sum(1 for e in ents_all if _affinity(e) > 0)
        base.update({"score": round(score, 3), "shrunk_affinity": round(float(np.mean(affs)), 4),
                     "data_weight": round(n_data / (n_data + SHRINK_K), 3) if n_data else 0.0,
                     "entities": [slim_entity(e) for e in sorted(ents_all, key=_affinity, reverse=True)[:8]],
                     "scored": n_data > 0,
                     "note": "" if n_data else "Qloo returned nothing for this domain; neutral engagement"})
        return base


def slim_entity(e: dict[str, Any]) -> dict[str, Any]:
    p = e.get("properties") or {}
    q = e.get("query") or {}
    ex = (q.get("explainability") or {}).get("signal.interests.entities") or []
    return {
        "name": e.get("name"), "entity_id": e.get("entity_id"), "domain": e.get("_domain") or (e.get("subtype") or "").split(":")[-1],
        "affinity": round(_affinity(e), 3), "popularity": e.get("popularity"),
        "image": (p.get("image") or {}).get("url") if isinstance(p.get("image"), dict) else p.get("image"),
        "address": p.get("address"), "rating": p.get("business_rating"),
        "tags": [t.get("name") for t in (e.get("tags") or [])[:5] if t.get("name")],
        "because": [{"entity_id": x.get("entity_id"), "score": round(float(x.get("score", 0)), 3)} for x in ex[:3]],
        "source": e.get("_source"),
    }


def taste_pagerank(profile: dict[str, Any], scored: dict[str, dict[str, Any]], damping: float = 0.85) -> dict[str, float]:
    """Personalised PageRank on favourites -> entities -> interventions. Returns per-intervention mass."""
    favs = favourite_ids(profile)
    nodes: dict[str, int] = {}
    def nid(x: str) -> int:
        if x not in nodes:
            nodes[x] = len(nodes)
        return nodes[x]
    edges: list[tuple[int, int, float]] = []
    for f in favs:
        nid("fav:" + f)
    for iid, eng in scored.items():
        inode = nid("int:" + iid)
        for e in eng.get("entities", []):
            enode = nid("ent:" + (e.get("entity_id") or e.get("name") or ""))
            for b in e.get("because", []) or []:
                for f in favs:
                    if f and b.get("entity_id") and f.startswith(str(b["entity_id"])[:8]):
                        edges.append((nid("fav:" + f), enode, max(b["score"], 1e-3)))
            if not e.get("because"):
                for f in favs:
                    edges.append((nid("fav:" + f), enode, e.get("affinity", 0.5) / max(len(favs), 1)))
            edges.append((enode, inode, e.get("affinity", 0.5)))
    n = len(nodes)
    if n == 0 or not edges:
        return {iid: 0.0 for iid in scored}
    M = np.zeros((n, n))
    for a, b, w in edges:
        M[b, a] += w
    col = M.sum(axis=0)
    col[col == 0] = 1.0
    M = M / col
    tele = np.zeros(n)
    for f in favs:
        tele[nodes["fav:" + f]] = 1.0 / len(favs)
    if tele.sum() == 0:
        tele[:] = 1.0 / n
    r = tele.copy()
    for _ in range(100):
        r_new = damping * M @ r + (1 - damping) * tele
        if np.abs(r_new - r).sum() < 1e-10:
            break
        r = r_new
    out = {iid: float(r[nodes["int:" + iid]]) if ("int:" + iid) in nodes else 0.0 for iid in scored}
    tot = sum(out.values()) or 1.0
    return {k: round(v / tot, 4) for k, v in out.items()}
