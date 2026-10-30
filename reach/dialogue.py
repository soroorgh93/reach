"""The Conversation agent: what the person actually said, read against what is playing right now.

It sits in front of the council and decides what a message needs:
  play / only   an artist the person named ("I said Hayedeh", "play Dariush", "only my artists")
  avoid         something they do not want ("not this one", "no more Kalben")
  source        podcasts, real nature sound, just the frequencies, the visual session, songs again
  answer        a question: why this singer, why this session, does this work, is it safe
  next / pause / resume
  compose       a new need ("I'm sleepy", "slower", "no vocals"): only then is the council asked again

Rules come first: deterministic, offline, in four languages. When a language model is configured it reads the
same context and returns the same JSON, so the person gets real understanding of free speech; its answer may
use only facts it was handed (what is playing, why, the protocol and its evidence). Providers, in order:
  Ollama on this machine (OLLAMA_URL, default http://127.0.0.1:11434; OLLAMA_MODEL, default llama3.2): words
  never leave the computer;  ANTHROPIC_API_KEY (ANTHROPIC_MODEL);  OPENAI_API_KEY (OPENAI_MODEL).
REACH_LLM=off turns the model off; REACH_LLM_ORDER changes the order. Nothing is sent to Qloo from here.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import urllib.request
from typing import Any

from .mood import INTENTS, detect_goal
from .narrator import GOAL_WORDS, mood_word, _join
from .rag import retrieve

LANGS = ("en", "es", "fa", "zh")

# ------------------------------------------------------------------ words
WHY = ("why", "how come", "what is this", "what's this", "who is this", "who's this", "who is that", "explain", "por qué", "porque", "quién es", "qué es esto",
       "چرا", "این کیه", "این کیست", "این چیه", "为什么", "这是谁", "这是什么", "?", "？", "؟")
EVIDENCE = ("evidence", "science", "scientific", "study", "studies", "research", "proof", "proven", "does it work", "does this work", "is it real", "safe", "safety",
            "hz", "hertz", "frequency", "frequencies", "binaural", "isochronic", "alpha", "beta", "theta", "delta", "gamma", "entrain", "brain", "nervous system", "how does",
            "evidencia", "ciencia", "estudio", "funciona", "seguro", "frecuencia", "cerebro", "شواهد", "علم", "علمی", "پژوهش", "تحقیق", "کار می‌کند", "امن", "فرکانس", "هرتز", "مغز",
            "证据", "科学", "研究", "有用吗", "安全", "频率", "赫兹", "大脑")
SESSION_WHY = ("this session", "this plan", "this protocol", "esta sesión", "این جلسه", "这个疗程", "why this?", "why this session")
OTHER_SINGER = ("another singer", "other singer", "another artist", "other artist", "different singer", "someone else", "not my singer", "not my artist", "random singer",
                "otro cantante", "otra cantante", "otro artista", "خواننده دیگه", "خوانندهٔ دیگر", "خواننده دیگر", "یه خواننده دیگه", "别的歌手", "其他歌手", "另一个歌手")
OWN = ("my favourites", "my favorites", "my favourite artists", "my favorite artists", "my artists", "my own artists", "my own songs", "my own music", "my singers", "my songs",
       "my list", "the ones i chose", "the ones i picked", "what i chose", "mis favoritos", "mis artistas", "mis cantantes", "mis canciones",
       "خواننده‌های خودم", "خواننده های خودم", "آهنگ‌های خودم", "آهنگ های خودم", "علاقه‌مندی‌هایم", "مورد علاقه‌ام", "我喜欢的歌手", "我的歌手", "我选的", "我的最爱")
ONLY = ("only", "just", "nothing but", "solo", "sólo", "فقط", "تنها", "只", "只要", "只听")
COMPLAINT = ("i don't like", "i dont like", "don't like this", "hate this", "hate it", "not this", "this is bad", "this is wrong", "wrong song", "wrong singer", "terrible", "awful",
             "boring", "annoying", "irrelevant", "turn this off", "no me gusta", "esto no", "دوست ندارم", "اینو نمی‌خوام", "این نه", "خیلی بده", "我不喜欢", "不要这个", "难听")
NEXT = ("next", "skip", "next one", "next song", "another song", "another one", "siguiente", "otra", "salta", "بعدی", "رد کن", "یکی دیگه", "下一首", "换一首", "跳过")
PAUSE = ("pause", "stop", "stop it", "be quiet", "silence", "enough", "para ya", "detente", "pausa", "بسه", "بس کن", "توقف", "قطع کن", "ساکت", "暂停", "停止", "停下")
RESUME = ("play", "resume", "continue", "go on", "start", "sigue", "continúa", "reproduce", "ادامه", "پخش", "شروع", "继续", "播放", "开始")
PODCAST = ("podcast", "podcasts", "pódcast", "پادکست", "播客")
SCAPES = {"rain": ("rain", "lluvia", "باران", "雨"), "fire": ("fire", "campfire", "fireplace", "hoguera", "fuego", "آتش", "篝火", "火"), "ocean": ("ocean", "sea", "waves", "mar", "olas", "دریا", "موج", "海"),
          "thunder": ("thunder", "storm", "tormenta", "رعد", "طوفان", "雷"), "forest": ("forest", "birds", "bosque", "pájaros", "جنگل", "پرنده", "森林", "鸟"),
          "river": ("river", "stream", "río", "رود", "河"), "waterfall": ("waterfall", "cascada", "آبشار", "瀑布"), "wind": ("wind", "viento", "باد", "风"),
          "night": ("crickets", "night sounds", "grillos", "جیرجیرک", "蟋蟀"), "bowls": ("singing bowl", "bowls", "cuenco", "کاسه", "颂钵"), "whale": ("whale", "ballena", "نهنگ", "鲸")}
SCAPE_HINT = ("sound", "sounds", "nature", "noise", "sonido", "naturaleza", "صدای", "طبیعت", "声", "自然")
BED = ("only frequencies", "only the frequency", "just the frequency", "just frequencies", "only hz", "just hz", "pure tone", "tones only", "binaural only", "no songs",
       "solo frecuencias", "فقط فرکانس", "فقط هرتز", "只要频率")
VISUAL = ("i can't hear", "i cannot hear", "deaf", "watch", "visual", "something to see", "no puedo oír", "sordo", "نمی‌شنوم", "ناشنوا", "تماشا", "听不见", "聋", "看")
SONGS = ("songs", "music again", "back to songs", "back to music", "canciones", "آهنگ", "موسیقی", "歌")
PLAY_PAT = [r"\b(?:play|put on|i want|i wanna|give me|let me hear|i said|i asked for|i asked|i meant|where is|where's|bring back|back to)\s+(?:me\s+)?(?:some\s+|more\s+|a song by\s+|songs? (?:by|from|of)\s+|music (?:by|from|of)\s+)?(.+?)(?=\s+(?:please|now|instead|again|songs?|music|why|but|and|so)\b|[,.!?;؟]|$)",
            r"\b(?:only|just)\s+(.+?)(?=\s+(?:please|now|songs?|music|why|but|and)\b|[,.!?;؟]|$)",
            r"(?:pon|ponme|toca|quiero|quiero escuchar|dije)\s+(?:a\s+|algo de\s+|canciones de\s+)?(.+?)(?=\s+(?:por favor|ahora)\b|[,.!?;]|$)",
            r"(?:بذار|پخش کن|می‌خوام|میخوام|گفتم)\s+(.+?)(?=[,.!?؛؟]|$)", r"(?:播放|放|我想听|我说了)\s*(.+?)(?=[，。！？,.!?]|$)"]
NOT_NAME = {"something", "anything", "music", "songs", "song", "it", "this", "that", "me", "some", "more", "less", "again", "them", "her", "him", "one", "another", "other",
            "the next", "next", "a podcast", "podcast", "podcasts", "sounds", "sound", "hz", "the music", "my favourites", "my favorites", "my artists", "my songs", "my own",
            "calm", "sleep", "focus", "relax", "relaxing", "sad", "happy", "energy", "slower", "faster", "softer", "louder", "quiet", "something else", "something different",
            "to sleep", "to relax", "to focus", "a song", "a break", "you", "what", "that one", "this one", "it again", "the same", "my", "mine", "us", "them all"}
# music words a "play X" can carry that are kinds of music, not artists ("play some jazz" is a need for the council)
KINDS = {"jazz", "classical", "classic", "lo-fi", "lofi", "lo fi", "pop", "rock", "ambient", "piano", "instrumental", "techno", "house", "edm", "hip hop", "hip-hop", "rap",
         "r&b", "rnb", "soul", "blues", "folk", "country", "reggae", "metal", "punk", "disco", "funk", "opera", "meditation", "chill", "electronic", "dance", "acoustic",
         "guitar", "violin", "strings", "orchestra", "lullaby", "lullabies", "white noise", "brown noise", "pink noise", "binaural beats", "beats", "oldies", "love songs",
         "jazz music", "classical music", "jazz musica", "música clásica", "clásica", "موسیقی کلاسیک", "جاز", "سنتی", "پاپ", "古典", "爵士", "流行", "轻音乐"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", s.replace("’", "'")).strip()


CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]")


def _has(t: str, words) -> bool:
    """Whole-word match (any script written with spaces: "بس" is not inside "بسیار", "stop" not inside "nonstop");
    substring match only for scripts written without spaces (Chinese, Japanese)."""
    for w in words:
        w = norm(w)
        if not w:
            continue
        if CJK.search(w):
            if w in t:
                return True
        elif not w[0].isalnum() or not w[-1].isalnum():
            if w in t:
                return True
        elif re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", t):
            return True
    return False


# Persian/Arabic letters as single consonant symbols (sh = c, kh = x, gh/q = q, zh = j), the same symbols the
# Latin digraphs become, so a letter pair like س + ه (Sohrab) is never read as "sh"
FA = {"ا": "a", "آ": "a", "أ": "a", "إ": "a", "ب": "b", "پ": "p", "ت": "t", "ث": "s", "ج": "j", "چ": "c", "ح": "h", "خ": "x", "د": "d", "ذ": "z", "ر": "r", "ز": "z", "ژ": "j",
      "س": "s", "ش": "c", "ص": "s", "ض": "z", "ط": "t", "ظ": "z", "ع": "", "غ": "q", "ف": "f", "ق": "q", "ک": "k", "ك": "k", "گ": "g", "ل": "l", "م": "m", "ن": "n",
      "و": "v", "ه": "h", "ة": "h", "ی": "y", "ي": "y", "ئ": "y", "ؤ": "v", "ء": ""}


def _skel(s: str) -> str:
    """Consonant skeleton, so هایده and Hayedeh, داریوش and Dariush, شهره and Shohreh, سهراب and Sohrab meet."""
    raw = unicodedata.normalize("NFC", s or "").lower()
    if re.search(r"[\u0600-\u06FF]", raw):
        s = "".join(FA.get(c, c) for c in raw)
    else:
        s = norm(raw).replace("kh", "x").replace("gh", "q").replace("sh", "c").replace("ch", "c").replace("zh", "j").replace("ph", "f")
    s = re.sub(r"(?<=[a-z])h$", "", re.sub(r"[^a-z]", "", s))
    return re.sub(r"(.)\1+", r"\1", re.sub(r"[aeiouyvw']", "", s))


def mentions(t: str, names: list[str], aliases: dict[str, str] | None = None) -> list[tuple[str, int, int]]:
    """(name, start, end) for each known artist the message mentions: by its name (Latin, or Chinese and
    Japanese characters, which have no spaces), by its first name when that is unique, by a Persian or Arabic
    spelling (consonant skeleton), or by another name MusicBrainz knows it by."""
    out: list[tuple[str, int, int]] = []
    def find(k: str, real: str) -> bool:
        if not k:
            return False
        m = re.search(re.escape(k), t) if CJK.search(k) else re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", t)
        if m:
            out.append((real, m.start(), m.end()))
        return bool(m)
    for n in names:
        k = norm(n)
        if len(k) < 2 or (len(k) < 3 and not CJK.search(k)):
            continue
        if find(k, n):
            continue
        first = k.split(" ")[0]
        if len(first) >= 5 and " " in k and sum(1 for x in names if norm(x).split(" ")[0] == first) == 1:
            find(first, n)
    for a_, real in (aliases or {}).items():
        if real in names and not any(o[0] == real for o in out):
            find(norm(a_), real)
    # Persian / Arabic script tokens, matched by skeleton
    toks = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"[\u0600-\u06FF\u200c]+", t)]
    grams = toks + [(a_[0] + " " + b_[0], a_[1], b_[2]) for a_, b_ in zip(toks, toks[1:])]
    for n in names:
        if any(o[0] == n for o in out):
            continue
        k = _skel(n); k1 = _skel(n.split(" ")[0]) if " " in n else None
        if not k or len(k) < 2:
            continue
        for g, st, en in grams:
            gk = _skel(g)
            if (len(gk) >= 3 or (len(gk) == 2 and len(g) >= 4)) and (gk == k or (k1 and len(k1) >= 3 and gk == k1)):
                out.append((n, st, en)); break
    seen, uniq = set(), []
    for o in sorted(out, key=lambda x: x[1]):
        if o[0] not in seen:
            seen.add(o[0]); uniq.append(o)
    return uniq


def _names_in(t: str, names: list[str], aliases: dict[str, str] | None = None) -> list[str]:
    return [n for n, _, _ in mentions(t, names, aliases)]


# negation right before a name ("not Kalben", "no more Kalben", "I don't want Kalben", "بدون داریوش", "不要周杰倫"),
# or right after it in Persian ("هایده نه")
NEG_BEFORE = re.compile(r"(?:^|[\s,،;])(?:not|no more|no|skip|without|stop playing|enough of|don'?t want|do not want|don'?t play|nada de|sin|ni|no quiero|"
                        r"نه|بدون|دیگه نه|نمیخوام|نمی‌خوام|نمی خوام)(?:\s+(?:of|de|any|the|more|از)\b)?\s*$|(?:不要|别放|不想听|别)\s*$")
NEG_AFTER = re.compile(r"^\s*(?:نه|رو نمی‌خوام|را نمی‌خواهم|نمی‌خوام|no|不要)(?!\w)")


def _negated(t: str, st: int, en: int) -> bool:
    return bool(NEG_BEFORE.search(t[max(0, st - 30):st])) or bool(NEG_AFTER.search(t[en:en + 16]))


def _captured(t_raw: str) -> list[str]:
    out = []
    for pat in PLAY_PAT:
        for m in re.finditer(pat, t_raw, flags=re.I):
            name = m.group(1).strip(" '\"“”«»")
            k = norm(name)
            if not k or len(k) > 40 or len(k.split()) > 4 or k in NOT_NAME or k in KINDS or any(k.startswith(w + " ") for w in ("my", "something", "some", "more", "a", "the next", "to")):
                continue
            if any(w in KINDS for w in k.split()) and len(k.split()) <= 2:
                continue
            if _has(k, PODCAST) or _has(k, SONGS) or detect_goal(k)[0] or any(_has(k, v) for v in SCAPES.values()) or _has(k, EVIDENCE):
                continue
            out.append(name)
    return out


# ------------------------------------------------------------------ replies
R: dict[str, dict[str, str]] = {
    "en": {"play": "Playing {a} now.", "only": "Only {a} from now on, until you say otherwise.", "insist": "You're right, you asked for {a}.",
           "now_rec": "{x} isn't one of your favourites: Qloo suggested them because people who love {b} also play them{c}.", "now_rec_nob": "{x} isn't one of your favourites: Qloo suggested them from your taste{c}.",
           "from_c": " (from {n})", "now_own": "That's {x}, one of your own favourites.", "now_pod": "This is {x}: {why}.", "now_none": "Nothing is playing yet.",
           "own_first": "From now on your own artists play first: {a}.", "only_own": "Only your own artists now: {a}.", "avoid": "Okay, no more {x}. On to the next one.", "avoid_none": "Okay, skipping this one.",
           "next": "Next one.", "pause": "Paused.", "resume": "Playing.", "src_podcast": "Here are podcasts picked for you. Choose one; Next moves to another show.",
           "src_podcast_q": "Podcasts about {q}. Choose one.", "src_scape": "Real {k} sound, no voices.", "src_bed": "Just the frequencies now, no songs.",
           "src_visual": "Switching to the visual session: follow the light.", "src_artists": "Back to songs, your own artists first.",
           "ev": "{summary} The strongest evidence is grade {g}: {claim} ({src}).", "ev_none": "I don't have a source for that, so I won't guess.",
           "why_session": "It's {p}, for {goal}. {summary} Evidence grade {g}: {claim}.", "compose": "On it.",
           "sr_open": "{name}here is a {min}-minute {p} session.", "sr_own": " It opens with your own {a}", "sr_pin": " It opens with {a}, as you asked", "sr_recs": ", then {b}: artists Qloo links to them{c}.",
           "sr_recsonly": " It plays {b}: artists Qloo links to your taste{c}.", "sr_plus": " Also {x}, for your love of {b}.", "sr_then": ", then {g}.", "sr_thenonly": " Qloo's picks: {g}.", "sr_g": "{b}, close to {f}", "sr_aside2": " I left out {x}: Qloo linked them, but their music is far from the artists you chose.", "sr_calmc": " {a} are lively, and lively music keeps you awake, so for {g} I am playing calm instrumental music instead. Say “my artists” to hear them anyway.", "sr_c": " from {n}", "sr_end": ".", "sr_aside": " I left out {x} ({n}): not your artists' musical world.",
           "sr_down": " It starts at your pace, {b0} beats a minute, and slowly winds down to {b1}.", "sr_up": " It starts at your pace, {b0} beats a minute, and lifts you to {b1}.",
           "sr_steady": " It holds a steady {b0} beats a minute.", "evA": " Music like this has strong evidence for {c}.", "evB": " There is good evidence for {c}.",
           "evC": " Evidence for {c} is still early, so treat it as a gentle help.", "sr_ask": " Want it softer, other artists, or a podcast instead?",
           "sr_feel": "you seem {m} right now. ", "sr_newp": "New plan: {p}.", "sr_done": "Done: {c}.", "sr_kept": "Your {p} session continues; it starts again from {a}.",
           "c_slower": "slower, winding down to {b} beats a minute", "c_faster": "faster, up to {b} beats a minute", "c_softer": "softer and quieter", "c_brighter": "brighter",
           "c_darker": "deeper", "c_novocals": "no vocals", "c_vocals": "with vocals", "c_shorter": "shorter, {m} minutes", "c_longer": "longer, {m} minutes", "c_newp": "a new plan: {p}",
           "c_pin": "starting with {a}", "and": " and ", "sr_group": " It's chosen so everyone in the room is held.",
           "sr_visual": "since you can't hear the music, I made it visual: a breathing light at six breaths a minute, your phone vibrating on the beat, and films and shows from your taste, starting from {fav}."},
    "es": {"play": "Ahora suena {a}.", "only": "Solo {a} a partir de ahora, hasta que digas otra cosa.", "insist": "Tienes razón, pediste {a}.",
           "now_rec": "{x} no es de tus favoritos: Qloo lo sugirió porque a quienes les gusta {b} también lo escuchan{c}.", "now_rec_nob": "{x} no es de tus favoritos: Qloo lo sugirió por tu gusto{c}.",
           "from_c": " (de {n})", "now_own": "Es {x}, uno de tus favoritos.", "now_pod": "Es {x}: {why}.", "now_none": "Aún no suena nada.",
           "own_first": "Desde ahora suenan primero tus artistas: {a}.", "only_own": "Solo tus artistas: {a}.", "avoid": "Vale, nada más de {x}. Pasamos a la siguiente.", "avoid_none": "Vale, salto esta.",
           "next": "La siguiente.", "pause": "En pausa.", "resume": "Sonando.", "src_podcast": "Aquí tienes pódcast elegidos para ti. Elige uno; Siguiente cambia de programa.",
           "src_podcast_q": "Pódcast sobre {q}. Elige uno.", "src_scape": "Sonido real de {k}, sin voces.", "src_bed": "Solo las frecuencias, sin canciones.",
           "src_visual": "Paso a la sesión visual: sigue la luz.", "src_artists": "Volvemos a las canciones, primero tus artistas.",
           "ev": "{summary} La mejor evidencia es de grado {g}: {claim} ({src}).", "ev_none": "No tengo una fuente para eso, así que no voy a adivinar.",
           "why_session": "Es {p}, para {goal}. {summary} Evidencia de grado {g}: {claim}.", "compose": "Voy.",
           "sr_open": "{name}aquí tienes una sesión de {min} minutos, {p}.", "sr_own": " Empieza con tus propios {a}", "sr_pin": " Empieza con {a}, como pediste", "sr_recs": ", y luego {b}: artistas que Qloo relaciona con ellos{c}.",
           "sr_recsonly": " Suenan {b}: artistas que Qloo relaciona con tu gusto{c}.", "sr_plus": " Y también {x}, por tu gusto por {b}.", "sr_then": ", y luego {g}.", "sr_thenonly": " Selección de Qloo: {g}.", "sr_g": "{b}, cerca de {f}", "sr_aside2": " Dejé fuera a {x}: Qloo los relacionó, pero su música está lejos de los artistas que elegiste.", "sr_calmc": " {a} son muy animados, y eso no ayuda a {g}, así que pongo música instrumental tranquila. Di “mis artistas” para oírlos igualmente.", "sr_c": " de {n}", "sr_end": ".", "sr_aside": " Dejé fuera a {x} ({n}): no es el mundo musical de tus artistas.",
           "sr_down": " Empieza a tu ritmo, {b0} pulsos por minuto, y baja poco a poco hasta {b1}.", "sr_up": " Empieza a tu ritmo, {b0} pulsos por minuto, y te sube hasta {b1}.",
           "sr_steady": " Se mantiene estable a {b0} pulsos por minuto.", "evA": " La música así tiene evidencia sólida para {c}.", "evB": " Hay buena evidencia para {c}.",
           "evC": " La evidencia para {c} aún es temprana: tómalo como una ayuda suave.", "sr_ask": " ¿La quieres más suave, con otros artistas o un pódcast?",
           "sr_feel": "ahora pareces {m}. ", "sr_newp": "Plan nuevo: {p}.", "sr_done": "Hecho: {c}.", "sr_kept": "Tu sesión {p} sigue; vuelve a empezar con {a}.",
           "c_slower": "más lenta, baja hasta {b} pulsos por minuto", "c_faster": "más rápida, sube a {b} pulsos por minuto", "c_softer": "más suave y bajita", "c_brighter": "más brillante",
           "c_darker": "más profunda", "c_novocals": "sin voces", "c_vocals": "con voces", "c_shorter": "más corta, {m} minutos", "c_longer": "más larga, {m} minutos", "c_newp": "un plan nuevo: {p}",
           "c_pin": "empezando con {a}", "and": " y ", "sr_group": " Está elegida para que nadie en la sala se quede fuera.",
           "sr_visual": "como no oyes la música, la hice visual: una luz que respira a seis respiraciones por minuto, el teléfono vibrando con el pulso, y películas y series de tu gusto, empezando por {fav}."},
    "fa": {"play": "حالا {a} پخش می‌شود.", "only": "از این به بعد فقط {a}، تا وقتی که چیز دیگری بگویی.", "insist": "حق با توست، {a} را خواسته بودی.",
           "now_rec": "{x} جزو علاقه‌مندی‌هایت نیست: Qloo پیشنهادش داد چون کسانی که {b} را دوست دارند او را هم گوش می‌دهند{c}.", "now_rec_nob": "{x} جزو علاقه‌مندی‌هایت نیست: Qloo از روی سلیقه‌ات پیشنهادش داد{c}.",
           "from_c": " (از {n})", "now_own": "این {x} است، یکی از علاقه‌مندی‌های خودت.", "now_pod": "این {x} است: {why}.", "now_none": "هنوز چیزی پخش نمی‌شود.",
           "own_first": "از این به بعد اول هنرمندان خودت پخش می‌شوند: {a}.", "only_own": "حالا فقط هنرمندان خودت: {a}.", "avoid": "باشه، دیگر {x} نه. می‌رویم سراغ بعدی.", "avoid_none": "باشه، این را رد می‌کنم.",
           "next": "بعدی.", "pause": "مکث.", "resume": "پخش.", "src_podcast": "این‌ها پادکست‌هایی است که برایت انتخاب شده. یکی را انتخاب کن؛ «بعدی» برنامهٔ دیگری می‌آورد.",
           "src_podcast_q": "پادکست‌هایی دربارهٔ {q}. یکی را انتخاب کن.", "src_scape": "صدای واقعی {k}، بدون صدای انسان.", "src_bed": "حالا فقط فرکانس‌ها، بدون آهنگ.",
           "src_visual": "می‌رویم سراغ جلسهٔ دیداری: نور را دنبال کن.", "src_artists": "برگشتیم به آهنگ‌ها، اول هنرمندان خودت.",
           "ev": "{summary} قوی‌ترین شاهد درجهٔ {g} است: {claim} ({src}).", "ev_none": "برای این منبعی ندارم، پس حدس نمی‌زنم.",
           "why_session": "این {p} است، برای {goal}. {summary} شواهد درجهٔ {g}: {claim}.", "compose": "چشم.",
           "sr_open": "{name}یک جلسهٔ {min} دقیقه‌ای ({p}) برایت آماده است.", "sr_own": " با هنرمندان خودت شروع می‌شود: {a}", "sr_pin": " همان‌طور که خواستی با {a} شروع می‌شود", "sr_recs": "، بعد {b}: هنرمندانی که Qloo به آن‌ها وصل می‌کند{c}.",
           "sr_recsonly": " {b} پخش می‌شوند: هنرمندانی که Qloo به سلیقه‌ات وصل می‌کند{c}.", "sr_plus": " و همچنین {x}، به خاطر علاقه‌ات به {b}.", "sr_then": "، بعد {g}.", "sr_thenonly": " پیشنهادهای Qloo: {g}.", "sr_g": "{b}، نزدیک به {f}", "sr_aside2": " {x} را کنار گذاشتم: Qloo آن‌ها را مرتبط دانست، اما موسیقی‌شان از هنرمندانی که انتخاب کردی دور است.", "sr_calmc": " {a} پرانرژی‌اند و برای {g} کمکی نمی‌کنند، پس موسیقی بی‌کلام و آرام پخش می‌کنم. اگر باز هم آن‌ها را می‌خواهی بگو «خواننده‌های خودم».", "sr_c": " از {n}", "sr_end": ".", "sr_aside": " {x} ({n}) را کنار گذاشتم: از دنیای موسیقی هنرمندانت نیست.",
           "sr_down": " با ریتم خودت شروع می‌شود، {b0} ضرب در دقیقه، و آرام‌آرام تا {b1} پایین می‌آید.", "sr_up": " با ریتم خودت شروع می‌شود، {b0} ضرب در دقیقه، و تا {b1} بالا می‌بردت.",
           "sr_steady": " روی {b0} ضرب در دقیقه ثابت می‌ماند.", "evA": " برای {c} شواهد محکمی وجود دارد.", "evB": " برای {c} شواهد خوبی هست.",
           "evC": " شواهد برای {c} هنوز اولیه است؛ آن را یک کمک ملایم بدان.", "sr_ask": " نرم‌ترش کنم، هنرمندان دیگر، یا یک پادکست؟",
           "sr_feel": "الان به نظر {m} می‌آیی. ", "sr_newp": "برنامهٔ تازه: {p}.", "sr_done": "انجام شد: {c}.", "sr_kept": "جلسهٔ {p} ادامه دارد؛ دوباره از {a} شروع می‌شود.",
           "c_slower": "آهسته‌تر، تا {b} ضرب در دقیقه", "c_faster": "تندتر، تا {b} ضرب در دقیقه", "c_softer": "نرم‌تر و آرام‌تر", "c_brighter": "روشن‌تر",
           "c_darker": "عمیق‌تر", "c_novocals": "بدون خواننده", "c_vocals": "با خواننده", "c_shorter": "کوتاه‌تر، {m} دقیقه", "c_longer": "بلندتر، {m} دقیقه", "c_newp": "برنامهٔ تازه: {p}",
           "c_pin": "شروع با {a}", "and": " و ", "sr_group": " طوری انتخاب شده که هیچ‌کس در اتاق جا نماند.",
           "sr_visual": "چون موسیقی را نمی‌شنوی، دیداری‌اش کردم: نوری که با شش نفس در دقیقه نفس می‌کشد، لرزش گوشی با ضرب، و فیلم‌ها و سریال‌هایی از سلیقه‌ات، از {fav} شروع."},
    "zh": {"play": "现在播放 {a}。", "only": "从现在起只放 {a}，直到你另有吩咐。", "insist": "你说得对，你要的是 {a}。",
           "now_rec": "{x} 不在你的最爱里：Qloo 推荐它，是因为喜欢 {b} 的人也听它{c}。", "now_rec_nob": "{x} 不在你的最爱里：Qloo 根据你的品味推荐了它{c}。",
           "from_c": "（来自{n}）", "now_own": "这是 {x}，你自己的最爱之一。", "now_pod": "这是 {x}：{why}。", "now_none": "还没有在播放。",
           "own_first": "从现在起先放你自己的艺术家：{a}。", "only_own": "现在只放你自己的艺术家：{a}。", "avoid": "好的，不再放 {x}。下一首。", "avoid_none": "好的，跳过这首。",
           "next": "下一首。", "pause": "已暂停。", "resume": "播放中。", "src_podcast": "这些是为你挑选的播客。选一个；“下一首”会换一个节目。",
           "src_podcast_q": "关于{q}的播客。选一个。", "src_scape": "真实的{k}声，无人声。", "src_bed": "现在只有频率，没有歌曲。",
           "src_visual": "切换到视觉疗程：跟随光。", "src_artists": "回到歌曲，先放你自己的艺术家。",
           "ev": "{summary}最有力的证据为 {g} 级：{claim}（{src}）。", "ev_none": "这一点我没有来源，所以不猜。",
           "why_session": "这是「{p}」，用于{goal}。{summary}证据等级 {g}：{claim}。", "compose": "好的。",
           "sr_open": "{name}这是一段 {min} 分钟的「{p}」疗程。", "sr_own": "先放你自己的 {a}", "sr_pin": "按你的要求，先放 {a}", "sr_recs": "，然后是 {b}：Qloo 关联到他们的艺术家{c}。",
           "sr_recsonly": "播放 {b}：Qloo 根据你的品味关联的艺术家{c}。", "sr_plus": "还有 {x}，因为你喜欢 {b}。", "sr_then": "，然后是{g}。", "sr_thenonly": "Qloo 的推荐：{g}。", "sr_g": "{b}（接近 {f}）", "sr_aside2": "我去掉了 {x}：Qloo 关联了他们，但他们的音乐与你选的艺术家相距较远。", "sr_calmc": "{a} 节奏很强，对{g}没有帮助，所以我改放平静的纯音乐。想听他们，就说“我的歌手”。", "sr_c": "，来自{n}", "sr_end": "。", "sr_aside": "我去掉了 {x}（{n}）：不属于你的艺术家的音乐世界。",
           "sr_down": "从你的节奏开始，每分钟 {b0} 拍，慢慢降到 {b1}。", "sr_up": "从你的节奏开始，每分钟 {b0} 拍，把你带到 {b1}。",
           "sr_steady": "保持每分钟 {b0} 拍。", "evA": "这类音乐对{c}有充分证据。", "evB": "对{c}有不错的证据。",
           "evC": "对{c}的证据还在早期，把它当作温和的帮助。", "sr_ask": "要更柔和、换些艺术家，还是听播客？",
           "sr_feel": "你现在看起来{m}。", "sr_newp": "新的方案：「{p}」。", "sr_done": "好了：{c}。", "sr_kept": "你的「{p}」疗程继续；重新从 {a} 开始。",
           "c_slower": "更慢，降到每分钟 {b} 拍", "c_faster": "更快，升到每分钟 {b} 拍", "c_softer": "更柔和、更安静", "c_brighter": "更明亮",
           "c_darker": "更深沉", "c_novocals": "不要人声", "c_vocals": "带人声", "c_shorter": "更短，{m} 分钟", "c_longer": "更长，{m} 分钟", "c_newp": "新的方案：{p}",
           "c_pin": "先放 {a}", "and": "和", "sr_group": "它的选择让房间里每个人都被照顾到。",
           "sr_visual": "因为你听不到音乐，我把它做成了视觉的：每分钟六次呼吸的光、手机随节拍振动，以及从你的品味出发的影片和剧集，从 {fav} 开始。"},
}
SCAPE_WORD = {"en": {"rain": "rain", "fire": "fire", "ocean": "ocean", "thunder": "thunderstorm", "forest": "forest", "river": "river", "waterfall": "waterfall", "wind": "wind", "night": "night", "bowls": "singing bowl", "whale": "whale"},
              "es": {"rain": "lluvia", "fire": "fuego", "ocean": "mar", "thunder": "tormenta", "forest": "bosque", "river": "río", "waterfall": "cascada", "wind": "viento", "night": "noche", "bowls": "cuenco", "whale": "ballena"},
              "fa": {"rain": "باران", "fire": "آتش", "ocean": "دریا", "thunder": "رعد و برق", "forest": "جنگل", "river": "رود", "waterfall": "آبشار", "wind": "باد", "night": "شب", "bowls": "کاسهٔ تبتی", "whale": "نهنگ"},
              "zh": {"rain": "雨", "fire": "篝火", "ocean": "海浪", "thunder": "雷雨", "forest": "森林", "river": "河流", "waterfall": "瀑布", "wind": "风", "night": "夜晚", "bowls": "颂钵", "whale": "鲸"}}


def _S(lang: str) -> dict[str, str]:
    return R.get(lang if lang in R else "en")


def _names(xs: list[str], lang: str) -> str:
    xs = [x for x in xs if x]
    if not xs:
        return ""
    if len(xs) == 1:
        return xs[0]
    sep = "، " if lang == "fa" else "、" if lang == "zh" else ", "
    return sep.join(xs[:-1]) + _S(lang)["and"] + xs[-1]


def cult(code: str | None, lang: str = "en") -> str:
    """A country as a token the browser names in the reader's language (Intl.DisplayNames): ⟦cc:IR⟧ -> Iran,
    ایران, Irán, 伊朗. No table of country names lives here."""
    code = (code or "").strip()
    return f"⟦cc:{code}⟧" if re.fullmatch(r"[A-Z]{2}", code) else code


def _about_now(now: dict[str, Any] | None, lang: str) -> str:
    S = _S(lang)
    if not now or not now.get("artist"):
        return S["now_none"]
    x = now["artist"]
    if now.get("kind") == "podcast":
        return S["now_pod"].format(x=x, why=now.get("because") or "")
    if now.get("own"):
        return S["now_own"].format(x=x)
    c = S["from_c"].format(n=cult(now["culture"], lang)) if now.get("culture") else ""
    return (S["now_rec"].format(x=x, b=now["because"], c=c) if now.get("because") else S["now_rec_nob"].format(x=x, c=c))


def _evidence_answer(text: str, ctx: dict[str, Any], lang: str) -> tuple[str, list[dict[str, Any]]]:
    S = _S(lang); p = ctx.get("protocol") or {}
    passages = [x for x in retrieve(text, 3) if x["score"] >= 0.12][:2]
    ev = (p.get("evidence") or [{}])[0] if p else {}
    if passages and passages[0]["score"] >= 0.2:
        top = passages[0]
        return f"{top['title']}. {top['text']} ({top['source']})", passages
    if p and ev:
        return S["ev"].format(summary=p.get("summary", ""), g=ev.get("grade", "?"), claim=ev.get("claim", ""), src=ev.get("source", "")), passages
    if passages:
        top = passages[0]
        return f"{top['title']}. {top['text']} ({top['source']})", passages
    return S["ev_none"], []


# ------------------------------------------------------------------ rules
def rules(text: str, ctx: dict[str, Any]) -> dict[str, Any]:
    lang = ctx.get("lang", "en"); S = _S(lang)
    raw = (text or "").strip(); t = norm(raw)
    favs = [f for f in (ctx.get("favourites") or []) if isinstance(f, str)]
    carrier = [c for c in (ctx.get("carrier") or []) if isinstance(c, str)]
    now = ctx.get("now") or {}
    known = favs + [c for c in carrier if c not in favs] + ([now["artist"]] if now.get("artist") and now.get("kind") != "podcast" else [])
    out: dict[str, Any] = {"act": "compose", "artists": [], "only": False, "src": None, "topic": None, "goal": None, "kind": "compose", "reply": "", "by": "rules"}
    if not t:
        return out
    cjk = bool(CJK.search(t))
    words = t.split()
    nwords = max(len(words), len(CJK.findall(t)) // 2) if cjk else len(words)
    is_q = _has(t, WHY)
    asks_why = _has(t, ("why", "how come", "por qué", "por que", "چرا", "为什么", "为何"))
    aliases = ctx.get("aliases") or {}
    found = mentions(t, known, aliases)
    # 1. transport (never when an artist is named: "skip Googoosh" and "stop playing Kalben" are about Googoosh and Kalben)
    if not found and nwords <= 3 and _has(t, NEXT) and not _has(t, PODCAST):
        return {**out, "act": "next", "kind": "control", "reply": S["next"]}
    if not found and nwords <= 3 and _has(t, PAUSE):
        return {**out, "act": "pause", "kind": "control", "reply": S["pause"]}
    if t.strip(" .!") in {norm(w) for w in RESUME} | {"play it", "play again", "keep playing", "go"}:
        return {**out, "act": "resume", "kind": "control", "reply": S["resume"]}
    only = _has(t, ONLY)
    # "more like X": similar artists, a job for the council
    if re.search(r"\b(more like|something like|similar to)\b|más como|mas como|بیشتر شبیه|像.+一样", t):
        return {**out, "act": "compose", "kind": "need", "reply": ""}
    # 2. "my own artists" / "only my favourites"
    if _has(t, OWN) and favs:
        return {**out, "act": "play", "artists": favs, "only": only, "kind": "own",
                "reply": S["only_own" if only else "own_first"].format(a=_names(favs, lang))}
    # 3. a named artist. A name right after a negation is unwanted ("not Kalben", "I don't want Kalben", "بدون
    # داریوش", "هایده نه", "不要周杰倫"); a "why" about a missing artist ("why is there no Dariush?") wants it.
    unwanted = [] if asks_why else [n for n, st, en in found if _negated(t, st, en)]
    named = [n for n, _, _ in found if n not in unwanted]
    if not found:
        named = [n for n in _captured(raw) if norm(n) not in {norm(x) for x in known}][:2]
        named = [n if re.search(r"[A-Z\u0600-\u06FF\u4e00-\u9fff]", n) else n.title() for n in named]
    if unwanted and not named:
        return {**out, "act": "avoid", "artists": unwanted, "kind": "avoid", "reply": S["avoid"].format(x=_names(unwanted, lang))}
    if named:
        insisted = _has(t, ("i said", "i asked", "i told you", "i meant", "i wanted", "dije", "te dije", "گفتم", "گفته بودم", "我说了", "我说"))
        r = (S["insist"].format(a=_names(named, lang)) + " ") if (insisted or is_q) else ""
        if is_q and now.get("artist") and norm(now["artist"]) not in {norm(n) for n in named}:
            r += _about_now(now, lang) + " "
        r += (S["only"] if only else S["play"]).format(a=_names(named, lang))
        if (insisted or is_q) and favs and not only:
            r += " " + S["own_first"].format(a=_names(favs, lang))
        return {**out, "act": "play", "artists": named, "only": only, "kind": "artist", "reply": r.strip(), "avoid": unwanted}
    # 4. "why another singer?"
    if _has(t, OTHER_SINGER) and favs:
        return {**out, "act": "play", "artists": favs, "only": False, "kind": "own", "reply": (_about_now(now, lang) + " " + S["own_first"].format(a=_names(favs, lang))).strip()}
    # 5. not this
    if _has(t, COMPLAINT) and not is_q:
        if now.get("artist"):
            return {**out, "act": "avoid", "artists": [now["artist"]], "kind": "avoid", "reply": S["avoid"].format(x=now["artist"]) if now.get("kind") != "podcast" else S["avoid_none"]}
        return {**out, "act": "next", "kind": "avoid", "reply": S["avoid_none"]}
    # 6. sources
    if _has(t, PODCAST):
        m = re.search(r"(?:about|on|sobre|de|درباره|دربارهٔ|关于)\s+(.+?)(?=[,.!?؟]|$)", raw, flags=re.I)
        q = m.group(1).strip() if m else None
        return {**out, "act": "source", "src": "podcast", "topic": q, "kind": "source", "reply": S["src_podcast_q"].format(q=q) if q else S["src_podcast"]}
    if _has(t, BED):
        return {**out, "act": "source", "src": "bed", "kind": "source", "reply": S["src_bed"]}
    kind = next((k for k, ws in SCAPES.items() if _has(t, ws)), None)
    if kind and (_has(t, SCAPE_HINT) or (nwords <= 3 and not cjk)):
        return {**out, "act": "source", "src": "scape", "topic": kind, "kind": "source", "reply": S["src_scape"].format(k=SCAPE_WORD.get(lang, SCAPE_WORD["en"]).get(kind, kind))}
    if _has(t, VISUAL) and not is_q:
        return {**out, "act": "source", "src": "visual", "kind": "source", "reply": S["src_visual"]}
    # 7. questions
    if is_q and (_has(t, SESSION_WHY) or t in ("why", "why?", "why this", "why this?", "por que", "¿por que?", "چرا", "چرا؟", "为什么", "为什么？")):
        p = ctx.get("protocol") or {}
        ev = (p.get("evidence") or [{}])[0]
        if p:
            goal = GOAL_WORDS.get(lang, GOAL_WORDS["en"]).get(ctx.get("goal") or p.get("goal") or "", ctx.get("goal") or "")
            return {**out, "act": "answer", "kind": "session", "reply": S["why_session"].format(p=p.get("name", ""), goal=goal, summary=p.get("summary", ""), g=ev.get("grade", "?"), claim=ev.get("claim", ""))}
    if is_q and _has(t, EVIDENCE):
        reply, passages = _evidence_answer(raw, ctx, lang)
        return {**out, "act": "answer", "kind": "evidence", "reply": reply, "passages": passages}
    if asks_why and now.get("artist") and not now.get("own") and now.get("kind") != "podcast" and favs and not _has(t, EVIDENCE):
        return {**out, "act": "play", "artists": favs, "only": False, "kind": "own", "reply": (_about_now(now, lang) + " " + S["own_first"].format(a=_names(favs, lang))).strip()}
    if is_q and (now.get("artist") and _has(t, ("this", "that", "him", "her", "them", "singer", "artist", "song", "podcast", "playing", "esto", "este", "esta", "cantante", "این", "خواننده", "آهنگ", "这", "歌手", "歌"))):
        return {**out, "act": "answer", "kind": "now", "reply": _about_now(now, lang)}
    # 8. a need, a tweak: ask the council
    goal, gw = detect_goal(t)
    flags = [k for k, ws in INTENTS.items() if k not in ("why", "stop") and _has(t, ws)]
    if goal or flags or re.search(r"\b(more like|something like|different|other artists|new artists)\b", t):
        return {**out, "act": "compose", "goal": goal, "kind": "need", "reply": ""}
    if is_q:
        reply, passages = _evidence_answer(raw, ctx, lang)
        if passages:
            return {**out, "act": "answer", "kind": "evidence", "reply": reply, "passages": passages}
        if now.get("artist"):
            return {**out, "act": "answer", "kind": "now", "reply": _about_now(now, lang)}
    if _has(t, SONGS) and ctx.get("src") not in (None, "artists"):
        return {**out, "act": "source", "src": "artists", "kind": "source", "reply": S["src_artists"]}
    return out


# ------------------------------------------------------------------ the language model (optional)
ACTS = {"play", "avoid", "compose", "source", "answer", "next", "pause", "resume"}
SRCS = {"artists", "podcast", "scape", "bed", "visual"}
GOALS = {"sleep", "calm", "focus", "energy", "mood", "memory", "autism_calm"}
LANG_NAME = {"en": "English", "es": "Spanish", "fa": "Persian (Farsi)", "zh": "Simplified Chinese"}
_probe: dict[str, tuple[float, bool]] = {}


def _ollama_url() -> str:
    return os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def _ollama_up() -> bool:
    hit = _probe.get("ollama")
    if hit and time.time() - hit[0] < 120:
        return hit[1]
    ok = False
    try:
        with urllib.request.urlopen(_ollama_url() + "/api/tags", timeout=0.6) as r:
            ok = r.status == 200 and bool(json.loads(r.read().decode()).get("models"))     # running, with a model pulled
    except Exception:  # noqa: BLE001
        ok = False
    _probe["ollama"] = (time.time(), ok)
    return ok


def ollama_model() -> str:
    """The model to ask: OLLAMA_MODEL (default llama3.2) when it is installed under that name or a tag of it
    ("llama3.2:latest", "llama3.2:3b"), else the first installed llama, else the first installed model.
    Ollama answers 404 for a name that is not pulled, so the name must match what `ollama list` shows."""
    want = os.environ.get("OLLAMA_MODEL", "llama3.2")
    hit = _probe.get("ollama_model")
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    pick = want
    try:
        with urllib.request.urlopen(_ollama_url() + "/api/tags", timeout=1.5) as r:
            names = [m.get("name") or m.get("model") or "" for m in json.loads(r.read().decode()).get("models", [])]
        names = [n for n in names if n]
        if names and want not in names:
            pick = next((n for n in names if n.split(":")[0] == want.split(":")[0]), None) \
                or next((n for n in names if n.lower().startswith("llama")), None) or names[0]
    except Exception:  # noqa: BLE001
        pass
    _probe["ollama_model"] = (time.time(), pick)
    return pick


def providers() -> list[str]:
    if os.environ.get("REACH_LLM", "auto").lower() in ("off", "0", "false", "none"):
        return []
    order = [p.strip() for p in os.environ.get("REACH_LLM_ORDER", "ollama,anthropic,openai").split(",") if p.strip()]
    out = []
    for p in order:
        if p == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
            out.append(p)
        elif p == "openai" and os.environ.get("OPENAI_API_KEY"):
            out.append(p)
        elif p == "ollama" and _ollama_up():
            out.append(p)
    return out


def status() -> dict[str, Any]:
    ps = providers()
    return {"llm": (ps[0] + (":" + ollama_model() if ps[0] == "ollama" else "")) if ps else None, "available": ps}


def _post(url: str, body: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


SYSTEM = """You are the conversation agent of Reach, a music-medicine app. Reach plays the person's OWN favourite artists first, then artists that Qloo (a cultural taste graph) links to them, inside an evidence-graded session (a tempo path and a gentle pulse in a frequency band). You get the person's message and a JSON context: their favourites, what is playing now (artist, title, whether it is their own favourite, which favourite Qloo linked it to, its country), the session's protocol and evidence, and the sources Reach offers.
Return ONLY one JSON object, no prose around it:
{"act": "play"|"avoid"|"compose"|"source"|"answer"|"next"|"pause"|"resume",
 "artists": [artist names, spelled as in the context when they are there],
 "only": true|false,
 "src": "artists"|"podcast"|"scape"|"bed"|"visual"|null,
 "topic": "podcast topic or soundscape kind (rain, fire, ocean, thunder, forest, river, waterfall, wind, night, bowls, whale)" or null,
 "goal": "sleep"|"calm"|"focus"|"energy"|"mood"|"memory"|null,
 "reply": "a short, warm, honest answer in LANGUAGE, at most three sentences"}
