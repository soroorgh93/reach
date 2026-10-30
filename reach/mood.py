"""The Listener: turns what the person says, shows and sounds like into an arousal/valence
estimate and a goal, with a confidence the rest of the council can weigh.

Everything here is an estimate the person can correct. Facial expression and voice prosody
are weak, culturally variable signals (Barrett et al. 2019), so they never override an
explicit request; they decide the starting point of the session (the ISO principle) and
the direction of adaptation. Faces and audio never leave the browser: the client sends
seven expression probabilities and three prosody numbers, nothing else.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

GOALS = ("focus", "sleep", "calm", "autism_calm", "mood", "memory", "energy", "visual")

# Keyword lexicon, deliberately small and multilingual (en, es, fa, zh). Order matters: first hit wins per goal.
LEXICON: dict[str, list[str]] = {
    "sleep": ["sleep", "insomnia", "can't sleep", "cannot sleep", "bed", "tired", "exhausted", "dormir", "sueño", "insomnio", "خواب", "بی‌خوابی", "بیخوابی", "睡", "失眠", "入睡"],
    "focus": ["focus", "concentrat", "study", "work", "deadline", "exam", "coding", "attention", "adhd", "concentr", "estudiar", "trabajo", "تمرکز", "مطالعه", "کار", "专注", "集中", "学习", "工作"],
    "autism_calm": ["autis", "meltdown", "overload", "sensory", "my son", "my daughter", "my child", "my kid", "stimming", "autista", "mi hijo", "mi hija", "اوتیسم", "فرزندم", "پسرم", "دخترم", "自闭", "孩子", "崩溃"],
    "calm": ["anxi", "stress", "panic", "nervous", "overwhelm", "calm", "relax", "tense", "worried", "ansie", "estrés", "estres", "relaj", "calma", "اضطراب", "استرس", "آرام", "نگران", "焦虑", "压力", "紧张", "放松", "平静"],
    "mood": ["sad", "grief", "lonely", "depress", "down", "cry", "miss", "lost", "heartbroken", "hopeless", "triste", "duelo", "solo", "sola", "غم", "غمگین", "تنها", "افسرد", "悲伤", "难过", "孤独", "抑郁", "失去"],
    "energy": ["boost", "energy", "energi", "pump", "wake me", "wake up", "motivat", "workout", "gym", "dance", "party", "hype", "energía", "energia", "ánimo arriba", "bailar", "انرژی", "انرژي", "شاد", "بیدار", "ورزش", "能量", "提神", "振奋", "运动", "跳舞"],
    "memory": ["memory", "dementia", "alzheimer", "forget", "remember", "memoria", "demencia", "حافظه", "آلزایمر", "فراموش", "记忆", "痴呆", "阿尔茨海默"],
}

# Expression -> (valence, arousal) anchors; probabilities from face-api.js expression net.
EXPR_ANCHORS = {"neutral": (0.0, 0.35), "happy": (0.7, 0.55), "sad": (-0.6, 0.25), "angry": (-0.6, 0.8),
                "fearful": (-0.5, 0.85), "disgusted": (-0.5, 0.6), "surprised": (0.1, 0.8)}

# Explicit self-report words -> (valence, arousal)
SELF_WORDS = {"calm": (0.3, 0.2), "tired": (-0.1, 0.15), "sleepy": (0.0, 0.1), "exhausted": (-0.3, 0.1), "sad": (-0.6, 0.25),
              "anxious": (-0.5, 0.8), "stressed": (-0.5, 0.75), "panic": (-0.7, 0.95), "angry": (-0.6, 0.85), "happy": (0.6, 0.6),
              "excited": (0.6, 0.85), "overwhelmed": (-0.5, 0.85), "numb": (-0.3, 0.15), "restless": (-0.2, 0.75), "lonely": (-0.5, 0.3),
              "fine": (0.1, 0.4), "okay": (0.05, 0.4), "ok": (0.05, 0.4)}


def detect_goal(text: str, default: str | None = None) -> tuple[str | None, list[str]]:
    t = (text or "").lower()
    hits: list[tuple[int, str, str]] = []
    for goal, words in LEXICON.items():
        for w in words:
            i = t.find(w)
            if i >= 0:
                hits.append((i, goal, w))
    if not hits:
        return default, []
    hits.sort()
    # autism wins if mentioned anywhere (it changes the safety envelope); an explicit ask for energy wins over sadness
    if any(h[1] == "autism_calm" for h in hits):
        return "autism_calm", [h[2] for h in hits]
    # "tired, need a boost": the ask (energy) wins over the state (tired/exhausted); an explicit sleep or calm ask still wins
    strong_sleep = {"sleep", "insomnia", "can't sleep", "cannot sleep", "bed", "dormir", "sueño", "insomnio", "خواب", "بی‌خوابی", "بیخوابی", "睡", "失眠", "入睡"}
    if any(h[1] == "energy" for h in hits) and not any(h[1] == "calm" or (h[1] == "sleep" and h[2] in strong_sleep) for h in hits):
        return "energy", [h[2] for h in hits]
    return hits[0][1], [h[2] for h in hits]


def from_face(expr: dict[str, float] | None) -> tuple[float, float, float] | None:
    """Expression probabilities -> (valence, arousal, confidence)."""
    if not expr:
        return None
    tot = sum(max(float(v), 0.0) for v in expr.values()) or 1.0
    v = a = 0.0
    for k, p in expr.items():
        if k in EXPR_ANCHORS:
            av, aa = EXPR_ANCHORS[k]
            v += av * float(p) / tot
            a += aa * float(p) / tot
    top = max(float(p) for p in expr.values()) / tot
    # neutral-dominated faces say little; confidence tracks how non-neutral the reading is
    conf = 0.25 + 0.5 * (1 - float(expr.get("neutral", 0)) / tot) * top
    return v, a, min(conf, 0.75)


def from_voice(voice: dict[str, float] | None) -> tuple[float, float, float] | None:
    """Prosody -> (valence, arousal, confidence). energy 0..1 (RMS, normalised), pitch_var 0..1, rate 0..1 (speech rate)."""
    if not voice:
        return None
    e = min(max(float(voice.get("energy", 0.0)), 0.0), 1.0)
    pv = min(max(float(voice.get("pitch_var", 0.0)), 0.0), 1.0)
    r = min(max(float(voice.get("rate", 0.5)), 0.0), 1.0)
    arousal = 0.15 + 0.45 * e + 0.25 * pv + 0.15 * r
    valence = 0.0 + 0.2 * pv - 0.1 * (1 - e)      # prosody says little about valence
    conf = 0.2 + 0.3 * e
    return valence, min(arousal, 1.0), min(conf, 0.5)


def from_text(text: str) -> tuple[float, float, float] | None:
    t = (text or "").lower()
    vals = [SELF_WORDS[w] for w in SELF_WORDS if re.search(r"\b" + re.escape(w) + r"\b", t)]
    if not vals:
        return None
    v = sum(x[0] for x in vals) / len(vals)
    a = sum(x[1] for x in vals) / len(vals)
    return v, a, 0.6


def fuse(parts: list[tuple[float, float, float] | None]) -> dict[str, float]:
    ps = [p for p in parts if p]
    if not ps:
        return {"valence": 0.0, "arousal": 0.45, "confidence": 0.15}
    w = sum(p[2] for p in ps) or 1.0
    v = sum(p[0] * p[2] for p in ps) / w
    a = sum(p[1] * p[2] for p in ps) / w
    conf = 1 - 1 / (1 + sum(p[2] for p in ps))   # saturating: more agreeing signals, more confidence
    return {"valence": round(v, 3), "arousal": round(a, 3), "confidence": round(conf, 3)}


def listen(request: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """request: {text, goal?, face?, voice?, local_hour?} -> listener report."""
    text = str(request.get("text") or "")[:400]
    goal_hint, words = detect_goal(text, None)
    face = from_face(request.get("face"))
    voice = from_voice(request.get("voice"))
    said = from_text(text)
    override = request.get("override")
    corrected = None
    if isinstance(override, dict) and "arousal" in override and "valence" in override:
        try:
            corrected = (max(-1.0, min(1.0, float(override["valence"]))), max(0.0, min(1.0, float(override["arousal"]))), 0.9)
        except (TypeError, ValueError):
            corrected = None
    mood = fuse([said, face, voice, corrected])
    signals = [n for n, p in (("text", said), ("face", face), ("voice", voice), ("corrected by person", corrected)) if p]
    hour = request.get("local_hour")
    try:
        hour = int(hour) if hour is not None else datetime.now().hour
    except (TypeError, ValueError):
        hour = datetime.now().hour
    # goal: explicit > words in the request > inferred from what the person shows > their usual
    inferred = None
    if not request.get("goal") and not goal_hint and (face or voice or corrected):
        v, a = mood["valence"], mood["arousal"]
        if v < -0.25 and a < 0.5:
            inferred = "mood"
        elif a > 0.6 and v < 0.1:
            inferred = "calm"
        elif a < 0.3 and (hour >= 21 or hour < 6):
            inferred = "sleep"
        elif a < 0.3:
            inferred = "focus" if 8 <= hour < 18 else "calm"
        else:
            inferred = "calm"
    goal = request.get("goal") or goal_hint or inferred or profile.get("default_goal") or "calm"
    if goal not in GOALS:
        goal = "calm"
    observations: list[str] = []
    expr = request.get("face") or {}
    if face and expr:
        top = sorted(((k, float(v)) for k, v in expr.items()), key=lambda kv: -kv[1])[:2]
        secs = request.get("face_seconds")
        observations.append("face: " + ", ".join(f"{k} {int(p * 100)}%" for k, p in top) + (f" over {int(secs)} s" if secs else ""))
    vf = request.get("voice") or {}
    if voice:
        e = float(vf.get("energy", 0)); pv = float(vf.get("pitch_var", 0))
        observations.append("voice: " + ("flat, " if pv < 0.2 else "lively, ") + ("quiet" if e < 0.3 else "strong"))
    if corrected:
        observations.append("you corrected the reading by hand")
    if inferred:
        observations.append(f"no goal was stated; from what you show, {inferred.replace('_', ' ')} is the goal")
    notes: list[str] = []
    if goal == "focus" and (hour >= 23 or hour < 5):
        notes.append("focus requested late at night; a sleep session may serve better")
    if goal == "focus" and mood["arousal"] < 0.25 and "face" in signals:
        notes.append("face and voice read as low energy; focus ramp will start gently")
    if goal in ("sleep",) and mood["arousal"] > 0.7:
        notes.append("arousal is high for a sleep session; ISO descent will start faster and longer")
    if goal == "mood" and mood["valence"] > 0.4:
        notes.append("mood reads as positive; lift protocol will stay light")
    if (profile.get("age") or 99) < 13 and goal == "focus":
        notes.append("child profile: pulse depth and volume capped")
    return {"goal": goal, "goal_words": words, "mood": mood, "signals": signals, "hour": hour, "observations": observations, "inferred": inferred,
            "arousal_bpm": round(52 + 60 * mood["arousal"]),  # where the ISO 'meet' segment starts
            "notes": notes, "text_len": len(text)}


# ---------------------------------------------------------------- conversational intents
INTENTS: dict[str, list[str]] = {
    "slower": ["slower", "slow down", "too fast", "más lento", "mas lento", "despacio", "آهسته", "کندتر", "慢", "慢一点"],
    "faster": ["faster", "speed up", "too slow", "más rápido", "mas rapido", "تندتر", "سریع", "快", "快一点"],
    "softer": ["softer", "quieter", "too loud", "gentler", "más suave", "mas suave", "bajo", "ملایم", "آرام‌تر", "轻", "柔和"],
    "brighter": ["brighter", "warmer", "more energy", "más brillante", "mas brillante", "روشن‌تر", "明亮", "亮"],
    "darker": ["darker", "deeper", "más oscuro", "mas oscuro", "تاریک‌تر", "暗"],
    "no_vocals": ["no vocals", "no voice", "no singing", "instrumental", "without lyrics", "sin voz", "sin letra", "بدون خواننده", "بی‌کلام", "纯音乐", "无人声"],
    "vocals": ["with vocals", "with singing", "with lyrics", "con voz", "con letra", "با خواننده", "با کلام", "人声"],
    "longer": ["longer", "more time", "más largo", "mas largo", "طولانی‌تر", "更长"],
    "shorter": ["shorter", "less time", "quick", "más corto", "mas corto", "کوتاه‌تر", "更短"],
    "why": ["why", "explain", "por qué", "porque", "چرا", "为什么", "解释"],
    "stop": ["stop", "pause", "enough", "para", "detente", "بس", "توقف", "停"],
}
LIKE_PATTERNS = [r"more like ([^,.!?]+)", r"something like ([^,.!?]+)", r"like ([^,.!?]+)", r"más como ([^,.!?]+)", r"mas como ([^,.!?]+)", r"بیشتر شبیه ([^,.!?]+)", r"像 ([^,.!?，。]+)"]
DISLIKE_PATTERNS = [r"not ([^,.!?]+)", r"no more ([^,.!?]+)", r"skip ([^,.!?]+)", r"no quiero ([^,.!?]+)", r"نه ([^,.!?]+)", r"不要 ([^,.!?，。]+)"]
STOP_LIKE = {"this", "that", "it", "me", "slower", "faster", "softer", "music", "esto", "eso", "این", "آن"}


def parse_intents(text: str) -> dict[str, Any]:
    t = (text or "").lower()
    out: dict[str, Any] = {"flags": [], "like": [], "dislike": []}
    for name, words in INTENTS.items():
        if any(w in t for w in words):
            out["flags"].append(name)
    for pat in LIKE_PATTERNS:
        for m in re.finditer(pat, t):
            name = m.group(1).strip()
            if name and name.split()[0] not in STOP_LIKE and len(name) < 60:
                out["like"].append(name)
    for pat in DISLIKE_PATTERNS:
        for m in re.finditer(pat, t):
            name = m.group(1).strip()
            if name and name.split()[0] not in STOP_LIKE and len(name) < 60 and not any(name.startswith(w) for w in ("vocals", "voice", "singing", "lyrics", "too", "so", "more")):
                out["dislike"].append(name)
    return out
