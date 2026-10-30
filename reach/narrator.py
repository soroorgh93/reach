"""Narrator: phrases the council's decision for the person. Template by default (four
languages). If ANTHROPIC_API_KEY is set, a language model may rephrase the template from
the fact sheet, but every number in its text must already exist in the facts or the
template is used instead (number-grounding guard). The narrator never decides anything."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

TEMPLATES = {
    "en": "{name}, you asked for {goal}. Because you love {favourites}, Qloo found {carrier}; the texture you lean toward is {texture}, so the session is built on a {palette} palette in {key}. {protocol} starts at {bpm0} bpm with a pulse of {hz0} Hz and ends at {hz_end} Hz over {duration} minutes. The evidence behind it is grade {grade} ({evidence_source}).",
    "es": "{name}, pediste {goal}. Como te gustan {favourites}, Qloo encontró {carrier}; tu textura es {texture}, así que la sesión usa una paleta de {palette} en {key}. {protocol} empieza a {bpm0} bpm con un pulso de {hz0} Hz y termina en {hz_end} Hz en {duration} minutos. La evidencia es de grado {grade} ({evidence_source}).",
    "fa": "{name}، شما {goal} خواستید. چون {favourites} را دوست دارید، Qloo {carrier} را یافت؛ بافت سلیقهٔ شما {texture} است، پس جلسه بر پایهٔ پالت {palette} در {key} ساخته شد. {protocol} با {bpm0} ضرب در دقیقه و پالس {hz0} هرتز شروع می‌شود و طی {duration} دقیقه به {hz_end} هرتز می‌رسد. شواهد پشت آن درجهٔ {grade} است ({evidence_source}).",
    "zh": "{name}，你想要{goal}。因为你喜欢{favourites}，Qloo 找到了{carrier}；你偏好的质感是{texture}，所以这次会话以{key}调的{palette}音色构建。{protocol}从 {bpm0} bpm 和 {hz0} Hz 脉冲开始，在 {duration} 分钟内降至 {hz_end} Hz。其证据等级为 {grade}（{evidence_source}）。",
}
GOAL_WORDS = {
    "en": {"focus": "focus", "sleep": "sleep", "calm": "calm", "autism_calm": "a sensory-safe session", "mood": "a lift in mood", "memory": "memory support", "energy": "energy", "visual": "a visual and haptic session"},
    "es": {"focus": "concentración", "sleep": "dormir", "calm": "calma", "autism_calm": "una sesión sensorialmente segura", "mood": "ánimo", "memory": "apoyo a la memoria", "energy": "energía", "visual": "una sesión visual y háptica"},
    "fa": {"focus": "تمرکز", "sleep": "خواب", "calm": "آرامش", "autism_calm": "جلسه‌ای حسی‌-ایمن", "mood": "بهبود خلق", "memory": "حمایت از حافظه", "energy": "انرژی", "visual": "جلسهٔ دیداری و لمسی"},
    "zh": {"focus": "专注", "sleep": "睡眠", "calm": "平静", "autism_calm": "感官安全的会话", "mood": "情绪提升", "memory": "记忆支持", "energy": "能量", "visual": "视觉与触觉会话"},
}
PALETTE_WORDS = {"piano": "piano", "strings": "strings", "nylon": "nylon guitar", "epiano": "electric piano", "plucked": "plucked folk", "synth": "soft synth", "bells": "bells", "guitar": "guitar"}


def _join(xs: list[str], lang: str) -> str:
    xs = [x for x in xs if x]
    if not xs:
        return "—"
    if len(xs) == 1:
        return xs[0]
    sep = {"en": " and ", "es": " y ", "fa": " و ", "zh": "和"}.get(lang, " and ")
    return ", ".join(xs[:-1]) + sep + xs[-1]


OBS_LEAD = {"en": "I noticed: ", "es": "Noté: ", "fa": "متوجه شدم: ", "zh": "我注意到："}


def template(facts: dict[str, Any], lang: str) -> str:
    lang = lang if lang in TEMPLATES else "en"
    obs = facts.get("observations") or []
    lead = (OBS_LEAD[lang] + "; ".join(obs) + ". ") if obs else ""
    return lead + TEMPLATES[lang].format(
        name=facts.get("name") or "", goal=GOAL_WORDS[lang].get(facts["goal"], facts["goal"]), favourites=_join(facts["favourites"], lang),
        carrier=_join(facts["carrier"], lang), texture=_join(facts["texture"][:3], lang), palette=PALETTE_WORDS.get(facts["palette"], facts["palette"]),
        key=facts["key"], protocol=facts["protocol"], bpm0=facts["bpm0"], hz0=_num(facts["hz0"]), hz_end=_num(facts["hz_end"]), duration=facts["duration"],
        grade=facts["grade"], evidence_source=facts["evidence_source"]).replace("  ", " ").strip()


def _num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def numbers_in(text: str) -> set[str]:
    return {m.replace(",", "") for m in re.findall(r"\d+(?:[.,]\d+)?", text)}


def grounded(text: str, facts: dict[str, Any]) -> bool:
    allowed = set()
    for v in facts.values():
        if isinstance(v, (int, float)):
            allowed |= numbers_in(str(v)) | {_num(v)}
        elif isinstance(v, str):
            allowed |= numbers_in(v)
        elif isinstance(v, list):
            for x in v:
                allowed |= numbers_in(str(x))
    return numbers_in(text) <= allowed


def narrate(facts: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    base = template(facts, lang)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"text": base, "by": "template", "grounded": True}
    try:
        body = {"model": os.environ.get("REACH_LLM_MODEL", "claude-haiku-4-5"), "max_tokens": 220,
                "messages": [{"role": "user", "content": "Rewrite this for the person in two warm, plain sentences, same language, keeping every number and name exactly, adding nothing:\n\n" + base}]}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                     headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=12) as r:
            out = json.loads(r.read().decode())
        text = "".join(b.get("text", "") for b in out.get("content", [])).strip()
        if text and grounded(text, facts) and len(text) < 600:
            return {"text": text, "by": "llm", "grounded": True}
        return {"text": base, "by": "template", "grounded": True, "llm_rejected": "ungrounded number or too long"}
    except Exception as e:  # network, auth, shape
        return {"text": base, "by": "template", "grounded": True, "llm_error": str(e)[:80]}


# ---------------------------------------------------------------- agent voices
# Each agent answers the person in its own voice, from computed facts only. Four languages.
R = {
    "en": {
        "listener_heard": "I heard: “{text}”.", "listener_read": "You read as {mood} (arousal {a}, valence {v}, confidence {c}).",
        "listener_goal": "Goal: {goal}{how}.", "listener_inferred": " (you did not say; I took it from what you show)", "listener_stated": " (you said so)",
        "listener_intents": "You asked me to make it {flags}; done.", "listener_learned": "Noted: more like {liked}; not {disliked}.",
        "listener_obs": "I noticed: {obs}.",
        "taste": "Through Qloo, your love of {favs} leads to {carrier}{pct}. The texture you lean toward is {texture}, so the instrument palette is {palette}.",
        "taste_memory": " I boosted {liked} you liked and excluded {disliked} you rejected.", "taste_fit": " {fit}% of your affinities fit this protocol's texture.",
        "clinician": "I weighed {cands}. {chosen} wins: evidence {ev}, fit {fit}, taste {taste}. Rules: {rules}.", "clinician_stances": " The person, carer and clinician stances {agree}.",
        "agree": "all agree", "disagree": "disagree; the least-favourable prior settled it",
        "composer": "{duration} minutes in {key} {mode}, {palette}: {path}. Pulse {entr} at depth {depth}, output capped at {gain} dBFS.{breath}",
        "composer_breath": " A breathing cue at {rate} per minute for the first {bm} minutes.",
        "guardian": "Checks: {checks}.", "gate": "Recommendation {verdict}: p = {p}, benefit {benefit} against cost {cost}.", "recommend": "justified", "hold": "on hold",
        "mood": {"sad": "sad", "tense": "tense", "wired": "wired", "tired": "tired", "low": "low and quiet", "bright": "bright", "calm": "calm and steady", "flat": "flat"},
        "flags": {"slower": "slower", "faster": "faster", "softer": "softer", "brighter": "brighter", "darker": "darker", "no_vocals": "instrumental", "vocals": "with vocals", "longer": "longer", "shorter": "shorter", "why": "explained", "stop": "stopped"},
    },
    "es": {
        "listener_heard": "Escuché: “{text}”.", "listener_read": "Te leo como {mood} (activación {a}, valencia {v}, confianza {c}).",
        "listener_goal": "Objetivo: {goal}{how}.", "listener_inferred": " (no lo dijiste; lo tomé de lo que muestras)", "listener_stated": " (lo dijiste tú)",
        "listener_intents": "Me pediste que lo hiciera {flags}; hecho.", "listener_learned": "Anotado: más como {liked}; no {disliked}.",
        "listener_obs": "Noté: {obs}.",
        "taste": "A través de Qloo, tu gusto por {favs} lleva a {carrier}{pct}. Tu textura es {texture}, así que la paleta es {palette}.",
        "taste_memory": " Reforcé {liked} que te gustó y excluí {disliked} que rechazaste.", "taste_fit": " El {fit}% de tus afinidades encaja con la textura de este protocolo.",
        "clinician": "Sopesé {cands}. Gana {chosen}: evidencia {ev}, ajuste {fit}, gusto {taste}. Reglas: {rules}.", "clinician_stances": " Las posturas de persona, cuidador y clínico {agree}.",
        "agree": "coinciden", "disagree": "difieren; el prior menos favorable lo decidió",
        "composer": "{duration} minutos en {key} {mode}, {palette}: {path}. Pulso {entr} a profundidad {depth}, salida limitada a {gain} dBFS.{breath}",
        "composer_breath": " Una guía de respiración a {rate} por minuto durante los primeros {bm} minutos.",
        "guardian": "Controles: {checks}.", "gate": "Recomendación {verdict}: p = {p}, beneficio {benefit} frente a coste {cost}.", "recommend": "justificada", "hold": "en espera",
        "mood": {"sad": "triste", "tense": "tenso", "wired": "acelerado", "tired": "cansado", "low": "bajo y callado", "bright": "brillante", "calm": "tranquilo y estable", "flat": "plano"},
        "flags": {"slower": "más lento", "faster": "más rápido", "softer": "más suave", "brighter": "más brillante", "darker": "más oscuro", "no_vocals": "instrumental", "vocals": "con voz", "longer": "más largo", "shorter": "más corto", "why": "explicado", "stop": "detenido"},
    },
    "fa": {
        "listener_heard": "شنیدم: «{text}».", "listener_read": "شما {mood} خوانده می‌شوید (برانگیختگی {a}، ظرفیت {v}، اطمینان {c}).",
        "listener_goal": "هدف: {goal}{how}.", "listener_inferred": " (نگفتید؛ از آنچه نشان می‌دهید برداشت کردم)", "listener_stated": " (خودتان گفتید)",
        "listener_intents": "خواستید {flags} شود؛ انجام شد.", "listener_learned": "یادداشت شد: بیشتر شبیه {liked}؛ نه {disliked}.",
        "listener_obs": "متوجه شدم: {obs}.",
        "taste": "از طریق Qloo، علاقهٔ شما به {favs} به {carrier}{pct} می‌رسد. بافت سلیقهٔ شما {texture} است، پس پالت سازها {palette} شد.",
        "taste_memory": " {liked} را که پسندیدید تقویت و {disliked} را که رد کردید حذف کردم.", "taste_fit": " {fit}٪ از قرابت‌های شما با بافت این پروتکل می‌خواند.",
        "clinician": "{cands} را سنجیدم. {chosen} برنده شد: شواهد {ev}، تناسب {fit}، سلیقه {taste}. قواعد: {rules}.", "clinician_stances": " دیدگاه فرد، مراقب و پزشک {agree}.",
        "agree": "همگی هم‌نظرند", "disagree": "اختلاف دارند؛ پیشین نامساعدترین آن را حل کرد",
        "composer": "{duration} دقیقه در {key} {mode}، {palette}: {path}. پالس {entr} با عمق {depth}، خروجی محدود به {gain} dBFS.{breath}",
        "composer_breath": " نشانهٔ تنفس با {rate} در دقیقه برای {bm} دقیقهٔ اول.",
        "guardian": "بررسی‌ها: {checks}.", "gate": "توصیه {verdict}: p = {p}، سود {benefit} در برابر هزینهٔ {cost}.", "recommend": "موجه است", "hold": "معلق است",
        "mood": {"sad": "غمگین", "tense": "تنیده", "wired": "برانگیخته", "tired": "خسته", "low": "پایین و ساکت", "bright": "روشن", "calm": "آرام و ثابت", "flat": "یکنواخت"},
        "flags": {"slower": "آهسته‌تر", "faster": "تندتر", "softer": "ملایم‌تر", "brighter": "روشن‌تر", "darker": "تاریک‌تر", "no_vocals": "بی‌کلام", "vocals": "با خواننده", "longer": "طولانی‌تر", "shorter": "کوتاه‌تر", "why": "توضیح داده شد", "stop": "متوقف شد"},
    },
    "zh": {
        "listener_heard": "我听到：“{text}”。", "listener_read": "你读取为{mood}（唤醒 {a}，效价 {v}，置信 {c}）。",
        "listener_goal": "目标：{goal}{how}。", "listener_inferred": "（你没有说；我从你表现出的状态推断）", "listener_stated": "（你说的）",
        "listener_intents": "你要求{flags}；已完成。", "listener_learned": "已记录：更像{liked}；不要{disliked}。",
        "listener_obs": "我注意到：{obs}。",
        "taste": "通过 Qloo，你对{favs}的喜爱指向{carrier}{pct}。你偏好的质感是{texture}，因此音色选用{palette}。",
        "taste_memory": " 我强化了你喜欢的{liked}，排除了你拒绝的{disliked}。", "taste_fit": " 你有 {fit}% 的亲和度符合该方案的质感。",
        "clinician": "我权衡了{cands}。{chosen}胜出：证据 {ev}，匹配 {fit}，偏好 {taste}。规则：{rules}。", "clinician_stances": " 本人、照护者与临床立场{agree}。",
        "agree": "一致", "disagree": "不一致；由最不利先验裁定",
        "composer": "{duration} 分钟，{key} {mode}，{palette}：{path}。{entr}脉冲深度 {depth}，输出上限 {gain} dBFS。{breath}",
        "composer_breath": " 前 {bm} 分钟有每分钟 {rate} 次的呼吸提示。",
        "guardian": "检查：{checks}。", "gate": "建议{verdict}：p = {p}，收益 {benefit} 对成本 {cost}。", "recommend": "成立", "hold": "暂缓",
        "mood": {"sad": "悲伤", "tense": "紧张", "wired": "紧绷亢奋", "tired": "疲惫", "low": "低落安静", "bright": "明亮", "calm": "平静稳定", "flat": "平淡"},
        "flags": {"slower": "更慢", "faster": "更快", "softer": "更柔和", "brighter": "更明亮", "darker": "更暗", "no_vocals": "纯音乐", "vocals": "带人声", "longer": "更长", "shorter": "更短", "why": "已解释", "stop": "已停止"},
    },
}


def mood_word(m: dict[str, float], lang: str) -> str:
    a, v = float(m.get("arousal", 0.45)), float(m.get("valence", 0.0)); W = R[lang]["mood"]
    if v < -0.3 and a < 0.5: return W["sad"]
    if v < -0.2 and a >= 0.6: return W["tense"]
    if a >= 0.65: return W["wired"]
    if a < 0.25 and v < 0: return W["tired"]
    if a < 0.3: return W["low"]
    if v > 0.3: return W["bright"]
    if abs(v) < 0.1 and a < 0.45: return W["calm"]
    return W["flat"]


def agent_replies(x: dict[str, Any], lang: str = "en") -> list[dict[str, str]]:
    lang = lang if lang in R else "en"; S = R[lang]; L = x["listener"]; T = x["taste"]; ses = x["session"]; adj = x["adjudication"]; proto = x["protocol"]
    out: list[dict[str, str]] = []
    # Listener
    parts = []
    text = (x.get("request_text") or "").strip()
    if text:
        parts.append(S["listener_heard"].format(text=text[:120]))
    parts.append(S["listener_read"].format(mood=mood_word(L["mood"], lang), a=L["mood"]["arousal"], v=L["mood"]["valence"], c=L["mood"]["confidence"]))
    parts.append(S["listener_goal"].format(goal=GOAL_WORDS[lang].get(L["goal"], L["goal"]), how=S["listener_inferred"] if L.get("inferred") else (S["listener_stated"] if L.get("goal_words") else "")))
    if L.get("observations"):
        parts.append(S["listener_obs"].format(obs="; ".join(L["observations"])))
    flags = [S["flags"].get(f, f) for f in L.get("intents", []) if f not in ("why", "stop")]
    if flags:
        parts.append(S["listener_intents"].format(flags=_join(flags, lang)))
    learned = L.get("learned", {})
    if learned.get("liked") or learned.get("disliked"):
        parts.append(S["listener_learned"].format(liked=_join([y["name"] for y in learned.get("liked", [])], lang), disliked=_join([y["name"] for y in learned.get("disliked", [])], lang)))
    out.append({"agent": "listener", "text": " ".join(parts)})
    # Taste
    favs = [f["name"] for f in x["profile"].get("favorites", [])[:3]]; carrier = T.get("carrier", [])[:3]
    pct = f" ({int(carrier[0]['affinity'] * 100)}%)" if carrier and carrier[0].get("affinity") else ""
    t = S["taste"].format(favs=_join(favs, lang), carrier=_join([c["name"] for c in carrier], lang), pct=pct, texture=_join(T.get("texture_tags", [])[:3], lang), palette=PALETTE_WORDS.get(ses["palette"], ses["palette"]))
    mu = T.get("memory_used") or {}
    if mu.get("liked") or mu.get("disliked"):
        t += S["taste_memory"].format(liked=mu.get("liked", 0), disliked=mu.get("disliked", 0))
    if T.get("fit_rate") is not None:
        t += S["taste_fit"].format(fit=int(T["fit_rate"] * 100))
    out.append({"agent": "taste", "text": t})
    # Group fairness (when more than one person is in the room)
    G = x.get("group")
    if G and G.get("ok"):
        adj = G["adjudication"]; names = {c["entity_id"]: c["name"] for c in G["carrier"]}
        w = ", ".join(f"{k} {v}" for k, v in adj["weights"].items())
        fair = {"en": "Room of {n}: {members}. Best on average would be {bayes}; least-bad for the unhappiest person is {minimax}; the least-favourable prior settles on {lfp} with weights {w}.{instr}",
                "es": "Sala de {n}: {members}. Lo mejor en promedio sería {bayes}; lo menos malo para quien peor queda es {minimax}; el prior menos favorable elige {lfp} con pesos {w}.{instr}",
                "fa": "اتاقی با {n} نفر: {members}. بهترین میانگین {bayes} بود؛ کم‌ضررترین برای ناراضی‌ترین نفر {minimax}؛ پیشین نامساعدترین {lfp} را با وزن‌های {w} برگزید.{instr}",
                "zh": "{n} 人同在：{members}。平均最佳是 {bayes}；对最不满意者最不坏的是 {minimax}；最不利先验选定 {lfp}，权重 {w}。{instr}"}[lang]
        instr = {"en": " Someone asked for no vocals, so the session is instrumental.", "es": " Alguien pidió sin voz, así que la sesión es instrumental.", "fa": " کسی بی‌کلام خواست، پس جلسه بی‌کلام است.", "zh": " 有人要求纯音乐，因此本次会话为器乐。"}[lang] if G.get("instrumental") else ""
        txt = fair.format(n=len(G["members"]), members=_join(G["members"], lang), bayes=names.get(adj["bayes"], adj["bayes"]), minimax=names.get(adj["minimax"], adj["minimax"]), lfp=names.get(adj["lfp"], adj["lfp"]), w=w, instr=instr)
        if G.get("unread"):
            txt += {"en": " I could not read {u} through Qloo yet: add something they love.", "es": " Aún no pude leer a {u} en Qloo: añade algo que le guste.", "fa": " هنوز نتوانستم {u} را از طریق Qloo بخوانم: چیزی که دوست دارد اضافه کنید.", "zh": " 我还无法通过 Qloo 读取{u}：请添加他们喜欢的东西。"}[lang].format(u=_join(G["unread"], lang))
        out.append({"agent": "group", "text": txt})
    # Clinician
    rows = {r["id"]: r for r in x["candidates"]}; ch = rows[proto["id"]]
    rules = ", ".join(f"{r['rule']} {r['verdict']}" for r in x["rules"]) or "—"
    c = S["clinician"].format(cands=_join(list(rows), lang), chosen=proto["name"], ev=ch["evidence"], fit=ch["reachability"], taste=ch["engagement"], rules=rules)
    c += S["clinician_stances"].format(agree=S["agree"] if adj["bayes"] == adj["minimax"] == adj["lfp"] else S["disagree"])
    out.append({"agent": "clinician", "text": c})
    # Composer
    path = " → ".join(f"{s['name']} {_num(s['hz_from'])}→{_num(s['hz_to'])} Hz @ {s['bpm']} bpm" for s in ses["segments"])
    br = ses.get("breathing")
    comp = S["composer"].format(duration=ses["duration_min"], key=ses["key"], mode=ses["segments"][0]["mode"], palette=PALETTE_WORDS.get(ses["palette"], ses["palette"]), path=path, entr=ses["entrainment"], depth=ses["pulse_depth"], gain=ses["gain_dbfs"],
                                breath=S["composer_breath"].format(rate=br["rate_per_min"], bm=br["minutes"]) if br else "")
    out.append({"agent": "compose", "text": comp})
    # Library: cited passages for a question
    for ps in (x.get("passages") or [])[:2]:
        lead = {"en": "From the evidence", "es": "De la evidencia", "fa": "از شواهد", "zh": "来自证据"}[lang]
        out.append({"agent": "library", "text": f"{lead}: {ps['title']}. {ps['text']} ({ps['source']})", "url": ps.get("url", "")})
    # Guardian + gate
    out.append({"agent": "guardian", "text": S["guardian"].format(checks="; ".join(f"{g['check']} {g['action']}" for g in x["guardian"]) or "—")})
    g = x["gate"]
    out.append({"agent": "gate", "text": S["gate"].format(verdict=S["recommend"] if g["justified"] else S["hold"], p=g["p"], benefit=g["benefit"], cost=g["cost"])})
    return out