How to decide:
- They name an artist they want, or insist ("I said X", "where is X", "why another singer, I said X"): act "play" with that artist; only=true if they say only/just. If they also ask why something else played, explain it from context.now in the reply.
- "Why another singer?" without a name: explain context.now honestly (it is a Qloo recommendation linked to one of their favourites) and act "play" with their favourites.
- They do not want what is playing: act "avoid" with that artist.
- Podcasts, nature sounds, only frequencies, something to watch, songs again: act "source".
- A feeling or a need (sleepy, anxious, need focus, a boost) or a change (slower, softer, no vocals, longer): act "compose" with the goal.
- A question about why the session or does it work / is it safe / what the Hz do: act "answer", using only context.protocol.
- next / skip, pause / stop, resume: those acts.
Never invent songs, studies, numbers or facts that are not in the context. Never claim to have done anything other than the act you return."""


def llm(text: str, ctx: dict[str, Any], provider: str) -> dict[str, Any] | None:
    lang = ctx.get("lang", "en")
    sys_p = SYSTEM.replace("LANGUAGE", LANG_NAME.get(lang, "English"))
    slim_ctx = {k: ctx.get(k) for k in ("favourites", "now", "carrier", "goal", "src", "lens", "set_aside")}
    p = ctx.get("protocol") or {}
    slim_ctx["protocol"] = {"name": p.get("name"), "goal": p.get("goal"), "summary": p.get("summary"), "evidence": [{k: e.get(k) for k in ("grade", "claim", "source")} for e in (p.get("evidence") or [])[:3]]}
    user = f"Context: {json.dumps(slim_ctx, ensure_ascii=False)}\nMessage: {text}"
    try:
        if provider == "ollama":
            d = _post(_ollama_url() + "/api/chat", {"model": ollama_model(), "stream": False, "format": "json", "options": {"temperature": 0.2},
                                                    "messages": [{"role": "system", "content": sys_p}, {"role": "user", "content": user}]}, {}, timeout=float(os.environ.get("OLLAMA_TIMEOUT", "20")))
            raw = (d.get("message") or {}).get("content", "")
        elif provider == "anthropic":
            d = _post("https://api.anthropic.com/v1/messages", {"model": os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5"), "max_tokens": 400, "temperature": 0.2, "system": sys_p,
                                                               "messages": [{"role": "user", "content": user}]},
                      {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"}, timeout=10)
            raw = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        elif provider == "openai":
            d = _post("https://api.openai.com/v1/chat/completions", {"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), "temperature": 0.2, "response_format": {"type": "json_object"},
                                                                    "messages": [{"role": "system", "content": sys_p}, {"role": "user", "content": user}]},
                      {"authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}, timeout=10)
            raw = d["choices"][0]["message"]["content"]
        else:
            return None
    except Exception:  # noqa: BLE001  any failure: the rules answer
        return None
    m = re.search(r"\{.*\}", raw or "", flags=re.S)
    if not m:
        return None
    try:
        j = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    act = str(j.get("act", "")).lower()
    if act == "only":
        act, j["only"] = "play", True
    if act not in ACTS:
        return None
    arts = [str(a).strip()[:60] for a in (j.get("artists") or []) if str(a).strip()][:4] if isinstance(j.get("artists"), list) else []
    src = j.get("src") if j.get("src") in SRCS else None
    goal = j.get("goal") if j.get("goal") in GOALS else None
    reply = str(j.get("reply") or "").strip()[:500]
    if act in ("play", "avoid") and not arts:
        return None
    if act == "source" and not src:
        return None
    return {"act": act, "artists": arts, "only": bool(j.get("only")), "src": src, "topic": (str(j["topic"])[:60] if j.get("topic") else None), "goal": goal, "reply": reply, "by": "llm:" + provider}


def turn(text: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """One message -> {act, artists, only, src, topic, goal, kind, reply, by, passages?}."""
    base = rules(text, ctx)
    for prov in providers():
        j = llm(text, ctx, prov)
        if not j:
            continue
        # the rules are certain about some things: a favourite named in the message, transport words
        if base["kind"] in ("control",) and j["act"] != base["act"]:
            break
        if base["kind"] in ("artist", "own"):
            if j["act"] != "play":
                break
            j = {**j, "artists": base["artists"], "only": base["only"]}     # the names the person said, as they said them
        if j.get("src") == "scape" and j.get("topic") not in SCAPES:
            j = {**j, "topic": next((k for k, ws in SCAPES.items() if _has(norm(j.get("topic") or ""), ws)), None) or "rain"}
        out = {**base, **j, "kind": base["kind"] if base["act"] == j["act"] else "llm"}
        if not out.get("reply"):
            out["reply"] = base["reply"]
        if j["act"] == "answer" and base.get("passages"):
            out["passages"] = base["passages"]
        return out
    return base


# ------------------------------------------------------------------ the session, in words
def session_reply(result: dict[str, Any], request: dict[str, Any]) -> str:
    """What Reach says when a session is ready: whose songs open it, which recommendations follow and from
    where, what was left out and why, the pace and the evidence. On a re-compose: what changed."""
    lang = request.get("lang", "en"); lang = lang if lang in R else "en"; S = _S(lang)
    s = result["session"]; L = result["listener"]; prof = result.get("profile") or {}
    own = [c["name"] for c in s["carrier"] if c.get("own")]
    pinned = [c["name"] for c in s["carrier"] if c.get("pinned")]
    lens0 = s.get("lens") or {}
    recs_all = [c for c in s["carrier"] if not c.get("own") and not c.get("pinned")]
    of = lens0.get("of") or {}
    fav_names = [f["name"] for f in prof.get("favorites", []) if f.get("type") == "artist"]
    def anchor(c):   # which of the person's own artists a pick belongs with: same culture, else Qloo's explanation
        b = (c.get("because") or [{}])[0].get("name")
        if b in fav_names and (not of.get(b) or not c.get("assigned") or of.get(b) == c.get("assigned")):
            return b
        mates = [n for n in fav_names if of.get(n) and of.get(n) == c.get("assigned")]
        return mates[0] if mates else (b if b in fav_names else None)
    groups: dict[str, list[str]] = {}
    loose: list[str] = []
    for c in recs_all[:8]:
        a_ = anchor(c)
        (groups.setdefault(a_, []) if a_ else loose).append(c["name"])
    # every one of the person's artists that has picks gets named, not only the biggest group
    gl = sorted(groups.items(), key=lambda kv: fav_names.index(kv[0]) if kv[0] in fav_names else 99)
    recs = [n for _, ns in gl for n in ns][:6] or loose[:3]
    b0, b1 = s["segments"][0]["bpm"], s["segments"][-1]["bpm"]
    name = (request.get("name") or prof.get("name") or "").strip()
    favs = [f["name"] for f in prof.get("favorites", [])[:3]]
    if s.get("entrainment") == "visual":
        return (f"{name}, " if name else "") + S["sr_visual"].format(fav=_names(favs, lang))
    prev = request.get("prev") if isinstance(request.get("prev"), dict) else None
    lead = pinned or own[:3]
    if prev and prev.get("protocol") == s["protocol_id"]:
        ch = []
        flags = set(s.get("applied_intents") or [])
        if b1 < (prev.get("bpm1") or b1) - 2 or "slower" in flags:
            ch.append(S["c_slower"].format(b=b1))
        if b1 > (prev.get("bpm1") or b1) + 2 or "faster" in flags:
            ch.append(S["c_faster"].format(b=b1))
        for f in ("softer", "brighter", "darker"):
            if f in flags:
                ch.append(S["c_" + f])
        if s.get("vocals") is False and prev.get("vocals") is not False:
            ch.append(S["c_novocals"])
        if s.get("vocals") is True and prev.get("vocals") is False:
            ch.append(S["c_vocals"])
        if s["duration_min"] < (prev.get("min") or s["duration_min"]):
            ch.append(S["c_shorter"].format(m=s["duration_min"]))
        if s["duration_min"] > (prev.get("min") or s["duration_min"]):
            ch.append(S["c_longer"].format(m=s["duration_min"]))
        if pinned:
            ch.append(S["c_pin"].format(a=_names(pinned, lang)))
        if ch:
            return S["sr_done"].format(c="; ".join(ch))
        return S["sr_kept"].format(p=s["protocol_name"], a=_names(lead[:2] or recs[:1], lang))
    sensed = any(k in (L.get("signals") or []) for k in ("face", "voice")) or bool(request.get("override"))
    head = (f"{name}, " if name else "") + (S["sr_feel"].format(m=mood_word(L["mood"], lang)) if sensed else "")
    txt = head + S["sr_open"].format(name="", min=s["duration_min"], p=s["protocol_name"])
    if prev and prev.get("protocol") and prev.get("protocol") != s["protocol_id"]:
        txt = S["sr_newp"].format(p=s["protocol_name"])
    if s.get("only") and pinned:
        gl, loose = [], []
    parts = [S["sr_g"].format(b=_names(ns[:3], lang), f=f) for f, ns in gl[:3]]
    if loose and len(parts) < 3:
        parts.append(_names(loose[:3], lang))
    sep = "؛ " if lang == "fa" else "；" if lang == "zh" else "; "
    if s.get("calm_carrier"):
        goal_w = GOAL_WORDS.get(lang, GOAL_WORDS["en"]).get(s["calm_carrier"].get("goal", ""), "")
        txt += S["sr_calmc"].format(g=goal_w, a=_names(own[:3], lang) or _names(favs, lang))
    elif lead:
        txt += (S["sr_pin"] if pinned else S["sr_own"]).format(a=_names(lead, lang))
        txt += S["sr_then"].format(g=sep.join(parts)) if parts else S["sr_end"]
    elif parts:
        txt += S["sr_thenonly"].format(g=sep.join(parts))
    aside = [a for a in (s.get("set_aside") or []) if a.get("why", "culture") == "culture"]
    if aside:
        txt += S["sr_aside2"].format(x=_names([a["name"] for a in aside[:3]], lang))
    if s.get("group"):
        txt += S["sr_group"]
    txt += S["sr_down"].format(b0=b0, b1=b1) if b1 < b0 - 3 else S["sr_up"].format(b0=b0, b1=b1) if b1 > b0 + 3 else S["sr_steady"].format(b0=b0)
    ev = (result.get("protocol", {}).get("evidence") or [{}])[0]
    if ev.get("claim") and lang == "en":                  # the evidence registry is written in English
        c = ev["claim"][0].lower() + ev["claim"][1:]
        txt += S["ev" + ev.get("grade", "C") if ev.get("grade") in ("A", "B") else "evC"].format(c=c)
    return txt + S["sr_ask"]
