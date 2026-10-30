"""Reach vs a plain chatbot vs a generic playlist, on the same people.

    python scripts/bench.py                 # live Qloo (QLOO_API_KEY), MusicBrainz, Deezer/iTunes; LLM if one is set up
    python scripts/bench.py --quick         # 4 people instead of 10

Three systems answer the same ten people (different cultures, goals, and a "lively favourites, needs
sleep" case):
  generic   the same calm/sleep/focus list any app hands everyone (reach/compare.py GENERIC)
  llm       a language model asked directly for 8 "Artist - Song" picks (Ollama llama3.2 locally, else
            Anthropic/OpenAI if a key is set; skipped when none is available)
  reach     the full council (Qloo candidates -> cultural ranking -> evidence-graded session)

Measured, per person, on the artists each system picks that are NOT the person's own favourites:
  culture    share of picks from a culture (MusicBrainz main language or country) of the person's own artists
             (not measured when Reach plays calm instrumentals: they have no language)
  exists     share of picks that are real and playable: the song (or artist, for generic) is found in the
             Deezer/iTunes catalogue. A made-up song fails. Reach is scored on what it plays: like the app, it
             skips a Qloo pick with no song in the catalogue (the count is kept as not_playable_skipped).
  calm_safe  sleep/calm only: share of picks that are NOT high-energy (Qloo/Deezer genre: EDM, techno,
             trap, metal...). When Reach switches to calm instrumentals for lively favourites, that is what plays.
  personal   among people who asked for the same thing (three need sleep), 1 - the average overlap
             (Jaccard) of what the system gave them; a one-list-for-everyone system scores 0.
  taste      mean Qloo affinity of the picks inside the person's own top 50 (0 when absent). Note: Reach's
             candidates come from Qloo, so this one favours Reach by construction; it is shown, not hidden.

Writes data/bench_results.json (aggregate numbers only, no Qloo response data, safe to commit) and
data/bench_detail.local.json (the actual picks, git-ignored), and prints a table.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.app import _load_env_file  # noqa: E402  (loads .env / env without printing anything)
for f in (ROOT / ".env", ROOT / "env"):
    _load_env_file(f)

from reach.qloo import QlooClient, QlooError  # noqa: E402
from reach.agent import ReachCouncil  # noqa: E402
from reach.compare import GENERIC  # noqa: E402
from reach import culture, previews, dialogue, fullsong, sources  # noqa: E402

PEOPLE = [
    {"id": "b-persian", "label": "Persian classics, needs sleep", "goal": "sleep", "city": "Los Angeles", "favs": ["Hayedeh", "Googoosh", "Dariush"]},
    {"id": "b-mandarin", "label": "Mandopop, needs calm", "goal": "calm", "city": "San Francisco", "favs": ["Jay Chou", "Teresa Teng", "Faye Wong"]},
    {"id": "b-mixed", "label": "Shakira + Aznavour, mood lift", "goal": "mood", "city": "Miami", "favs": ["Shakira", "Charles Aznavour"]},
    {"id": "b-lively", "label": "Britney + Guetta + John Summit, needs sleep", "goal": "sleep", "city": "New York", "favs": ["Britney Spears", "David Guetta", "John Summit"]},
    {"id": "b-afro", "label": "Afrobeats, energy", "goal": "energy", "city": "London", "favs": ["Burna Boy", "Wizkid", "Asake"]},
    {"id": "b-korean", "label": "K-pop, focus", "goal": "focus", "city": "Seoul", "favs": ["IU", "BTS"]},
    {"id": "b-turkish", "label": "Turkish pop, memory", "goal": "memory", "city": "Berlin", "favs": ["Sezen Aksu", "Tarkan"]},
    {"id": "b-hindi", "label": "Bollywood, calm", "goal": "calm", "city": "Toronto", "favs": ["Arijit Singh", "Lata Mangeshkar"]},
    {"id": "b-mexican", "label": "Mexican, memory", "goal": "memory", "city": "Chicago", "favs": ["Vicente Fernández", "Natalia Lafourcade"]},
    {"id": "b-techno", "label": "Techno, needs sleep", "goal": "sleep", "city": "Berlin", "favs": ["Charlotte de Witte", "Amelie Lens"]},
]
ASK = {"sleep": "I can't sleep, help me fall asleep", "calm": "I'm anxious, help me calm down", "focus": "I need to focus on work", "energy": "I need energy",
       "mood": "I feel low, lift my mood", "memory": "play music that brings back memories"}
# whole words only: "electronic" or "ambient" is not high-energy, "electro house" and "techno" are
LIVELY = re.compile(r"\b(edm|electro house|big room|house|tech house|techno|trance|dubstep|drum and bass|drum & bass|hardstyle|heavy metal|metal|metalcore|hard rock|punk|trap|drill|hip hop|hip-hop|rap|reggaeton|dance pop|eurodance|dance)\b")


def nrm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return re.sub(r"[^\w]+", " ", "".join(c for c in s if not unicodedata.combining(c)).lower()).strip()


def llm_picks(person: dict) -> list[tuple[str, str]] | None:
    ps = dialogue.providers()
    if not ps:
        return None
    p = ps[0]
    prompt = (f"Someone who loves {', '.join(person['favs'])} asks: \"{ASK[person['goal']]}\". Recommend 8 songs by OTHER artists "
              f"(not {', '.join(person['favs'])}) for this. Answer ONLY as JSON: {{\"picks\": [{{\"artist\": \"...\", \"song\": \"...\"}}]}}")
    try:
        if p == "ollama":
            d = dialogue._post(dialogue._ollama_url() + "/api/chat", {"model": dialogue.ollama_model(), "stream": False, "format": "json", "options": {"temperature": 0.2},
                                                                     "messages": [{"role": "user", "content": prompt}]}, {}, timeout=90)
            raw = (d.get("message") or {}).get("content", "")
        elif p == "anthropic":
            d = dialogue._post("https://api.anthropic.com/v1/messages", {"model": os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5"), "max_tokens": 600, "temperature": 0.2,
                                                                          "messages": [{"role": "user", "content": prompt}]},
                               {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"}, timeout=40)
            raw = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        else:
            d = dialogue._post("https://api.openai.com/v1/chat/completions", {"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), "temperature": 0.2, "response_format": {"type": "json_object"},
                                                                             "messages": [{"role": "user", "content": prompt}]}, {"authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}, timeout=40)
            raw = d["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", raw or "", flags=re.S)
        j = json.loads(m.group(0)) if m else {}
        out = [(str(x.get("artist", "")).strip(), str(x.get("song", "")).strip()) for x in (j.get("picks") or []) if isinstance(x, dict) and x.get("artist")]
        return out[:8]
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "404" in msg and p == "ollama":
            msg += f" (Ollama has no model called '{dialogue.ollama_model()}'. Run: ollama pull llama3.2)"
        print("  llm failed:", msg[:200])
        return []


_exists: dict[tuple[str, str], bool] = {}


def song_exists(artist: str, song: str | None) -> bool:
    """The artist is in the catalogue and, when a song is named, that song is too, in any common spelling
    (reach/previews.py same_title: Gol-e Yakh = Gole Yakh). Same check for every system."""
    if not artist:
        return False
    k = (nrm(artist), nrm(song or ""))
    if k not in _exists:
        # previews() already makes sure the songs are this artist's (by name, or for a name in its own script,
        # 陳綺貞, by the one catalogue artist who owns the results, here "Cheer Chen"), so no second name check
        tracks = previews.previews(artist, 10)
        if not tracks:
            _exists[k] = False
        else:
            _exists[k] = True if not song else previews.find_track(artist, song) is not None
    return _exists[k]


def lively_of(client: QlooClient, artist: str) -> bool | None:
    """True when the artist's genres (Qloo search tags, else Deezer genre) are high-energy."""
    words: list[str] = []
    try:
        for r in client.search(artist, ["artist"], take=3):
            if nrm(r.get("name") or "") == nrm(artist):
                words += [str(t.get("name") or t.get("tag_id") or "").lower() for t in (r.get("tags") or [])]
                break
    except QlooError:
        pass
    if not words:
        return None
    return any(LIVELY.search(w.strip()) for w in words)


