"""Reach as an MCP server: any assistant (Claude, ChatGPT, an agent framework) can ask Reach for a session.

Model Context Protocol over Streamable HTTP, JSON responses: POST /mcp with JSON-RPC 2.0
(initialize, ping, tools/list, tools/call; notifications are acknowledged with 202).

Tools
  compose_session      the full council: favourites -> Qloo -> cultural ranking -> evidence-graded session
  after_the_music      places, a table and a book near the person, from the same taste (Qloo places, books)
  explain_evidence     the graded evidence behind a need, with sources
  reach_vs_chatbot     the last measured comparison with a plain language model

Every tool answers with text an assistant can read aloud, the same data as structured JSON, and a link that
opens the session in the Reach app. Inputs are validated and capped; no personal data beyond what the
assistant passes in is used, and nothing is stored.
"""
from __future__ import annotations

import json
import urllib.parse
from typing import Any, Callable

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
NEEDS = ["sleep", "calm", "focus", "mood", "memory", "energy"]
LANGS = ["en", "es", "fa", "zh"]

TOOLS = [
    {"name": "compose_session",
     "title": "Compose a music-medicine session",
     "description": "Build an evidence-graded music session for one person from what they love. Reach resolves the favourites in Qloo's taste graph, "
                    "plays the person's own artists first, then artists Qloo links to them in their own culture, on a protocol for the need "
                    "(tempo path, gentle pulse band, safe volume). Returns the plan, the evidence grade, the picks with why, and a link to play it.",
     "inputSchema": {"type": "object", "properties": {
         "favourites": {"type": "array", "items": {"type": "string", "maxLength": 80}, "minItems": 1, "maxItems": 8,
                        "description": "Artists, films, shows, books or games the person loves, e.g. [\"Hayedeh\", \"Googoosh\"]"},
         "need": {"type": "string", "enum": NEEDS, "description": "What the session is for"},
         "city": {"type": "string", "maxLength": 60, "description": "Optional: where they are"},
         "language": {"type": "string", "enum": LANGS, "description": "Language of the reply (default en)"},
         "age": {"type": "integer", "minimum": 3, "maximum": 100, "description": "Optional; under 13 gets child limits"},
         "hearing": {"type": "string", "enum": ["full", "partial", "none"], "description": "none = a visual and vibration session"},
         "request": {"type": "string", "maxLength": 300, "description": "Optional: their own words, e.g. 'no vocals, softer'"}},
         "required": ["favourites", "need"]},
     "annotations": {"readOnlyHint": True, "openWorldHint": True}},
    {"name": "after_the_music",
     "title": "One gentle next step after the session",
     "description": "Places that suit the need (a park after calm, a library after focus; never a bar), a restaurant people with the same taste love "
                    "(the kitchen of the songs after a memory session) and a book, near the person's city, from Qloo's taste graph, each with which favourite it is close to.",
     "inputSchema": {"type": "object", "properties": {
         "favourites": {"type": "array", "items": {"type": "string", "maxLength": 80}, "minItems": 1, "maxItems": 8},
         "need": {"type": "string", "enum": NEEDS},
         "city": {"type": "string", "maxLength": 60},
         "age": {"type": "integer", "minimum": 3, "maximum": 100}},
         "required": ["favourites", "need", "city"]},
     "annotations": {"readOnlyHint": True, "openWorldHint": True}},
    {"name": "explain_evidence",
     "title": "Evidence behind a need",
     "description": "The protocols Reach uses for a need, with evidence grades (A = meta-analysis or several trials ... D = mechanism only), the claims, and their sources.",
     "inputSchema": {"type": "object", "properties": {"need": {"type": "string", "enum": NEEDS}}, "required": ["need"]},
     "annotations": {"readOnlyHint": True}},
    {"name": "reach_vs_chatbot",
     "title": "Reach compared with a plain chatbot",
     "description": "The last measured comparison (scripts/bench.py): the same people asked a generic playlist, a language model and Reach for music; share of picks from their culture, songs that exist, calm picks for sleep, and personalisation.",
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": {"readOnlyHint": True}},
]


class ToolError(Exception):
    pass


def _str_list(v: Any, n: int = 8) -> list[str]:
    if not isinstance(v, list):
        raise ToolError("favourites must be a list of names")
    out = [str(x).strip()[:80] for x in v if str(x).strip()][:n]
    if not out:
        raise ToolError("add at least one favourite")
    return out


def _need(v: Any) -> str:
    if v not in NEEDS:
        raise ToolError(f"need must be one of {', '.join(NEEDS)}")
    return v


def _profile(args: dict[str, Any]) -> dict[str, Any]:
    favs = _str_list(args.get("favourites"))
    age = args.get("age")
    try:
        age = max(3, min(100, int(age))) if age is not None else 30
    except (TypeError, ValueError):
        age = 30
    hearing = args.get("hearing") if args.get("hearing") in ("full", "partial", "none") else "full"
    lang = args.get("language") if args.get("language") in LANGS else "en"
    return {"id": "mcp", "name": "you", "age": age, "city": str(args.get("city") or "")[:60], "language": lang, "targets": [], "flags": [], "sensory": {},
            "favorites": [{"name": n, "type": "artist", "entity_id": None} for n in favs],
            "capacities": {"hearing": hearing, "vision": "full", "reading": "yes", "mobility": "ambulatory", "verbal": "yes"}, "consent": {"taste": True}}


def open_link(base: str, favs: list[str], need: str, city: str = "", lang: str = "en") -> str:
    q = {"love": "|".join(favs), "need": need}
    if city:
        q["city"] = city
    if lang != "en":
        q["lang"] = lang
    return base.rstrip("/") + "/?" + urllib.parse.urlencode(q)


def compose_session(args: dict[str, Any], deps: dict[str, Any]) -> dict[str, Any]:
    need = _need(args.get("need"))
    prof = deps["resolve"](_profile(args))
    if not any(f.get("entity_id") for f in prof["favorites"]):
        raise ToolError("none of these favourites was found in Qloo's taste graph; check the spelling or add another")
    text = str(args.get("request") or "")[:300] or {"sleep": "help me fall asleep", "calm": "I'm anxious, calm me down", "focus": "I need to focus",
                                                      "mood": "lift my mood", "memory": "bring back memories", "energy": "I need energy"}[need]
    r = deps["council"].compose_once(prof, {"text": text, "goal": need, "lang": prof["language"]})
    if r.get("error"):
        raise ToolError(f"Reach refused to compose ({r.get('error')}): {r.get('reason') or 'no taste data from Qloo for these favourites'}")
    s = r.get("session") or {}
    pr = r.get("protocol") or {}
    ev = [{"grade": e.get("grade"), "claim": e.get("claim"), "source": e.get("source"), "url": e.get("url")} for e in (pr.get("evidence") or [])[:3]]
    segs = s.get("segments") or []
    hz = [x for g in segs for x in (g.get("hz_from"), g.get("hz_to")) if x is not None]
    bpm = [g.get("bpm") for g in segs if g.get("bpm")]
    own = [o.get("name") for o in (s.get("own") or []) if o.get("name")][:6]
    picks = [{"name": c.get("name"), "close_to": [b.get("name") for b in (c.get("because") or [])[:2]], "affinity": c.get("affinity")} for c in (s.get("carrier") or [])[:8]]
    calm = s.get("calm_carrier")
    out = {"protocol": s.get("protocol_name"), "need": s.get("goal"), "minutes": s.get("duration_min"),
           "tempo_bpm": [bpm[0], bpm[-1]] if bpm else None, "pulse_hz": [hz[0], hz[-1]] if hz else None, "pulse": s.get("entrainment"),
           "volume_cap_dbfs": s.get("gain_dbfs"), "vocals": s.get("vocals"), "own_artists_first": own, "qloo_picks": picks,
           "plays_calm_instrumentals_instead": bool(calm), "evidence": ev, "gate": r.get("gate"),
           "qloo_calls": len(r.get("qloo_calls") or []), "ledger_head": r.get("ledger_head"),
           "reply": r.get("reply"), "open_in_app": open_link(deps["base"], [f["name"] for f in prof["favorites"]], need, prof["city"], prof["language"])}
    lines = [f"{out['protocol']}, {out['minutes']} minutes."]
    if ev:
        lines.append("Evidence: " + "; ".join(f"grade {e['grade']}, {e['claim']} ({e['source']})" for e in ev[:2]) + ".")
    if calm:
        lines.append("Their favourites are lively, so for this need Reach plays calm instrumental pieces instead of their songs.")
    else:
        if own:
            lines.append("Plays their own artists first: " + ", ".join(own) + ".")
        if picks:
            lines.append("Then Qloo's picks: " + "; ".join(p["name"] + (f" (close to {', '.join(p['close_to'])})" if p["close_to"] else "") for p in picks[:6]) + ".")
    if out["tempo_bpm"] and out["pulse_hz"]:
        lines.append(f"Tempo {out['tempo_bpm'][0]} to {out['tempo_bpm'][1]} beats a minute; {out['pulse'] or 'gentle'} pulse {out['pulse_hz'][0]} to {out['pulse_hz'][1]} Hz "
                     "(entrainment is labelled experimental); volume capped at " + f"{out['volume_cap_dbfs']} dBFS.")
    lines.append(f"Grounded in {out['qloo_calls']} Qloo calls; every step hash-chained (ledger {str(out['ledger_head'])[:12]}…).")
    lines.append("Play it: " + out["open_in_app"])
    return {"text": "\n".join(lines), "data": out}


def after_the_music(args: dict[str, Any], deps: dict[str, Any]) -> dict[str, Any]:
    need = _need(args.get("need"))
    if not str(args.get("city") or "").strip():
        raise ToolError("city is required to find places near the person")
    prof = deps["resolve"](_profile(args))
    d = deps["after"](prof, need)
    def row(x: dict[str, Any]) -> str:
        bits = [x.get("name") or ""]
        if x.get("kitchen"):
            bits.append(f"{x['kitchen']} kitchen")
        elif x.get("category"):
            bits.append(str(x["category"]).replace("_", " "))
        if x.get("km") is not None:
            bits.append(f"{x['km']} km")
        if x.get("because"):
            bits.append("close to " + ", ".join(b["name"] for b in x["because"][:2]))
        return " · ".join(b for b in bits if b)
    lines = [f"After a {need} session, {'tomorrow' if d.get('when') == 'tomorrow' else 'today'}, near {d.get('city') or args.get('city')}:"]
    for k, title in (("places", "A place"), ("food", "A table"), ("read", "A page")):
        if d.get(k):
            lines.append(f"{title}: " + "; ".join(row(x) for x in d[k][:3]))
    if len(lines) == 1:
        lines.append("Qloo found nothing for this yet (check the city's spelling, or the server is in recorded-answers mode).")
    lines.append("Never suggested: bars, clubs, or anything built around drinking.")
    return {"text": "\n".join(lines), "data": {k: d.get(k) for k in ("goal", "when", "city", "places", "food", "read", "sent")}}


def explain_evidence(args: dict[str, Any], deps: dict[str, Any]) -> dict[str, Any]:
    need = _need(args.get("need"))
    reg = deps["protocols"]()
    rows = [p for p in reg.get("protocols", []) if p.get("goal") == need or (need == "calm" and p.get("goal") == "autism_calm")]
    lines, data = [], []
    for p in rows:
        ev = [{"grade": e.get("grade"), "claim": e.get("claim"), "note": e.get("note"), "source": e.get("source"), "url": e.get("url")} for e in (p.get("evidence") or [])]
        data.append({"protocol": p.get("name"), "summary": p.get("summary"), "evidence": ev})
        lines.append(f"{p.get('name')}: {p.get('summary')}")
        lines += [f"  grade {e['grade']}: {e['claim']} ({e['source']})" for e in ev]
    if not lines:
        lines = ["No protocol for this need."]
    lines.append("Grades: A = meta-analysis or several RCTs, B = one adequately powered RCT, C = pilot or inconsistent, D = mechanism only.")
    return {"text": "\n".join(lines), "data": data}


def reach_vs_chatbot(args: dict[str, Any], deps: dict[str, Any]) -> dict[str, Any]:
    b = deps["bench"]()
    if not b.get("ran"):
        return {"text": "The comparison has not been run on this server yet (scripts/bench.py needs a live Qloo key).", "data": b}
    S = b.get("systems") or {}
    pct = lambda x: "-" if x is None else f"{round(x * 100)}%"
    names = {"reach": "Reach", "llm": f"Chatbot ({b.get('llm')})", "generic": "Generic playlist"}
    lines = [f"Run {b.get('run_at')} on {b.get('people')} people."]
    for k in ("reach", "llm", "generic"):
        if k in S:
            v = S[k]
            lines.append(f"{names[k]}: from their culture {pct(v.get('culture'))}, songs that exist {pct(v.get('exists'))}, calm picks for sleep {pct(v.get('calm_safe'))}, personal {pct(v.get('personal'))}.")
    return {"text": "\n".join(lines), "data": b}


HANDLERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "compose_session": compose_session, "after_the_music": after_the_music, "explain_evidence": explain_evidence, "reach_vs_chatbot": reach_vs_chatbot}


