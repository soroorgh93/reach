"""The Composer: resolves a protocol template into a concrete session the browser can play.

Inputs: the protocol, the Listener's report (arousal, valence), the Taste agent's report
(palette, carrier, biases) and the profile (age, sensory flags). Output: a timeline of
segments with pulse Hz, tempo, musical key/mode, instrument palette, pulse depth, gain cap,
breathing cue and the carrier playlist. Deterministic; every number can be traced back.
"""
from __future__ import annotations

import hashlib
from typing import Any

KEYS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
MODES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10], "dorian": [0, 2, 3, 5, 7, 9, 10],
         "lydian": [0, 2, 4, 6, 7, 9, 11], "pentatonic": [0, 2, 4, 7, 9], "mixolydian": [0, 2, 4, 5, 7, 9, 10]}


def _key_for(profile: dict[str, Any], valence: float) -> str:
    # a stable key per person, so sessions feel like "theirs"; shifted down a little when valence is low
    h = int(hashlib.sha256(str(profile.get("id", "x")).encode()).hexdigest(), 16)
    base = h % 12
    if valence < -0.3:
        base = (base - 2) % 12
    return KEYS[base]


def _mode_for(seg: dict[str, Any], valence: float, goal: str) -> str:
    if seg.get("mode_music"):
        return seg["mode_music"]
    if goal == "energy":
        return "mixolydian"
    if goal == "sleep":
        return "pentatonic" if valence >= 0 else "dorian"
    if goal == "focus":
        return "lydian" if valence > 0.2 else "mixolydian"
    if goal == "autism_calm":
        return "pentatonic"
    if valence < -0.3:
        return "minor"
    if valence < 0.2:
        return "dorian"
    return "major"


def compose(protocol: dict[str, Any], listener: dict[str, Any], taste: dict[str, Any], profile: dict[str, Any],
            safety: dict[str, Any], intents: dict[str, Any] | None = None) -> dict[str, Any]:
    intents = intents or {}
    flags = set(intents.get("flags", []))
    mood = listener["mood"]
    goal = listener["goal"]
    age = profile.get("age") or 30
    child = age < 13
    autism = goal == "autism_calm" or "autism" in (profile.get("targets") or [])
    arousal_bpm = listener["arousal_bpm"]
    tempo_bias = taste.get("tempo_bias", 0.0)
    key = _key_for(profile, mood["valence"])
    palette = taste.get("palette", "piano")
    if goal in ("sleep", "calm", "autism_calm"):
        palette = {"guitar": "plucked", "synth": "pad"}.get(palette, palette)   # soften for down-regulating sessions
    if goal == "energy":
        palette = {"plucked": "synth", "piano": "synth", "strings": "synth", "pad": "synth", "bells": "synth", "nylon": "guitar", "epiano": "synth"}.get(palette, palette)
    depth = float(protocol.get("pulse_depth", 0.3))
    depth = min(depth, safety["pulse_depth_autism_max"] if autism else safety["pulse_depth_max"])
    gain_db = safety["child_max_output_dbfs"] if (child or autism) else safety["max_output_dbfs"]
    segments: list[dict[str, Any]] = []
    t = 0.0
    n = len(protocol["segments"])
    for i, s in enumerate(protocol["segments"]):
        bpm = s["bpm"]
        if bpm == "match":
            bpm = arousal_bpm
        elif bpm == "descend":
            bpm = round((arousal_bpm + 60) / 2)
        bpm = int(round(bpm * (1 + 0.12 * tempo_bias)))
        if "slower" in flags:
            bpm = int(round(bpm * 0.9))
        if "faster" in flags:
            bpm = int(round(bpm * 1.1))
        if autism:
            bpm = min(bpm, 84)
        hz_from, hz_to = float(s["hz_from"]), float(s["hz_to"])
        if goal == "sleep" and i == 0 and mood["arousal"] > 0.7:
            hz_from = 12.0  # meet a wired person a little higher, then descend
        minutes = float(s["minutes"])
        if "longer" in flags:
            minutes *= 1.5
        if "shorter" in flags:
            minutes *= 0.6
        if goal == "sleep" and mood["arousal"] > 0.7 and s["name"] == "drift":
            minutes += 3
        segments.append({
            "name": s["name"], "start_s": round(t * 60), "minutes": minutes, "hz_from": hz_from, "hz_to": hz_to,
            "jitter": float(s.get("jitter", 0.0)), "bpm": bpm, "texture": s["texture"],
            "brightness": min(1.0, max(0.05, float(s["brightness"]) + (0.12 if "brighter" in flags else 0) - (0.12 if "darker" in flags else 0) - (0.06 if "softer" in flags else 0))),
            "mode": _mode_for(s, mood["valence"], goal), "repeat": bool(s.get("repeat", False)), "fade_out": bool(s.get("fade_out", False)),
        })
        t += minutes
    if "softer" in flags:
        gain_db -= 4
        depth = max(0.0, depth - 0.1)
    breathing = protocol.get("breathing")
    carrier = list(taste.get("favourites_first", [])) + list(taste.get("carrier", []))
    return {
        "protocol_id": protocol["id"], "protocol_name": protocol["name"], "goal": goal, "duration_min": round(t),
        "entrainment": protocol["mode"], "pulse_depth": round(depth, 2), "gain_dbfs": gain_db,
        "key": key, "palette": palette, "palette_source": taste.get("palette", "piano"), "mood_bias": taste.get("mood_bias", 0.0),
        "segments": segments, "breathing": breathing, "carrier": carrier[:12], "own": [c["name"] for c in carrier if c.get("own")],  "pinned": list(taste.get("pinned", [])),
        "lens": taste.get("lens"), "set_aside": taste.get("set_aside", []),
        "start": {"arousal": mood["arousal"], "valence": mood["valence"], "bpm": arousal_bpm},
        "vocals": False if "no_vocals" in flags else (True if "vocals" in flags else bool(protocol.get("carrier", {}).get("vocals", True))),
        "applied_intents": sorted(flags),
        "caps": {"child": child, "autism": autism, "volume_note": safety["who_safe_listening"]},
    }