def main_lang(p: dict) -> str | None:
    """An artist's main release language (the one most of their releases are in), not every language they ever used."""
    langs = (p or {}).get("langs") or {}
    return max(langs, key=langs.get) if isinstance(langs, dict) and langs else None


def culture_keys(P: dict, names: list[str]) -> tuple[set, set]:
    ccs, langs = set(), set()
    for n in names:
        p = P.get(n) or {}
        if p.get("cc"):
            ccs.add(p["cc"])
        if main_lang(p):
            langs.add(main_lang(p))
    return ccs, langs


def score(client: QlooClient, person: dict, picks: list[tuple[str, str | None]], top50: dict, P: dict, mode: str, calm_switch: bool = False) -> dict:
    fav_cc, fav_lang = culture_keys(P, person["favs"])
    own = {nrm(f) for f in person["favs"]}
    picks = [(a, s) for a, s in picks if a and nrm(a) not in own]
    n = len(picks)
    if not n:
        return {"n": 0}
    known = match = 0
    for a, _ in picks:
        p = P.get(a) or {}
        cc, lg = p.get("cc"), main_lang(p)
        if cc or lg:
            known += 1
            if (cc and cc in fav_cc) or (lg and lg in fav_lang):
                match += 1
    exists = sum(1 for a, s in picks if song_exists(a, s))
    out = {"n": n, "culture": round(match / known, 3) if known else None, "culture_known": known, "exists": round(exists / n, 3)}
    if person["goal"] in ("sleep", "calm"):
        if calm_switch:
            out["calm_safe"] = 1.0; out["calm_note"] = "switched to calm instrumentals"
        else:
            lv = [lively_of(client, a) for a, _ in picks]
            k = [x for x in lv if x is not None]
            out["calm_safe"] = round(1 - sum(k) / len(k), 3) if k else None
    aff = []
    for a, _ in picks:
        aff.append(top50.get(nrm(a), 0.0))
    out["taste"] = round(sum(aff) / n, 3)
    return out


