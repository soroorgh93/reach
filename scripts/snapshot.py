"""Build a static preview in dist/: the web app plus recorded council runs, so the demo
runs with no server. Start the server on :8000 first, then: python3 scripts/snapshot.py"""
from __future__ import annotations

import json
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB, DIST = ROOT / "web", ROOT / "dist"
BASE = "http://127.0.0.1:8000"


def get(path: str, body: dict | None = None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None, headers={"content-type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def main() -> None:
    snap: dict = {"GET /api/personas": get("/api/personas"), "GET /api/protocols": get("/api/protocols"), "GET /api/health": get("/api/health"), "session": {}}
    goals = ["focus", "sleep", "calm", "autism_calm", "mood", "memory", "energy"]
    snap["GET /api/tour"] = get("/api/tour")
    snap["tour"] = {}
    for stop in snap["GET /api/tour"]["stops"]:
        try:
            snap["tour"][stop["city"]] = get(f"/api/tour?city={urllib.parse.quote(stop['city'])}")
        except Exception as e:  # noqa: BLE001
            print("tour", stop["city"], e)
    for p in snap["GET /api/personas"]["personas"]:
        for g in [None] + goals:
            req = {"text": p.get("sample_request", ""), "local_hour": p.get("sample_hour", 12), "lang": p.get("language", "en")}
            if g:
                req["goal"] = g
            r = get("/api/session", {"persona_id": p["id"], "request": req})
            snap["session"][f"{p['id']}:{g or ''}"] = r
            print("snapshot", p["id"], g, r.get("error") or r["session"]["protocol_id"])
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(WEB, DIST)
    (DIST / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    html = (DIST / "index.html").read_text(encoding="utf-8").replace('<script type="module" src="./app.js"></script>', '<script src="./shim.js"></script>\n<script type="module" src="./app.js"></script>')
    (DIST / "index.html").write_text(html, encoding="utf-8")
    (DIST / "shim.js").write_text(SHIM, encoding="utf-8")
    print("dist ready:", DIST)


SHIM = r"""// Static preview: answers /api/* from snapshot.json, replays the council trace from the ledger,
// verifies the hash chain in the browser and runs the ISO adaptation rule locally.
(function () {
  let snap = null; const ready = fetch("./snapshot.json").then(r => r.json()).then(j => (snap = j));
  const realFetch = window.fetch.bind(window);
  const sha = async (s) => { const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)); return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join(""); };
  const canon = (x) => typeof x === "number" ? (Number.isInteger(x) ? x : Math.round(x * 1e10) / 1e10) : Array.isArray(x) ? x.map(canon) : (x && typeof x === "object") ? Object.fromEntries(Object.keys(x).sort().map(k => [k, canon(x[k])])) : x;
  const stable = (o) => JSON.stringify(canon(o));
  const target = { sleep: 0.15, calm: 0.3, autism_calm: 0.3, mood: 0.45, focus: 0.6, memory: 0.45 };
  function adapt(session, mood, elapsed) {
    const a = +mood.arousal || 0.45, v = +mood.valence || 0, goal = session.goal; let seg = session.segments[0]; session.segments.forEach(s => { if (s.start_s <= elapsed) seg = s; });
    const out = { segment: seg.name, bpm_delta: 0, hz_delta: 0, depth_delta: 0, brightness_delta: 0, reason: "on course" }; const gap = a - (target[goal] ?? 0.4);
    if (["sleep", "calm", "autism_calm"].includes(goal) && gap > 0.2) Object.assign(out, { bpm_delta: -4, hz_delta: -0.5, brightness_delta: -0.08, reason: "arousal still high; slowing and darkening (ISO step down)" });
    else if (["sleep", "calm", "autism_calm"].includes(goal) && gap < -0.2) Object.assign(out, { depth_delta: -0.05, reason: "settled; pulse softened" });
    else if (goal === "focus" && gap < -0.2) Object.assign(out, { bpm_delta: 4, hz_delta: 1, brightness_delta: 0.08, reason: "energy low; lifting tempo and pulse" });
    else if (goal === "focus" && gap > 0.25) Object.assign(out, { bpm_delta: -3, hz_delta: -1, reason: "over-aroused for focus; easing pulse" });
    else if (goal === "mood" && v < -0.4) Object.assign(out, { brightness_delta: -0.05, bpm_delta: -2, reason: "staying with the person a little longer before brightening" });
    if (goal === "autism_calm") out.depth_delta = Math.min(out.depth_delta, 0); return out;
  }
  window.fetch = async function (url, opts) {
    const u = String(url); if (!u.startsWith("/api/")) return realFetch(url, opts);
    await ready; const body = opts && opts.body ? JSON.parse(opts.body) : {}; let out;
    if (u === "/api/personas" || u === "/api/protocols" || u === "/api/health") out = snap["GET " + u];
    else if (u === "/api/session") out = snap.session[`${body.persona_id}:${(body.request && body.request.goal) || ""}`] || snap.session[`${body.persona_id}:`];
    else if (u.startsWith("/api/preview")) out = { tracks: [] };
    else if (u.startsWith("/api/resolve") || u.startsWith("/api/suggest")) out = { results: [], mode: "fixture" };
    else if (u.startsWith("/api/soundscape") || u.startsWith("/api/podcast")) out = { tracks: [] };
    else if (u.startsWith("/api/watch")) out = { items: [] };
    else if (u.startsWith("/api/fullsong") || u.startsWith("/api/calmvideo") || u.startsWith("/api/trailer")) out = { id: null };
    else if (u.startsWith("/api/tour")) { const c = new URL(u, location.href).searchParams.get("city"); out = c ? (snap.tour && snap.tour[c]) || { stop: null, artists: [], tracks: [], source: "none" } : snap["GET /api/tour"]; }
    else if (u === "/api/compare") out = { ok: false, reason: "needs the hosted app (live Qloo)" };
    else if (u.startsWith("/api/ask")) out = { passages: [] };
    else if (u === "/api/adapt") out = adapt(body.session, body.mood || {}, +body.elapsed_s || 0);
    else if (u === "/api/verify") {
      let prev = "0".repeat(64); out = { ok: true, length: body.ledger.length, head: prev };
      for (const e of body.ledger) { if (e.prev !== prev) { out = { ok: false, at: e.i, reason: "prev hash mismatch" }; break; } const h = await sha(prev + stable({ i: e.i, t: e.t, kind: e.kind, payload: e.payload })); if (h !== e.hash) { out = { ok: false, at: e.i, reason: "entry hash mismatch" }; break; } prev = h; out.head = h; }
    } else out = { error: "not in snapshot" };
    return new Response(JSON.stringify(out), { status: out && out.error === "not in snapshot" ? 400 : 200, headers: { "content-type": "application/json" } });
  };
  class FakeES extends EventTarget {
    constructor(url) {
      super(); const q = new URL(url, location.href).searchParams; let goal = ""; try { goal = JSON.parse(q.get("req") || "{}").goal || ""; } catch {}
      let pid = q.get("persona"); if (!pid) { try { pid = JSON.parse(q.get("profile") || "{}").id; } catch {} }
      if (!pid || pid === "you") pid = Object.keys(snap.session)[0].split(":")[0];
      const key = `${pid}:${goal}`;
      ready.then(() => { const r = snap.session[key] || snap.session[`${pid}:`]; let i = 0; const tick = () => {
        if (this.closed) return;
        if (i < r.ledger.length) { const e = r.ledger[i++]; this.dispatchEvent(new MessageEvent(e.kind, { data: JSON.stringify({ kind: e.kind, i: e.i, hash: e.hash.slice(0, 12), t: e.t, ...e.payload }) })); setTimeout(tick, 110); }
        else { this.dispatchEvent(new MessageEvent("result", { data: JSON.stringify({ result: r }) })); this.dispatchEvent(new MessageEvent("done", { data: "{}" })); }
      }; setTimeout(tick, 150); });
    }
    close() { this.closed = true; }
  }
  window.EventSource = FakeES;
})();
"""

if __name__ == "__main__":
    main()
