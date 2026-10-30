"""Evidence retrieval for "why" questions: a small, deterministic retriever over the protocol
registry and a curated knowledge base (no vector service needed; TF-IDF cosine over short
passages). Every answer cites the passage it came from, so nothing is said without a source."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent.parent / "data"
_INDEX: list[dict[str, Any]] | None = None
_DF: Counter | None = None
TOK = re.compile(r"[a-z0-9]+")


def _tokens(s: str) -> list[str]:
    return TOK.findall(s.lower())


def _build() -> None:
    global _INDEX, _DF
    docs: list[dict[str, Any]] = []
    P = json.loads((DATA / "protocols.json").read_text(encoding="utf-8"))
    for p in P["protocols"]:
        docs.append({"id": f"protocol:{p['id']}", "title": p["name"], "text": p["summary"], "source": "Reach protocol registry", "url": ""})
        for e in p["evidence"]:
            docs.append({"id": f"evidence:{p['id']}:{e['claim'][:30]}", "title": e["claim"], "text": f"{e['claim']}. Grade {e['grade']}. {e['note']}", "source": e["source"], "url": e.get("url", "")})
    docs.append({"id": "safety", "title": "Safety", "text": " ".join(str(v) for v in P["safety"].values()), "source": "WHO-ITU H.870; Epilepsy Society", "url": "https://www.who.int/publications/i/item/9789241515276"})
    docs.append({"id": "genes", "title": "Music and gene activity", "text": P.get("gene_note", ""), "source": "Kanduri 2015 PeerJ; Bhasin 2013 PLoS One", "url": "https://peerj.com/articles/830"})
    kb = DATA / "knowledge.json"
    if kb.exists():
        for d in json.loads(kb.read_text(encoding="utf-8")):
            docs.append(d)
    for d in docs:
        d["tf"] = Counter(_tokens(d["title"] + " " + d["text"]))
    df: Counter = Counter()
    for d in docs:
        df.update(set(d["tf"]))
    _INDEX, _DF = docs, df


def retrieve(query: str, k: int = 3) -> list[dict[str, Any]]:
    if _INDEX is None:
        _build()
    q = Counter(_tokens(query))
    if not q:
        return []
    N = len(_INDEX)
    def w(term: str, tf: int) -> float:
        return (1 + math.log(tf)) * math.log((N + 1) / (1 + _DF.get(term, 0)))
    qv = {t: w(t, c) for t, c in q.items()}
    qn = math.sqrt(sum(v * v for v in qv.values())) or 1.0
    scored = []
    for d in _INDEX:
        dv = {t: w(t, c) for t, c in d["tf"].items()}
        dn = math.sqrt(sum(v * v for v in dv.values())) or 1.0
        dot = sum(qv[t] * dv.get(t, 0) for t in qv)
        if dot > 0:
            scored.append((dot / (qn * dn), d))
    scored.sort(key=lambda x: -x[0])
    return [{"score": round(s, 3), "title": d["title"], "text": d["text"], "source": d["source"], "url": d["url"]} for s, d in scored[:k]]