def _ok(rid: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid: Any, code: int, msg: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}


def handle(msg: Any, deps: dict[str, Any]) -> dict[str, Any] | None:
    """One JSON-RPC message -> its response (None for a notification)."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return _err(msg.get("id") if isinstance(msg, dict) else None, -32600, "invalid request")
    rid, method, params = msg.get("id"), msg["method"], msg.get("params") or {}
    if "id" not in msg:                                  # a notification (notifications/initialized, cancelled ...)
        return None
    if method == "initialize":
        want = params.get("protocolVersion")
        return _ok(rid, {"protocolVersion": want if want in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                         "capabilities": {"tools": {"listChanged": False}},
                         "serverInfo": {"name": "reach", "title": "Reach: music medicine with taste", "version": "1.0"},
                         "instructions": "Use compose_session when someone wants music to sleep, calm down, focus, lift their mood or remember; pass what they love. "
                                         "Use after_the_music for a gentle next step near them, explain_evidence when they ask whether it works."})
    if method == "ping":
        return _ok(rid, {})
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name"); args = params.get("arguments") or {}
        fn = HANDLERS.get(name)
        if not fn:
            return _err(rid, -32602, f"unknown tool: {name}")
        if not isinstance(args, dict) or len(json.dumps(args)) > 4000:
            return _err(rid, -32602, "arguments must be a small object")
        try:
            out = fn(args, deps)
            return _ok(rid, {"content": [{"type": "text", "text": out["text"]}], "structuredContent": out["data"] if isinstance(out["data"], dict) else {"items": out["data"]}, "isError": False})
        except ToolError as e:
            return _ok(rid, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        except Exception as e:  # noqa: BLE001  a tool failing is reported to the assistant, never a crash
            return _ok(rid, {"content": [{"type": "text", "text": f"Reach could not finish this: {type(e).__name__}"}], "isError": True})
    return _err(rid, -32601, f"method not found: {method}")