def mark(client: QlooClient, person: dict, artist: str, song: str | None, P: dict) -> str:
    """One pick as the bench saw it: name, song, where from, and what failed (shown so a run explains itself)."""
    fav_cc, fav_lang = culture_keys(P, person["favs"])
    if nrm(artist) in {nrm(f) for f in person["favs"]}:
        return f"{artist}{' - ' + song if song else ''} [their own favourite, not counted]"
    p = P.get(artist) or {}
    cc, lg = p.get("cc"), main_lang(p)
    where = f"{cc or '?'}/{lg or '?'}"
    flags = []
    if (cc or lg) and not ((cc and cc in fav_cc) or (lg and lg in fav_lang)):
        flags.append("other culture")
    if not song_exists(artist, song):
        flags.append("song not found")
    if person["goal"] in ("sleep", "calm") and lively_of(client, artist):
        flags.append("lively")
    return f"{artist}{' - ' + song if song else ''} [{where}{', ' + ', '.join(flags) if flags else ''}]"


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--quick", action="store_true"); args = ap.parse_args()
    client = QlooClient()
    if client.offline:
        print("This needs live Qloo: put QLOO_API_KEY in .env (or env) and run again."); sys.exit(1)
    council = ReachCouncil(client)
    people = PEOPLE[:4] if args.quick else PEOPLE
    llm_name = (dialogue.providers() or [None])[0]
    if llm_name == "ollama":
        llm_name = "ollama:" + dialogue.ollama_model()
    print("LLM baseline:", llm_name or "none (install Ollama or set ANTHROPIC_API_KEY / OPENAI_API_KEY to include it)")
    rows, detail = [], []
    for person in people:
        t0 = time.time(); print(f"\n{person['label']} ({person['goal']}, {person['city']})")
        favs = []
        for name in person["favs"]:
            r = client.resolve(name, "artist")
            favs.append({"name": name, "type": "artist", "entity_id": r["entity_id"] if r else None})
        prof = {"id": person["id"], "name": "Bench", "age": 35, "city": person["city"], "language": "en", "favorites": favs, "targets": [], "flags": [], "sensory": {},
                "capacities": {"hearing": "full", "vision": "full", "reading": "yes", "mobility": "ambulatory", "verbal": "yes"}, "consent": {"taste": True}}
        ids = [f["entity_id"] for f in favs if f["entity_id"]]
        top = client.insights("artist", entities=ids, take=50, label=f"{person['id']}.bench.top50") if ids else []
        top50 = {nrm(e.get("name") or ""): float((e.get("query") or {}).get("affinity") or 0) for e in top}
        # reach
        res = council.compose_once(prof, {"text": ASK[person["goal"]], "goal": person["goal"], "lang": "en"})
        ses = res.get("session") or {}
        # what the app plays: it asks the catalogue for each pick and plays only artists it found a song for
        reach_picks, dropped = [], 0
        for c in (ses.get("carrier") or [])[:12]:
            if len(reach_picks) >= 8:
                break
            tr = previews.previews(c["name"], 4)
            if tr:
                reach_picks.append((c["name"], tr[0].get("title")))
            else:
                dropped += 1
        calm_switch = bool(ses.get("calm_carrier"))
        played = None
        if calm_switch:
            # lively favourites at bedtime: the app does not play the carrier, it plays the most watched long calm
            # instrumental pieces (YouTube), or a rain / ocean recording without a key. Score what plays.
            vids = fullsong.calm_music(person["goal"]) if fullsong.enabled() else []
            played = [(v.get("title") or "calm instrumental", None) for v in vids] or \
                     [(t.get("title") or "rain recording", None) for t in sources.soundscape("rain" if person["goal"] == "sleep" else "ocean", 3)]
        gen = [(a, None) for a in GENERIC.get(person["goal"], GENERIC["calm"])]
        llm = llm_picks(person)
        names = person["favs"] + [a for a, _ in reach_picks + gen + (llm or [])]
        P = culture.profiles(names, budget_s=90.0, network=True)
        reach_score = score(client, person, reach_picks, top50, P, "reach", calm_switch) if not calm_switch else \
            {"n": len(played or []), "culture": None, "exists": 1.0 if played else None, "calm_safe": 1.0 if played else None, "taste": None,
             "calm_note": "lively favourites: plays calm instrumentals instead of songs"}
        r = {"id": person["id"], "label": person["label"], "goal": person["goal"], "reach": reach_score,
             "generic": score(client, person, gen, top50, P, "generic")}
        if llm is not None:
            r["llm"] = score(client, person, llm, top50, P, "llm")
        rows.append(r)
        r["reach"]["not_playable_skipped"] = dropped
        detail.append({"id": person["id"], "reach": played if calm_switch else reach_picks, "carrier_not_played": reach_picks if calm_switch else None,
                       "generic": gen, "llm": llm, "calm_switch": calm_switch})
        for k in ("reach", "llm", "generic"):
            if k in r:
                print(f"  {k:8s}", {m: r[k].get(m) for m in ("culture", "exists", "calm_safe", "taste")})
                if k == "reach" and calm_switch:
                    print("           plays calm instrumentals: " + "; ".join(t for t, _ in (played or [])[:5]))
                    print("           (Qloo's picks from their taste, not played tonight: " + ", ".join(a for a, _ in reach_picks[:8]) + ")")
                    continue
                picks = {"reach": reach_picks, "llm": llm or [], "generic": gen}[k]
                print("           " + "; ".join(mark(client, person, a, s_, P) for a, s_ in picks[:8]))
        print(f"  ({time.time() - t0:.0f}s)")
    # personalisation: how different each system's picks are across people
    def jacc(a, b):
        a, b = {nrm(x) for x, _ in a}, {nrm(x) for x, _ in b}
        return len(a & b) / len(a | b) if a | b else 0.0
    personal = {}
    goal_of = {p["id"]: p["goal"] for p in people}
    for k in ("reach", "generic", "llm"):
        lists = [(goal_of[d["id"]], d[k]) for d in detail if d.get(k)]
        # people who asked for the same thing (three need sleep): a personal system still answers each differently
        pairs = [(i, j) for i in range(len(lists)) for j in range(i + 1, len(lists)) if lists[i][0] == lists[j][0]]
        personal[k] = round(1 - sum(jacc(lists[i][1], lists[j][1]) for i, j in pairs) / len(pairs), 3) if pairs else None
    agg = {}
    for k in ("reach", "llm", "generic"):
        vals = [r[k] for r in rows if k in r and r[k].get("n")]
        if not vals:
            continue
        def mean(m):
            xs = [v[m] for v in vals if v.get(m) is not None]
            return round(sum(xs) / len(xs), 3) if xs else None
        agg[k] = {"culture": mean("culture"), "exists": mean("exists"), "calm_safe": mean("calm_safe"), "taste": mean("taste"), "personal": personal.get(k), "people": len(vals)}
    out = {"run_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "llm": llm_name, "people": len(rows), "systems": agg,
           "per_person": [{"label": r["label"], "goal": r["goal"], **{k: {m: r[k].get(m) for m in ("culture", "exists", "calm_safe", "taste", "calm_note", "not_playable_skipped") if r[k].get(m) is not None} for k in ("reach", "llm", "generic") if k in r}} for r in rows],
           "method": "scripts/bench.py docstring", "note": "aggregate numbers only; no Qloo response data"}
    (ROOT / "data" / "bench_results.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    (ROOT / "data" / "bench_detail.local.json").write_text(json.dumps(detail, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\n               culture  exists  calm_safe  personal  taste")
    for k, v in agg.items():
        f = lambda x: "  -  " if x is None else f"{x * 100:5.0f}%"
        print(f"  {k:10s}  {f(v['culture'])}  {f(v['exists'])}   {f(v['calm_safe'])}    {f(v['personal'])}   {v['taste'] if v['taste'] is not None else '-'}")
    print("\nwrote data/bench_results.json (safe to commit) and data/bench_detail.local.json (git-ignored)")


if __name__ == "__main__":
    main()
