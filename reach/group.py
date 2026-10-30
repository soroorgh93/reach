"""Group sessions: several people, one room, one sound.

Members come from the UI (name + favourites) or from the request text ("I'm with four friends;
one is into Indian music, one wants no vocals"). Each member gets their own Qloo reading; the
candidate artists are scored per member; then the group decision is adjudicated with Bayes
(best on average), minimax (least-bad for the unhappiest member) and the least-favourable
prior found by multiplicative weights, which says who the session must satisfy to be robust.
"""
from __future__ import annotations

import re
from typing import Any

import numpy as np

from .decision import group_adjudicate
from .qloo import QlooClient, QlooError
from .taste import TasteAgent, GENRE_URN

GENRE_WORDS = {
    "rock": "rock", "metal": "metal", "pop": "pop", "jazz": "jazz", "classical": "classical", "hip hop": "hip_hop", "hip-hop": "hip_hop", "rap": "hip_hop",
    "indian": "indian", "bollywood": "bollywood", "latin": "latin", "reggaeton": "reggaeton", "salsa": "salsa", "persian": "persian", "iranian": "persian",
    "arabic": "arabic", "turkish": "turkish", "k-pop": "k_pop", "kpop": "k_pop", "korean": "k_pop", "chinese": "mandopop", "c-pop": "mandopop", "japanese": "j_pop",
    "electronic": "electronic", "techno": "techno", "house": "house", "edm": "edm", "country": "country", "folk": "folk", "blues": "blues", "soul": "soul",
    "r&b": "r_b", "reggae": "reggae", "afrobeat": "afrobeat", "afrobeats": "afrobeats", "ambient": "ambient", "lo-fi": "lo_fi", "lofi": "lo_fi", "classic": "classical",
    "instrumental": "instrumental", "no vocals": "instrumental", "no voice": "instrumental", "without lyrics": "instrumental", "meditation": "new_age", "opera": "opera",
}
DESC = r"(.+?)(?=\s+(?:and|but|while|whereas)\b|[,.;!?]|$)"
MEMBER_PATTERNS = [
    r"(?:my|a|another|one|the other|other)\s+(?:friend|brother|sister|mother|father|mom|dad|son|daughter|partner|wife|husband|colleague|kid)s?\s+(?:is into|likes?|loves?|wants?|prefers?|listens? to)\s+" + DESC,
    r"(?:one|another|someone|somebody|the other one|the others?)\s+(?:of us|of them)?\s*(?:is into|likes?|loves?|wants?|prefers?)\s+" + DESC,
    r"(?-i:\b(?!She\b|He\b|They\b|We\b|It\b|You\b|My\b|Her\b|His\b|Our\b|The\b|Everyone\b|Someone\b|Nobody\b|People\b|Then\b|And\b|But\b)([A-Z][a-z]+))\s+(?:is into|likes|loves|wants|prefers|listens to)\s+" + DESC,
]
COUNT_PATTERN = r"(?:with|we are|we're|there are)\s+(\d+|two|three|four|five|six|seven|eight)\s+(?:of (?:us|my|them|our)\s+)?(?:friends|people|colleagues|kids|children|of us)"
WORDS_TO_NUM = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}


