"""The Reach council.

Six roles, run in a fixed order so the trace is reproducible and every step is sealed:
  Listener   what the person said, showed and sounded like -> goal, arousal, valence
  Taste      Qloo: favourites -> carrier artists, texture palette, cultural lens (required)
  Clinician  candidate protocols ranked on evidence x fit x taste under three stances
             (Bayes, minimax, least-favourable prior), with safety rules
  Composer   the protocol resolved into a playable session (Hz, bpm, key, palette, depth)
  Guardian   adversarial checks with ids; can veto or amend
  Gate       is recommending justified at all (p*benefit >= (1-p)*cost)
Every step is appended to a hash-chained ledger. No free text from a language model
decides anything; an optional narrator may phrase the result, and is number-checked.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Iterator

from . import decision
from .composer import compose, adapt as compose_adapt
from .ledger import Ledger
from .mood import listen, parse_intents
from .narrator import narrate, agent_replies
from .dialogue import session_reply
from .rag import retrieve
from .qloo import QlooClient
from .taste import TasteAgent
from .group import GroupAgent, parse_members

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_PROTO: dict[str, Any] | None = None

ADJACENT = {"focus": ["focus_beta", "calm_iso"], "sleep": ["sleep_descent", "calm_iso"], "calm": ["calm_iso", "mood_lift"],
            "autism_calm": ["sensory_safe", "calm_iso"], "mood": ["mood_lift", "energize"], "memory": ["gamma_support", "mood_lift"],
            "energy": ["energize", "mood_lift"], "visual": ["visual_breath"]}
GRADE_SCORE = {"A": 0.95, "B": 0.75, "C": 0.45, "D": 0.2}
INJECTION = [r"ignore (all|previous|prior) instructions", r"\bsystem prompt\b", r"<\s*script", r"\bapi[_ -]?key\b", r"\bdisregard\b"]


def journey(a: dict[str, Any], b: dict[str, Any], pa: dict[str, Any], pb: dict[str, Any]) -> dict[str, Any]:
    """One session out of two: the opening half of the first (where the person is), then all of the second
    (where they want to go). Times, carrier and names are joined; the safety caps are the stricter of the two."""
    segs_a = a.get("segments") or []
    keep, total = [], 0.0
    for sg in segs_a:
        keep.append(dict(sg)); total += float(sg.get("minutes") or 0)
        if total >= float(a.get("duration_min") or 0) / 2:
            break
    out = dict(b)
    segs, t = [], 0.0
    for sg in keep + [dict(x) for x in (b.get("segments") or [])]:
        sg["start_s"] = round(t * 60); t += float(sg.get("minutes") or 0); segs.append(sg)
    out["segments"] = segs; out["duration_min"] = round(t)
    seen, carrier = set(), []
    for c in (a.get("carrier") or [])[:4] + (b.get("carrier") or []):
        if c.get("name") not in seen:
            seen.add(c.get("name")); carrier.append(c)
    out["carrier"] = carrier[:10]
    out["gain_dbfs"] = min(a.get("gain_dbfs", -14), b.get("gain_dbfs", -14)); out["pulse_depth"] = min(a.get("pulse_depth", 0.3), b.get("pulse_depth", 0.3))
    out["protocol_name"] = f"{pa['name']} → {pb['name']}"
    out["journey"] = {"from": a.get("goal"), "to": b.get("goal"), "protocols": [pa["id"], pb["id"]], "switch_s": segs[len(keep)]["start_s"] if len(segs) > len(keep) else None,
                      "evidence": [{k: e.get(k) for k in ("grade", "claim", "source")} for e in (pb.get("evidence") or [])[:2]]}
    return out


def protocols() -> dict[str, Any]:
    global _PROTO
    if _PROTO is None:
        _PROTO = json.loads((DATA_DIR / "protocols.json").read_text(encoding="utf-8"))
    return _PROTO


def protocol(pid: str) -> dict[str, Any]:
    return next(p for p in protocols()["protocols"] if p["id"] == pid)


def guard(profile: dict[str, Any], request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    notes: list[str] = []
    prof = json.loads(json.dumps(profile))
    req = json.loads(json.dumps(request))
    for obj, fields in ((prof, ("name", "city", "story")), (req, ("text",))):
        for f in fields:
            v = obj.get(f)
            if isinstance(v, str):
                for pat in INJECTION:
                    if re.search(pat, v, flags=re.I):
                        obj[f] = re.sub(pat, "[removed]", v, flags=re.I); notes.append(f"instruction-like text removed from {f}")
                obj[f] = obj[f][:400]
    prof["favorites"] = [f for f in prof.get("favorites", [])[:12] if not f.get("entity_id") or re.fullmatch(r"[0-9A-Fa-f-]{36}", f["entity_id"])]
    for k in ("face", "voice"):
        if k in req and not isinstance(req[k], dict):
            req.pop(k); notes.append(f"{k} payload ignored (not an object)")
    if "face" in req:
        req["face"] = {k: float(v) for k, v in req["face"].items() if k in ("neutral", "happy", "sad", "angry", "fearful", "disgusted", "surprised")}
    return prof, req, notes


def clinician_rules(proto: dict[str, Any], profile: dict[str, Any], listener: dict[str, Any]) -> list[dict[str, str]]:
    caps = profile.get("capacities", {})
    flags = {f.lower() for f in profile.get("flags", [])}
    age = profile.get("age") or 30
    out = []
    h = str(caps.get("hearing", "full")).lower()
    if proto.get("mode") == "visual":
        out.append({"rule": "R-SENS-AUD", "verdict": "PASS", "reason": "visual and haptic delivery; hearing not required"})
    elif h in ("none", "deaf"):
        out.append({"rule": "R-SENS-AUD", "verdict": "REFUSE", "reason": "auditory session; the person does not hear. Vibrotactile delivery is the alternative."})
    elif h in ("partial", "aided", "hard_of_hearing"):
        out.append({"rule": "R-SENS-AUD", "verdict": "REVIEW", "reason": "partial hearing: binaural beats need both ears; isochronic pulse used instead"})
    else:
        out.append({"rule": "R-SENS-AUD", "verdict": "PASS", "reason": "hearing sufficient"})
    if age < 5 and proto["pulse_depth"] > 0:
        out.append({"rule": "R-AGE", "verdict": "REVIEW", "reason": f"age {age}: entrainment pulse disabled, music only"})
    elif age < 13:
        out.append({"rule": "R-AGE", "verdict": "PASS", "reason": f"age {age}: child volume and pulse caps apply"})
    for c in proto.get("contra", []):
        if c in flags:
            out.append({"rule": "R-SAFETY", "verdict": "REFUSE", "reason": f"contraindicated: {c.replace('_', ' ')}"})
    if "tinnitus" in flags and proto["mode"] == "binaural":
        out.append({"rule": "R-SAFETY", "verdict": "REVIEW", "reason": "tinnitus: carrier kept low and pulse shallow"})
    if "bedtime" in proto.get("not_when", []) and (listener["hour"] >= 23 or listener["hour"] < 5):
        out.append({"rule": "R-TIMING", "verdict": "REVIEW", "reason": "focus session late at night; sleep may be the better goal"})
    if not profile.get("consent", {}).get("taste", True):
        out.append({"rule": "R-CONSENT", "verdict": "REFUSE", "reason": "no consent to use favourites; Reach cannot personalise"})
    return out


def rules_score(rules: list[dict[str, str]]) -> float:
    s = 1.0
    for r in rules:
        s *= {"PASS": 1.0, "REVIEW": 0.6, "REFUSE": 0.0}[r["verdict"]]
    return s


class ReachCouncil:
    def __init__(self, client: QlooClient | None = None):
        self.client = client or QlooClient()

    def run(self, profile_in: dict[str, Any], request_in: dict[str, Any], stream_delay: float = 0.0) -> Iterator[dict[str, Any]]:
        t0 = time.monotonic()
        calls_start = len(self.client.calls)
        ledger = Ledger()

        def ev(kind: str, **payload: Any) -> dict[str, Any]:
            entry = ledger.append(kind, payload)
            if stream_delay:
                time.sleep(stream_delay)
            return {"kind": kind, "i": entry["i"], "hash": entry["hash"][:12], "t": round(time.monotonic() - t0, 3), **payload}

        profile, request, gnotes = guard(profile_in, request_in)
        yield ev("guard", notes=gnotes, favourites=len(profile.get("favorites", [])),
                 signals=[k for k in ("text", "face", "voice") if request.get(k)], on_device=["face frames", "audio"], leaves_browser=["7 expression probabilities", "3 prosody numbers", "text"])

        # ---- Listener (mood, goal, and what the person asked the council to change)
        # a tweak ("slower", "no vocals") keeps the goal of the session it changes
        prev = request.get("prev") if isinstance(request.get("prev"), dict) else {}
        from .mood import detect_goal as _dg
        if prev.get("goal") and not request.get("goal") and not _dg(request.get("text", ""))[0] and not request.get("face") and not request.get("override"):
            request["goal"] = prev["goal"]
        L = listen(request, profile)
        intents = parse_intents(request.get("text", ""))
        learned = {"liked": [], "disliked": []}
        if not self.client.offline:
            for name in intents["like"][:3]:
                r = self._resolve_artist(name)
                if r:
                    learned["liked"].append(r)
            for name in intents["dislike"][:3]:
                r = self._resolve_artist(name)
                if r:
                    learned["disliked"].append(r)
        L["intents"] = intents["flags"]; L["learned"] = learned
        yield ev("listener", goal=L["goal"], goal_words=L["goal_words"], mood=L["mood"], signals=L["signals"], arousal_bpm=L["arousal_bpm"], notes=L["notes"], hour=L["hour"], observations=L["observations"], inferred=L["inferred"],
                 intents=intents["flags"], learned={k: [x["name"] for x in v] for k, v in learned.items()})

        # ---- Candidates
        cand_ids = ADJACENT.get(L["goal"], ["calm_iso"])
        hearing = str(profile.get("capacities", {}).get("hearing", "full")).lower()
        if hearing in ("none", "deaf") or L["goal"] == "visual":
            cand_ids = ["visual_breath"]            # no auditory candidate for someone who cannot hear: route, do not refuse
            L["routed_visual"] = True
        cands = [protocol(c) for c in cand_ids]
        yield ev("plan", candidates=[c["id"] for c in cands], steps=["taste (Qloo) per candidate", "rules", "evidence", "stance adjudication", "compose", "guardian", "gate", "seal"])

        # ---- Group? members from the UI or from the words ("I'm with four friends, one likes Indian music")
        members = [m for m in (request.get("group") or []) if isinstance(m, dict) and m.get("name")][:8]
        parsed, stated = parse_members(request.get("text", ""))
        if parsed and not members:
            members = parsed
        group_agent = GroupAgent(self.client) if members else None
        if members:
            yield ev("group", members=[{"name": m["name"], "genres": m.get("genres", []), "artist": m.get("artist"), "needs": m.get("needs", {}), "favourites": len(m.get("favorites") or [])} for m in members], stated_count=stated)

        # ---- Taste (Qloo) per candidate
        taste_agent = TasteAgent(self.client)
        tastes: dict[str, dict[str, Any]] = {}
        memory = dict(request.get("memory")) if isinstance(request.get("memory"), dict) else {}
        memory["liked"] = list(memory.get("liked", [])) + [x["entity_id"] for x in learned["liked"]]
        memory["disliked"] = list(memory.get("disliked", [])) + [x["entity_id"] for x in learned["disliked"]]
        if "no_vocals" in intents["flags"]:
            memory["instrumental"] = True
        memory["pin"] = [str(x)[:60] for x in (request.get("pin") or []) if str(x).strip()][:4]
        for c in cands:
            T = group_agent.read(profile, members, c, memory) if group_agent else taste_agent.read(profile, c, memory)
            tastes[c["id"]] = T
            if group_agent and T.get("ok"):
                yield ev("fairness", protocol=c["id"], members=T["members"], bayes=T["adjudication"]["bayes"], minimax=T["adjudication"]["minimax"], lfp=T["adjudication"]["lfp"],
                         weights=T["adjudication"]["weights"], top=[(x["name"], x["per_member"]) for x in T["carrier"][:4]], instrumental=T["instrumental"], per_member=T["per_member"])
            yield ev("taste", protocol=c["id"], ok=T["ok"], carrier=[x["name"] for x in T.get("carrier", [])[:5]], palette=T.get("palette"),
                     fit_rate=T.get("fit_rate"), strength=T.get("strength"), data_weight=T.get("data_weight"), texture=T.get("texture_tags", [])[:6],
                     source=T.get("source"), sent=T.get("sent", []), reason=T.get("reason"), memory=T.get("memory_used"))
        if not any(T["ok"] for T in tastes.values()):
            yield ev("refuse", by="Taste", reason="Qloo returned no usable taste data; Reach does not compose generic sessions", ledger=ledger.verify()["ok"])
            yield {"kind": "result", "result": {"error": "qloo_required", "detail": "Qloo returned no usable taste data for this profile.",
                                               "replies": [{"agent": "taste", "text": "I could not read any taste for this profile from Qloo, so there is nothing to build a carrier from. Add two or three things you love and I will try again."}],
                                               "ledger": ledger.entries, "qloo_calls": self.client.calls[calls_start:]}}
            return

        # ---- Clinician: rules + evidence + stance adjudication
        rows = []
        rule_map: dict[str, list[dict[str, str]]] = {}
        for c in cands:
            rules = clinician_rules(c, profile, L)
            rule_map[c["id"]] = rules
            grades = [e["grade"] for e in c["evidence"]]
            ev_score = max(GRADE_SCORE[g] for g in grades) * 0.7 + min(GRADE_SCORE[g] for g in grades) * 0.3
            fit = 1.0 if c["goal"] == L["goal"] else 0.55
            T = tastes[c["id"]]
            taste_score = (0.5 + 0.5 * T.get("fit_rate", 0)) * (0.6 + 0.4 * T.get("data_weight", 0)) if T["ok"] else 0.0
            rows.append({"id": c["id"], "evidence": round(ev_score, 3), "reachability": round(fit * rules_score(rules), 3), "engagement": round(taste_score, 3)})
            yield ev("rule", protocol=c["id"], rules=rules, evidence=round(ev_score, 3), fit=fit, taste=round(taste_score, 3))
        adj = decision.adjudicate(rows)
        yield ev("adjudicate", bayes=adj["bayes"], minimax=adj["minimax"], lfp=adj["lfp"], weights=adj["weights"], ranking=[(x["id"], x["final"]) for x in adj["ranking"]])
        chosen_id = next((x["id"] for x in adj["ranking"] if rules_score(rule_map[x["id"]]) > 0 and tastes[x["id"]]["ok"]), None)
        if chosen_id is None:
            refused = [(cid, [r for r in rs if r["verdict"] == "REFUSE"]) for cid, rs in rule_map.items()]
            yield ev("refuse", by="Clinician", reason="every candidate protocol is refused by a safety rule", rules=refused)
            alt = "vibrotactile_music" if any(r["rule"] == "R-SENS-AUD" and r["verdict"] == "REFUSE" for rs in rule_map.values() for r in rs) else None
            yield {"kind": "result", "result": {"error": "refused", "detail": "No auditory protocol can reach this person.", "alternative": alt,
                                               "replies": [{"agent": "clinician", "text": "Every candidate protocol is refused by a safety rule: " + "; ".join(f"{cid}: " + ", ".join(r["reason"] for r in rs) for cid, rs in refused if rs) + (". Vibrotactile music, felt through the body, is the honest alternative." if alt else ".")}],
                                               "rules": refused, "listener": L, "ledger": ledger.entries, "qloo_calls": self.client.calls[calls_start:]}}
            return
        chosen = protocol(chosen_id)
        T = tastes[chosen_id]

        # ---- Composer
        if T.get("instrumental"):
            intents = dict(intents); intents["flags"] = sorted(set(intents.get("flags", [])) | {"no_vocals"})
        session = compose(chosen, L, T, profile, protocols()["safety"], intents)
        session["only"] = bool(request.get("only")) and bool(session.get("pinned"))
        # ---- a journey: two needs in one session (energy, then focus; calm, then sleep). The ISO principle:
        # meet the person where they are, then lead. The first protocol's opening, then the second protocol.
        then = request.get("then_goal")
        if then in ADJACENT and then != L["goal"] and hearing not in ("none", "deaf") and not L.get("routed_visual"):
            pid2 = next((x for x in ADJACENT[then] if x != chosen_id), None)
            if pid2:
                p2 = protocol(pid2)
                # already read for this protocol? reuse it (no second Qloo call); a group is read as a group
                T2 = tastes.get(pid2) or (group_agent.read(profile, members, p2, memory) if group_agent else taste_agent.read(profile, p2, memory))
                if T2.get("ok"):
                    s2 = compose(p2, dict(L, goal=then), T2, profile, protocols()["safety"], intents)
                    session = journey(session, s2, chosen, p2)
                    yield ev("journey", start=chosen_id, then=pid2, minutes=session["duration_min"], segments=[(x["name"], x["hz_from"], x["hz_to"], x["bpm"]) for x in session["segments"]])
        # be careful with what a goal needs: lively artists (techno, dance, loud pop) do not help someone sleep or calm
        # down. Then the session plays calm instrumental music instead, says so, and "my artists" brings them back.
        tags = " ".join(T.get("texture_tags") or []).lower()
        lively = any(w in tags for w in ("techno", "edm", "house", "dance", "trance", "dubstep", "drum and bass", "metal", "punk", "hardcore",
                                          "trap", "drill", "rap", "hip hop", "hip-hop", "reggaeton", "electro", "club", "party")) \
            or float(T.get("tempo_bias") or 0) > 0.12 or ("pop" in tags and float(T.get("tempo_bias") or 0) > 0.04)
        if L["goal"] in ("sleep", "calm", "autism_calm") and lively and not session.get("pinned") and "vocals" not in (intents.get("flags") or []):
            session["calm_carrier"] = {"goal": L["goal"], "why": "lively"}
            session["vocals"] = False
        if group_agent:
            session["group"] = {"members": T.get("members", []), "weights": T["adjudication"]["weights"], "per_member": T.get("per_member", {})}
        if any(r["rule"] == "R-AGE" and r["verdict"] == "REVIEW" for r in rule_map[chosen_id]):
            session["pulse_depth"] = 0.0
        if any(r["rule"] == "R-SENS-AUD" and r["verdict"] == "REVIEW" for r in rule_map[chosen_id]):
            session["entrainment"] = "isochronic"
        yield ev("compose", protocol=chosen_id, key=session["key"], palette=session["palette"], entrainment=session["entrainment"], pulse_depth=session["pulse_depth"],
                 gain_dbfs=session["gain_dbfs"], duration_min=session["duration_min"],
                 segments=[(s["name"], s["hz_from"], s["hz_to"], s["bpm"], s["mode"]) for s in session["segments"]], carrier=[c["name"] for c in session["carrier"][:5]])

        # ---- Guardian
        checks: list[dict[str, Any]] = []
        grade_best = max(e["grade"] for e in chosen["evidence"])  # 'A' < 'B' lexically, so min is best; handle below
        best = min(e["grade"] for e in chosen["evidence"])
        if best in ("C", "D") and rows[[r["id"] for r in rows].index(chosen_id)]["engagement"] > 0.7:
            checks.append({"check": "G-TASTE-OVER-EVIDENCE", "action": "flag", "detail": f"best evidence for {chosen['name']} is grade {best}; it is shown as 'engaging, weakly proven'"})
            session["flag"] = "engaging_weakly_proven"
        if session["caps"]["autism"]:
            ok = session["pulse_depth"] <= 0.25 and session["gain_dbfs"] <= -20 and all(s["bpm"] <= 84 for s in session["segments"])
            checks.append({"check": "G-SENSORY-ENVELOPE", "action": "pass" if ok else "amend", "detail": "pulse depth <= 0.25, output <= -20 dBFS, tempo <= 84 bpm" + ("" if ok else " (amended)")})
            if not ok:
                session["pulse_depth"] = min(session["pulse_depth"], 0.25); session["gain_dbfs"] = min(session["gain_dbfs"], -20)
                for s in session["segments"]:
                    s["bpm"] = min(s["bpm"], 84)
        if L["notes"]:
            checks.append({"check": "G-REQUEST-VS-STATE", "action": "note", "detail": "; ".join(L["notes"])})
        used = [k for k in ("face", "voice") if request.get(k)]
        consent = request.get("consent", {})
        if used and not all(consent.get(k) for k in used):
            checks.append({"check": "G-CONSENT", "action": "amend", "detail": f"{', '.join(used)} data arrived without a consent flag; discarded from the mood estimate"})
            L2 = listen({k: v for k, v in request.items() if k not in used}, profile)
            L["mood"] = L2["mood"]; L["signals"] = L2["signals"]
        if adj["bayes"] != adj["minimax"]:
            checks.append({"check": "G-STANCE-DISAGREEMENT", "action": "note", "detail": f"average-case pick {adj['bayes']} differs from worst-case pick {adj['minimax']}; least-favourable prior chose {adj['lfp']}"})
        if T.get("fit_rate", 1) < 0.25:
            checks.append({"check": "G-CARRIER-FIT", "action": "note", "detail": "few artists in the person's taste fit this protocol's texture; carrier falls back to general affinities"})
        checks.append({"check": "G-QLOO-CONTRIBUTION", "action": "pass", "detail": f"carrier and palette come from Qloo ({T.get('source')}); without it Reach would refuse"})
        yield ev("guardian", checks=checks)

        # ---- Gate
        rank_val = next(x["final"] for x in adj["ranking"] if x["id"] == chosen_id)
        p = decision.belief(rank_val, rows[[r["id"] for r in rows].index(chosen_id)]["evidence"], support=0.5 if T["ok"] else 0.0)
        gate = decision.policy_gate(p, "auditory", best)
        yield ev("gate", protocol=chosen_id, **gate)

        seal = ledger.verify()
        yield ev("seal", ok=seal["ok"], length=seal["length"] + 1, head=ledger.head()[:16])

        facts = {"name": profile.get("name"), "goal": L["goal"], "protocol": chosen["name"], "palette": session["palette"], "key": session["key"],
                 "bpm0": session["segments"][0]["bpm"], "hz0": session["segments"][0]["hz_from"], "hz_end": session["segments"][-1]["hz_to"],
                 "duration": session["duration_min"], "carrier": [c["name"] for c in session["carrier"][:3]],
                 "favourites": [f["name"] for f in profile.get("favorites", [])[:3]], "arousal": L["mood"]["arousal"], "valence": L["mood"]["valence"],
                 "grade": best, "evidence_source": chosen["evidence"][0]["source"], "texture": T.get("texture_tags", [])[:4], "observations": L["observations"]}
        story = narrate(facts, lang=request.get("lang", "en"))
        text_q = request.get("text", "")
        passages = retrieve(text_q, 2) if (("?" in text_q) or any(w in text_q.lower() for w in ("why", "what", "how", "is it safe", "evidence", "por qué", "چرا", "为什么"))) else []
        pre = {"request_text": text_q, "passages": passages, "group": T if group_agent else None, "listener": L, "candidates": rows, "adjudication": adj, "rules": rule_map[chosen_id], "protocol": chosen, "taste": T, "session": session, "guardian": checks, "gate": gate, "profile": profile}
        replies = agent_replies(pre, lang=request.get("lang", "en"))
        result = {
            "profile": {k: profile.get(k) for k in ("id", "name", "age", "city", "language", "targets", "favorites")},
            "listener": L, "candidates": rows, "adjudication": {k: adj[k] for k in ("bayes", "minimax", "lfp", "weights")},
            "rules": rule_map[chosen_id], "protocol": {k: chosen[k] for k in ("id", "name", "goal", "summary", "evidence", "mode", "duration_min")},
            "taste": {k: T.get(k) for k in ("carrier", "palette", "palette_votes", "texture_tags", "mood_bias", "tempo_bias", "fit_rate", "strength", "data_weight", "demographics", "source", "sent")},
            "session": session, "guardian": checks, "gate": gate, "story": story, "replies": replies, "learned": learned, "passages": passages,
            "ledger": ledger.entries, "ledger_head": ledger.head(), "qloo_calls": self.client.calls[calls_start:], "elapsed_ms": round((time.monotonic() - t0) * 1000),
        }
        result["reply"] = session_reply(result, request)
        yield {"kind": "result", "result": result}

    def _resolve_artist(self, name: str) -> dict[str, Any] | None:
        try:
            r = self.client.resolve(name, "artist")
        except Exception:
            return None
        return {"name": r["name"], "entity_id": r["entity_id"]} if r else None

    def compose_once(self, profile: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        last: dict[str, Any] = {}
        for e in self.run(profile, request):
            last = e
        return last["result"]

    @staticmethod
    def adapt(session: dict[str, Any], mood: dict[str, float], elapsed_s: float) -> dict[str, Any]:
        return compose_adapt(session, mood, elapsed_s, session.get("goal", "calm"))