def adapt(session: dict[str, Any], mood: dict[str, float], elapsed_s: float, goal: str) -> dict[str, Any]:
    """Given a fresh mood reading mid-session, return adjustments for the running segment (ISO principle).
    Returns {bpm_delta, hz_delta, depth_delta, brightness_delta, reason}."""
    a, v = float(mood.get("arousal", 0.45)), float(mood.get("valence", 0.0))
    seg = None
    for s in session["segments"]:
        if s["start_s"] <= elapsed_s:
            seg = s
    if seg is None:
        seg = session["segments"][0]
    out = {"segment": seg["name"], "bpm_delta": 0, "hz_delta": 0.0, "depth_delta": 0.0, "brightness_delta": 0.0, "reason": "on course"}
    target_arousal = {"sleep": 0.15, "calm": 0.3, "autism_calm": 0.3, "mood": 0.45, "focus": 0.6, "memory": 0.45}.get(goal, 0.4)
    gap = a - target_arousal
    if goal in ("sleep", "calm", "autism_calm") and gap > 0.2:
        out.update({"bpm_delta": -4, "hz_delta": -0.5, "brightness_delta": -0.08, "reason": "arousal still high; slowing and darkening (ISO step down)"})
    elif goal in ("sleep", "calm", "autism_calm") and gap < -0.2:
        out.update({"bpm_delta": 0, "depth_delta": -0.05, "reason": "settled; pulse softened"})
    elif goal == "focus" and gap < -0.2:
        out.update({"bpm_delta": +4, "hz_delta": +1.0, "brightness_delta": +0.08, "reason": "energy low; lifting tempo and pulse"})
    elif goal == "focus" and gap > 0.25:
        out.update({"bpm_delta": -3, "hz_delta": -1.0, "reason": "over-aroused for focus; easing pulse"})
    elif goal == "mood" and v < -0.4:
        out.update({"brightness_delta": -0.05, "bpm_delta": -2, "reason": "staying with the person a little longer before brightening"})
    if goal == "autism_calm":
        out["depth_delta"] = min(out["depth_delta"], 0.0)   # never deepen the pulse for a child in overload
    return out
