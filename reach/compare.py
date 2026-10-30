"""Without Qloo: what a generic model would hand this person, measured against them.

A generic calm/focus/sleep list is what any language model produces without taste data (the
same five names for everyone). Reach resolves those names to Qloo entities and asks Qloo how
strongly each one actually sits in *this* person's taste, then compares with the carrier the
council built. The lift is the number judges can check: mean affinity to the person, and how
many of the generic picks do not appear anywhere in the person's top fifty.
"""
from __future__ import annotations

from typing import Any

from .qloo import QlooClient, QlooError
from .taste import favourite_ids

GENERIC = {
    "calm": ["Marconi Union", "Enya", "Brian Eno", "Ludovico Einaudi", "Norah Jones"],
    "sleep": ["Max Richter", "Brian Eno", "Sigur Rós", "Nils Frahm", "Enya"],
    "focus": ["Hans Zimmer", "Tycho", "Bonobo", "Ólafur Arnalds", "Explosions in the Sky"],
    "mood": ["Pharrell Williams", "Bill Withers", "Stevie Wonder", "Coldplay", "Bob Marley"],
    "autism_calm": ["Raffi", "The Wiggles", "Enya", "Yo-Yo Ma", "Mister Rogers"],
    "memory": ["Frank Sinatra", "The Beatles", "Elvis Presley", "Nat King Cole", "ABBA"],
    "energy": ["David Guetta", "Calvin Harris", "Dua Lipa", "Daft Punk", "Avicii"],
}


def compare(client: QlooClient, profile: dict[str, Any], goal: str, carrier: list[dict[str, Any]]) -> dict[str, Any]:
    names = GENERIC.get(goal, GENERIC["calm"])
    ids = favourite_ids(profile)
    if not ids or client.offline:
        return {"ok": False, "reason": "needs live Qloo and resolved favourites", "generic": names}
    generic: list[dict[str, Any]] = []
    for n in names:
        try:
            r = client.resolve(n, "artist")
        except QlooError:
            r = None
        generic.append({"name": n, "entity_id": r["entity_id"] if r else None})
    try:
        top = client.insights("artist", entities=ids, take=50, label=f"{profile.get('id', 'p')}.compare.top50")
    except QlooError as e:
        return {"ok": False, "reason": str(e), "generic": names}
    aff = {e.get("entity_id"): float((e.get("query") or {}).get("affinity") or 0) for e in top}
    floor = min(aff.values()) if aff else 0.0
    for g in generic:
        g["affinity"] = aff.get(g["entity_id"]) if g["entity_id"] in aff else None
        g["in_top50"] = g["entity_id"] in aff
    mean_generic = sum((g["affinity"] if g["affinity"] is not None else floor * 0.9) for g in generic) / max(len(generic), 1)
    mean_carrier = sum(c.get("affinity", 0) for c in carrier[:5]) / max(min(len(carrier), 5), 1)
    return {"ok": True, "goal": goal, "generic": generic, "carrier": [{"name": c["name"], "affinity": c.get("affinity")} for c in carrier[:5]],
            "mean_generic": round(mean_generic, 3), "mean_carrier": round(mean_carrier, 3), "floor_top50": round(floor, 3),
            "generic_missing": sum(1 for g in generic if not g["in_top50"]), "lift": round(mean_carrier - mean_generic, 3)}
