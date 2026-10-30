// Guided tour: a narrated walkthrough of Reach that plays like a video. Each chapter points at
// one part of the interface (a spotlight cut out of a dimmed mask) with its caption, narrated
// by a recorded neural voice (Kokoro, scripts/make_voice.py, assets/guide/<lang>/nNN.mp3).
// One play/pause button and one blue timeline across the whole tour, with chapter marks:
// click or drag anywhere on it to jump, like scrubbing a film. Keyboard: space, ←, →, Esc.
// A language without recordings shows captions and advances at reading pace.
// Render mode (?tour=1&render=1) hands control to scripts/make_guide_video.py.

const GAP = 0.7;   // seconds of silence between chapters

export class Guide {
  // hooks: { steps(lang) -> [{t, s}], lang() -> code, targets: [fn -> {el, media}], media: {chapter: film}, order: [chapter index per position], onOpen, onClose }
  // A chapter keeps its narration (nNN.mp3) and its target wherever `order` places it.
  constructor(root, hooks) {
    this.root = root; this.hooks = hooks; this.i = -1; this.open = false; this.playing = false; this.voice = true; this.render = false;
    this.audio = null; this.stepT0 = 0; this.offset = 0; this.seq = 0;
    this.spot = root.querySelector(".guide-spot"); this.card = root.querySelector(".guide-card");
    this.bar = root.querySelector("#guide-bar"); this.fill = root.querySelector("#guide-fill"); this.knob = root.querySelector("#guide-knob"); this.clock = root.querySelector("#guide-time");
    root.querySelector("#guide-play").addEventListener("click", () => this.toggle());
    root.querySelector("#guide-close").addEventListener("click", () => this.close());
    root.querySelector("#guide-voice").addEventListener("change", (e) => { this.voice = e.target.checked; if (this.audio) this.audio.muted = !this.voice; });
    root.addEventListener("click", (e) => { if (e.target === root.querySelector(".guide-mask")) this.close(); });
    // scrubbing
    let drag = false;
    const at = (e) => { const r = this.bar.getBoundingClientRect(); const x = (e.touches ? e.touches[0].clientX : e.clientX) - r.left; return Math.min(1, Math.max(0, x / r.width)) * this.total(); };
    const preview = (t) => { this._paint(t); };
    this.bar.addEventListener("pointerdown", (e) => { drag = true; this.bar.setPointerCapture(e.pointerId); preview(at(e)); });
    this.bar.addEventListener("pointermove", (e) => { if (drag) preview(at(e)); else this._hover(at(e)); });
    this.bar.addEventListener("pointerup", (e) => { if (!drag) return; drag = false; this.seek(at(e)); });
    this.bar.addEventListener("pointerleave", () => { this.bar.title = ""; });
    window.addEventListener("keydown", (e) => {
      if (!this.open) return;
      if (e.key === "Escape") this.close();
      else if (e.key === " ") { e.preventDefault(); this.toggle(); }
      else if (e.key === "ArrowRight") this.goto(Math.min(this.steps.length - 1, this.i + 1));
      else if (e.key === "ArrowLeft") this.goto(Math.max(0, this.i - 1));
    });
    window.addEventListener("resize", () => { if (this.open) this._place(); });
    this._tick = () => { if (!this.open) return; this._place(); this._paint(this.now()); requestAnimationFrame(this._tick); };
    this.manifest = {}; this.ready = fetch("./assets/guide/manifest.json").then(r => r.json()).then(m => { this.manifest = m; }).catch(() => {});
  }
  _all() { return this.hooks.steps(this.hooks.lang()) || []; }
  _order(n) { const o = this.hooks.order; return o && o.length === n ? o : null; }   // used only when it covers every chapter of this language
  get steps() { const all = this._all(), o = this._order(all.length); return o ? o.map(k => all[k]) : all; }
  ord(i) { const o = this._order(this._all().length); return o ? o[i] : i; }
  key(i) { return `n${String(this.ord(i)).padStart(2, "0")}`; }
  // chapter lengths in seconds: the recording, or reading time when there is none
  dur(i) { const m = this.manifest[this.hooks.lang()]; const k = this.key(i); if (m && m[k]) return m[k] + GAP; const s = this.steps[i] ? this.steps[i].s : ""; const units = /[一-鿿]/.test(s) ? s.length / 2.2 : s.split(/\s+/).length; return Math.max(3, units * 0.33 + 1.2); }
  starts() { const out = []; let t = 0; for (let i = 0; i < this.steps.length; i++) { out.push(t); t += this.dur(i); } return out; }
  total() { return this.steps.reduce((a, _, i) => a + this.dur(i), 0); }
  now() { const base = this.starts()[Math.max(0, this.i)] || 0; const inside = this.audio ? this.audio.currentTime : this.playing ? (performance.now() - this.stepT0) / 1000 + this.offset : this.offset; return Math.min(this.total(), base + Math.min(inside, this.dur(Math.max(0, this.i)))); }
  async start({ render = false, at = 0 } = {}) {
    await this.ready;
    this.render = render; this.open = true; this.root.hidden = false; this.root.classList.toggle("render", render);
    if (this.hooks.onOpen) this.hooks.onOpen();
    this._marks(); requestAnimationFrame(this._tick); this.playing = !render; this._setBtn(); this.goto(at);
  }
  close() { this._media(null); if (!this.open) return; this.open = false; this.seq++; this._stopAudio(); clearTimeout(this.timer); this.root.hidden = true; if (this.hooks.onClose) this.hooks.onClose(); }
  toggle() {
    this.playing = !this.playing; this._setBtn();
    if (this.playing) { if (this.audio) this.audio.play().catch(() => {}); else this._run(this.offset); }
    else { if (this.audio) { this.audio.pause(); this.offset = this.audio.currentTime; } else this.offset = (performance.now() - this.stepT0) / 1000 + this.offset; clearTimeout(this.timer); }
  }
  seek(t) {
    const st = this.starts(); let i = st.length - 1; while (i > 0 && st[i] > t) i--;
    this.goto(i, Math.max(0, t - st[i]));
  }
  async goto(i, offset = 0) {
    const steps = this.steps; if (i < 0) return; if (i >= steps.length) { this.close(); return; }
    const seq = ++this.seq; this._stopAudio(); clearTimeout(this.timer); this.i = i; this.offset = offset; const step = steps[i];
    this.root.querySelector("#guide-n").textContent = `${i + 1} / ${steps.length}`;
    this.root.querySelector("#guide-title").textContent = step.t; this.root.querySelector("#guide-text").textContent = step.s;
    const film = this.hooks.media ? this.hooks.media[this.ord(i)] : null; this.target = null; this._media(film);   // a chapter's film shows at once, before its screen is ready
    const fn = this.hooks.targets[this.ord(i)], tg = fn ? await fn() : null; if (seq !== this.seq) return;
    this.target = tg && tg.el ? tg.el : null; if (!film && tg && tg.media) this._media(tg.media);
    if (this.target) { this._reveal(this.target); await new Promise(r => setTimeout(r, 300)); if (seq !== this.seq) return; }
    this._place(); if (!this.render && this.playing) this._run(offset);
  }
  // play chapter i from `offset` seconds, then the next one
  _run(offset) {
    const seq = this.seq, lang = this.hooks.lang(), k = this.key(this.i), have = this.manifest[lang] && this.manifest[lang][k];
    this.stepT0 = performance.now(); this.offset = offset;
    const next = (ms) => { this.timer = setTimeout(() => { if (seq === this.seq && this.playing) this.goto(this.i + 1); }, ms); };
    if (!have) { next(Math.max(0, (this.dur(this.i) - offset) * 1000)); return; }
    const a = new Audio(`./assets/guide/${lang}/${k}.mp3`); a.muted = !this.voice; a.volume = 1; this.audio = a;
    const go = () => { try { a.currentTime = Math.min(offset, have - 0.05); } catch {} a.play().catch(() => { this.audio = null; next((this.dur(this.i) - offset) * 1000); }); };
    if (a.readyState >= 1) go(); else a.addEventListener("loadedmetadata", go, { once: true });
    a.onended = () => { if (seq === this.seq) { this.audio = null; this.offset = have; next(GAP * 1000); } };
    a.onerror = () => { if (seq === this.seq) { this.audio = null; next(Math.max(0, (this.dur(this.i) - offset) * 1000)); } };
  }
  // a step can bring a short film of the real thing (the hand and face demo): shown large, the card below it
  // media: a film's address, or { src, at } to start it at a moment (the same film runs on across chapters otherwise)
  _media(m) {
    const box = this.root.querySelector("#guide-media"); if (!box) return; const v = box.querySelector("video");
    const src = m && typeof m === "object" ? m.src : m, at = m && typeof m === "object" ? +m.at || 0 : null;
    this.media = src || null; this.root.classList.toggle("hasmedia", !!src);
    if (!src) { box.hidden = true; try { v.pause(); } catch {} return; }
    v.muted = true;                                       // the film is silent: only the narration speaks
    if (v.getAttribute("src") !== src) { v.src = src; v.poster = src.replace(/\.mp4(\?.*)?$/, ".jpg$1"); }
    if (at !== null) { const seek = () => { try { v.currentTime = at; } catch {} }; if (v.readyState >= 1) seek(); else v.addEventListener("loadedmetadata", seek, { once: true }); }
    box.hidden = false; v.play().catch(() => {});
  }
  _stopAudio() { if (this.audio) { try { this.audio.pause(); } catch {} this.audio = null; } }
  _setBtn() { const b = this.root.querySelector("#guide-play"); b.textContent = this.playing ? "❚❚" : "▶"; b.setAttribute("aria-label", this.playing ? "pause" : "play"); }
  _marks() { const box = this.root.querySelector("#guide-marks"); const T = this.total(); box.innerHTML = this.starts().slice(1).map(t => `<i style="left:${(t / T) * 100}%"></i>`).join(""); }
  _hover(t) { const st = this.starts(); let i = st.length - 1; while (i > 0 && st[i] > t) i--; this.bar.title = `${i + 1}. ${this.steps[i].t}`; }
  _paint(t) { const T = this.total() || 1, k = Math.min(1, t / T); this.fill.style.width = `${k * 100}%`; this.knob.style.left = `${k * 100}%`; this.clock.textContent = `${fmt(t)} / ${fmt(T)}`; }
  _place() {
    const el = this.target && this.target.isConnected && this.target.offsetParent !== null ? this.target : null;
    const spot = this.spot, card = this.card, pad = 10;
    if (this.media) {                                   // the film is the point: no spotlight, the card sits under it
      spot.style.opacity = "0"; const W = window.innerWidth, H = window.innerHeight, box = this.root.querySelector("#guide-media");
      const mw = Math.min(W - 32, 1100, (H * 0.62) * 16 / 9), mh = mw * 9 / 16; box.style.width = `${mw}px`; box.style.left = `${(W - mw) / 2}px`; box.style.top = `${Math.max(12, H * 0.05)}px`;
      card.classList.remove("center"); const cw = Math.min(mw, 620, W - 32); card.style.width = `${cw}px`; card.style.transform = "none";
      card.style.left = `${(W - cw) / 2}px`; card.style.top = `${Math.min(H - (card.offsetHeight || 200) - 12, Math.max(12, H * 0.05) + mh + 14)}px`; return;
    }
    if (!el) { spot.style.opacity = "0"; card.style.left = "50%"; card.style.top = "64%"; card.style.transform = "translate(-50%,-50%)"; card.classList.add("center"); card.style.width = ""; return; }
    const r = el.getBoundingClientRect(); spot.style.opacity = "1"; spot.style.left = `${r.left - pad}px`; spot.style.top = `${r.top - pad}px`; spot.style.width = `${r.width + 2 * pad}px`; spot.style.height = `${r.height + 2 * pad}px`;
    card.classList.remove("center"); card.style.transform = "none"; const cw = Math.min(460, window.innerWidth - 32); card.style.width = `${cw}px`; const ch = card.offsetHeight || 220;
    const W = window.innerWidth, H = window.innerHeight, cx = r.left + r.width / 2; let left, top;
    const clampTop = (t) => Math.max(12, Math.min(H - ch - 12, t));
    if (cx > W * 0.6 && r.left - cw - 24 > 0) { left = r.left - cw - 16; top = clampTop(r.top); }
    else if (cx < W * 0.4 && r.right + cw + 24 < W) { left = r.right + 16; top = clampTop(r.top); }
    else { const below = r.bottom + 16, above = r.top - ch - 16; top = below + ch < H - 12 ? below : (above > 12 ? above : clampTop(H - ch - 12)); left = Math.max(16, Math.min(W - cw - 16, cx - cw / 2)); }
    card.style.left = `${left}px`; card.style.top = `${top}px`;
  }
  _reveal(el) {
    if (this.media) return;
    let p = el.parentElement;
    while (p && p !== document.body) { const cs = getComputedStyle(p); if (/(auto|scroll)/.test(cs.overflowY) && !p.classList.contains("deck")) { const top = el.offsetTop - p.offsetTop; p.scrollTo({ top: Math.max(0, top - 24), behavior: "smooth" }); break; } p = p.parentElement; }
  }
}
function fmt(t) { t = Math.max(0, Math.round(t)); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`; }
