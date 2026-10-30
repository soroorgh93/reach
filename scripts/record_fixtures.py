"""Record real Qloo responses for the demo personas so the app can run offline (and never
die on stage). Run where hackathon.api.qloo.com is reachable:

    set QLOO_API_KEY=...        (Windows)   /   export QLOO_API_KEY=...   (mac/linux)
    python scripts/record_fixtures.py

Writes data/fixtures.json (slimmed responses keyed by the request hash; no raw dumps) and
fills missing entity ids in data/personas.json through /search. The key is read from the
environment only and never written anywhere.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reach.agent import ReachCouncil, ADJACENT
from reach.qloo import QlooClient, QlooError
from reach.taste import favourite_ids
from reach.tour import TOUR


def main() -> None:
    if not os.environ.get("QLOO_API_KEY"):
        sys.exit("QLOO_API_KEY is not set")
    client = QlooClient(offline=False, min_interval=0.6)
    client.record = {}
    personas_path = ROOT / "data" / "personas.json"
    data = json.loads(personas_path.read_text(encoding="utf-8"))
    # 1. resolve favourites that have no entity id
    for p in data["personas"]:
        for f in p["favorites"]:
            if not f.get("entity_id"):
                try:
                    r = client.resolve(f["name"], f.get("type", "artist"))
                except QlooError as e:
                    print("resolve failed", f["name"], e); continue
                if r:
                    f["entity_id"] = r["entity_id"]; print("resolved", f["name"], "->", r["name"], r["entity_id"])
                else:
                    print("NOT FOUND", f["name"])
    personas_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    # 2. run the council for every persona and every goal so all carrier queries are recorded
    council = ReachCouncil(client)
    for p in data["personas"]:
        for goal in ADJACENT:
            r = council.compose_once(p, {"text": p.get("sample_request", ""), "goal": goal, "local_hour": p.get("sample_hour", 12), "lang": p.get("language", "en")})
            print(p["id"], goal, "->", r.get("error") or r["session"]["protocol_id"], "| calls so far", len(client.record))
    # 3. the world tour (location signal per city, genre fallback), podcasts and films per persona
    for stop in TOUR:
        try:
            ents = client.insights("artist", take=8, label=f"tour.{stop['city']}", **{"signal.location.query": stop["city"]})
            print("tour", stop["city"], "->", [e.get("name") for e in ents[:3]])
            if not ents:
                client.insights("artist", take=8, label=f"tour.genre.{stop['genre']}", **{"filter.tags": "urn:tag:genre:music:" + stop["genre"]})
        except QlooError as e:
            print("tour failed", stop["city"], e)
    for p in data["personas"]:
        ids = favourite_ids(p)
        if not ids:
            continue
        for ftype, label in (("podcast", "podcasts"), ("movie", "watch.movie"), ("tv_show", "watch.tv_show")):
            try:
                client.insights(ftype, entities=ids, take=8, label=f"{p['id']}.{label}")
            except QlooError as e:
                print(ftype, "failed", p["id"], e)
        try:
            client.insights("artist", entities=ids, take=50, label=f"{p['id']}.compare.top50")
        except QlooError as e:
            print("compare failed", p["id"], e)
    out = {"_about": "Recorded Qloo responses (slimmed) keyed by request hash. Recorded live on the hackathon tier.",
           "recorded_at": __import__("datetime").datetime.utcnow().isoformat() + "Z", "calls": client.record}
    (ROOT / "data" / "fixtures.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("wrote", len(client.record), "calls to data/fixtures.json")


if __name__ == "__main__":
    main()
