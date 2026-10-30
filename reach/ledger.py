"""Hash-chained audit ledger. Every step the agent takes is appended with the hash of the
previous entry, so a reviewer can verify after the fact that the trace shown was the trace
run and nothing was dropped or reordered."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

GENESIS = "0" * 64


class Ledger:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    @staticmethod
    def _canon(x: Any) -> Any:
        """JSON round-trips turn 1.0 into 1; hash a form that survives that."""
        if isinstance(x, float):
            return int(x) if x.is_integer() else round(x, 10)
        if isinstance(x, dict):
            return {str(k): Ledger._canon(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [Ledger._canon(v) for v in x]
        return x

    @staticmethod
    def _digest(prev: str, entry: dict[str, Any]) -> str:
        body = json.dumps(Ledger._canon(entry), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        return hashlib.sha256((prev + body).encode()).hexdigest()

    def append(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        prev = self.entries[-1]["hash"] if self.entries else GENESIS
        entry = {"i": len(self.entries), "t": round(time.time(), 3), "kind": kind, "payload": payload}
        entry["prev"] = prev
        entry["hash"] = self._digest(prev, {k: entry[k] for k in ("i", "t", "kind", "payload")})
        self.entries.append(entry)
        return entry

    def verify(self) -> dict[str, Any]:
        prev = GENESIS
        for e in self.entries:
            if e["prev"] != prev:
                return {"ok": False, "at": e["i"], "reason": "prev hash mismatch"}
            h = self._digest(prev, {k: e[k] for k in ("i", "t", "kind", "payload")})
            if h != e["hash"]:
                return {"ok": False, "at": e["i"], "reason": "entry hash mismatch"}
            prev = h
        return {"ok": True, "length": len(self.entries), "head": prev}

    @staticmethod
    def verify_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
        l = Ledger(); l.entries = entries
        return l.verify()

    def head(self) -> str:
        return self.entries[-1]["hash"] if self.entries else GENESIS