def parse_members(text: str) -> tuple[list[dict[str, Any]], int | None]:
    """Pull members and their stated tastes out of free text. Returns (members, stated count)."""
    t = text or ""
    members: list[dict[str, Any]] = []
    taken: list[tuple[int, int]] = []
    for pat in MEMBER_PATTERNS:
        for m in re.finditer(pat, t, flags=re.I):
            if any(a <= m.start() < b or a < m.end() <= b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            if m.lastindex == 2:
                name, desc = m.group(1), m.group(2)
            else:
                name, desc = f"friend {len(members) + 1}", m.group(1)
            desc_l = desc.lower().strip()
            genres = sorted({tag for word, tag in GENRE_WORDS.items() if word in desc_l})
            needs = {"vocals": False} if any(w in desc_l for w in ("no vocal", "no voice", "without lyrics", "instrumental")) else {}
            # anything that is not a genre word may be an artist name ("likes Shakira")
            artist = None
            if not genres and len(desc_l.split()) <= 4:
                artist = desc.strip().rstrip(".")
            members.append({"name": name.strip(), "genres": genres, "artist": artist, "needs": needs, "favorites": []})
    count = None
    m = re.search(COUNT_PATTERN, t, flags=re.I)
    if m:
        v = m.group(1).lower(); count = int(v) if v.isdigit() else WORDS_TO_NUM.get(v)
    return members, count


class GroupAgent:
    def __init__(self, client: QlooClient):
        self.client = client
        self.taste = TasteAgent(client)

    def _member_profile(self, m: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
        favs = [dict(f) for f in (m.get("favorites") or []) if isinstance(f, dict) and f.get("name")][:4]
        # favourites typed by name (the start page's "With others"): look each one up in Qloo
        for f in favs:
            if not f.get("entity_id") and not self.client.offline:
                try:
                    r = self.client.resolve(str(f["name"])[:80], f.get("type") or "artist")
                    if r:
                        f["entity_id"] = r["entity_id"]; f["name"] = r["name"]
                except QlooError:
                    pass
        if m.get("artist") and not favs and not self.client.offline:
            try:
                r = self.client.resolve(m["artist"], "artist")
                if r:
                    favs = [{"name": r["name"], "entity_id": r["entity_id"], "type": "artist"}]
            except QlooError:
                pass
        prof = {"id": f"member-{re.sub(r'[^a-z0-9]+', '-', m['name'].lower())}", "name": m["name"], "age": base.get("age", 30), "city": base.get("city", ""),
                "favorites": favs, "favorite_tags": [GENRE_URN + g for g in m.get("genres", [])], "consent": {"taste": True}, "capacities": base.get("capacities", {})}
        return prof

    def read(self, host: dict[str, Any], members: list[dict[str, Any]], protocol: dict[str, Any], memory: dict[str, Any] | None = None) -> dict[str, Any]:
        """host: the signed-in person's profile; members: the others. Returns a group taste report."""
        people = [("you", host)] + [(m["name"], self._member_profile(m, host)) for m in members]
        readings: list[tuple[str, dict[str, Any]]] = []
        unread: list[str] = []
        for name, prof in people:
            if not (prof.get("favorites") or prof.get("favorite_tags")):
                unread.append(name); continue
            T = self.taste.read(prof, protocol, memory if name == "you" else None)
            if T.get("ok"):
                readings.append((name, T))
            else:
                unread.append(name)
        if not readings:
            return {"ok": False, "reason": "no member could be read through Qloo"}
        # candidate pool: union of everyone's carriers; score per member by affinity (0 when absent)
        pool: dict[str, dict[str, Any]] = {}
        for _, T in readings:
            for c in T["carrier"]:
                if c.get("entity_id"):
                    pool.setdefault(c["entity_id"], c)
        ids = list(pool)
        names = [n for n, _ in readings]
        U = np.zeros((len(readings), len(ids)))
        for j, (_, T) in enumerate(readings):
            aff = {c["entity_id"]: c["affinity"] for c in T["carrier"] if c.get("entity_id")}
            for i, eid in enumerate(ids):
                U[j, i] = aff.get(eid, 0.0)
        adj = group_adjudicate(U, ids, names)
        carrier = [dict(pool[r["id"]], per_member=r["per_member"], fairness=r["final"]) for r in adj["ranking"][:8]]
        needs_instrumental = any((m.get("needs") or {}).get("vocals") is False for m in members)
        palettes = [T.get("palette") for _, T in readings]
        palette = max(set(palettes), key=palettes.count)
        texture = sorted({t for _, T in readings for t in T.get("texture_tags", [])[:4]})[:8]
        return {"ok": True, "members": names, "unread": unread, "carrier": carrier, "adjudication": {k: (pool[adj[k]].get("name", adj[k]) if isinstance(adj[k], str) and adj[k] in pool else adj[k]) for k in ("bayes", "minimax", "lfp", "weights")},
                "palette": palette, "texture_tags": texture, "instrumental": needs_instrumental, "source": readings[0][1].get("source"),
                "strength": float(np.mean([T.get("strength", 0.88) for _, T in readings])), "data_weight": float(np.mean([T.get("data_weight", 0) for _, T in readings])),
                "fit_rate": float(np.mean([T.get("fit_rate", 1) for _, T in readings])), "tempo_bias": float(np.mean([T.get("tempo_bias", 0) for _, T in readings])),
                "mood_bias": float(np.mean([T.get("mood_bias", 0) for _, T in readings])), "sent": readings[0][1].get("sent", []), "per_member": {n: [c["name"] for c in T["carrier"][:3]] for n, T in readings}}
