// Generative session player. Everything is synthesised in the browser from the session the
// council composed: entrainment pulse (isochronic or binaural), chord pad, plucked melody,
// sub drone, air. Palette, key, mode, tempo, pulse depth and gain cap all come from the
// session; adapt() nudges the running segment (ISO principle). No audio leaves the device.
//
// Real recordings (previews, soundscapes, podcasts) play through two alternating media
// elements so one track follows the next without a gap; the generated layer sits *under*
// them at a level the person controls (layer.on / layer.level), and the pulse touches the
// recording only lightly (a 40 % share of the depth) so songs never sound like noise.
const NOTE = { C: 0, Db: 1, D: 2, Eb: 3, E: 4, F: 5, Gb: 6, G: 7, Ab: 8, A: 9, Bb: 10, B: 11 };
const MODES = { major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10], dorian: [0, 2, 3, 5, 7, 9, 10], lydian: [0, 2, 4, 6, 7, 9, 11], pentatonic: [0, 2, 4, 7, 9], mixolydian: [0, 2, 4, 5, 7, 9, 10] };
const PROG = { major: [0, 5, 3, 4], minor: [0, 5, 2, 6], dorian: [0, 3, 6, 0], lydian: [0, 1, 4, 0], pentatonic: [0, 3, 4, 0], mixolydian: [0, 6, 3, 0] };
const PALETTE = {
  piano:   { pluck: { types: ["triangle", "sine"], decay: 1.8, cutoff: 3200, mix: 0.9 }, pad: { type: "triangle", gain: 0.35 }, density: 0.55, wet: 0.35 },
  plucked: { pluck: { types: ["sawtooth"], decay: 0.9, cutoff: 1800, mix: 0.8 }, pad: { type: "triangle", gain: 0.3 }, density: 0.6, wet: 0.3 },
  nylon:   { pluck: { types: ["triangle", "sawtooth"], decay: 0.7, cutoff: 2200, mix: 0.85, noise: true }, pad: { type: "triangle", gain: 0.25 }, density: 0.7, wet: 0.25 },
  epiano:  { pluck: { types: ["sine", "sine2"], decay: 1.6, cutoff: 2600, mix: 0.8, trem: true }, pad: { type: "sine", gain: 0.4 }, density: 0.45, wet: 0.4 },
  strings: { pluck: { types: ["sawtooth"], decay: 2.4, cutoff: 1400, mix: 0.4, slow: true }, pad: { type: "sawtooth", gain: 0.5 }, density: 0.2, wet: 0.55 },
  synth:   { pluck: { types: ["square"], decay: 0.5, cutoff: 1600, mix: 0.6 }, pad: { type: "sawtooth", gain: 0.45 }, density: 0.5, wet: 0.45 },
  pad:     { pluck: { types: ["sine"], decay: 2.5, cutoff: 1200, mix: 0.4 }, pad: { type: "triangle", gain: 0.55 }, density: 0.2, wet: 0.6 },
  bells:   { pluck: { types: ["sine", "bell"], decay: 2.6, cutoff: 5000, mix: 0.8 }, pad: { type: "sine", gain: 0.3 }, density: 0.4, wet: 0.5 },
  guitar:  { pluck: { types: ["sawtooth", "triangle"], decay: 1.1, cutoff: 2400, mix: 0.8 }, pad: { type: "triangle", gain: 0.3 }, density: 0.65, wet: 0.3 },
};
const mtof = (m) => 440 * Math.pow(2, (m - 69) / 12);
const dbToGain = (db) => Math.pow(10, db / 20);
const TRACK_PULSE = 0.4;   // share of the pulse depth applied to a real recording

function impulse(ctx, seconds = 2.8, decay = 2.6) {
  const rate = ctx.sampleRate, len = Math.floor(rate * seconds), buf = ctx.createBuffer(2, len, rate);
  for (let c = 0; c < 2; c++) { const d = buf.getChannelData(c); for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, decay); }
  return buf;
}
function pinkNoise(ctx, seconds = 4) {
  const rate = ctx.sampleRate, len = rate * seconds, buf = ctx.createBuffer(1, len, rate), d = buf.getChannelData(0);
  let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
  for (let i = 0; i < len; i++) { const w = Math.random() * 2 - 1; b0 = 0.99886 * b0 + w * 0.0555179; b1 = 0.99332 * b1 + w * 0.0750759; b2 = 0.969 * b2 + w * 0.153852; b3 = 0.8665 * b3 + w * 0.3104856; b4 = 0.55 * b4 + w * 0.5329522; b5 = -0.7616 * b5 - w * 0.016898; d[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.11; b6 = w * 0.115926; }
  return buf;
}

export class SessionPlayer {
  constructor() {
    this.ctx = null; this.playing = false; this.session = null; this.elapsed = 0; this.deltas = { bpm: 0, hz: 0, depth: 0, brightness: 0 }; this.listeners = {};
    this.tracks = []; this.trackIdx = -1; this.els = []; this.cur = 0; this.speed = 1; this.holdHz = null; this.depthOverride = null;
    this.layer = { on: false, level: 0.25 };   // generated layer under real recordings
    this.hasTrack = false; this.pulseOnTrack = false;
  }
  spectrum() { if (!this.analyser) return null; const b = this.fbuf || (this.fbuf = new Uint8Array(this.analyser.frequencyBinCount)); this.analyser.getByteFrequencyData(b); return b; }
  setSpeed(x) { if (this.playing && this.ctx) { this.t0 = this.ctx.currentTime - this.elapsed / x; } this.speed = x; }
  setTracks(tracks) {
    this.tracks = tracks || []; this.trackIdx = -1; this.trackPaused = false;
    if (!this.tracks.length) this._silenceTrack();          // switching to Frequencies: the podcast or song stops, it never plays under them
    else if (this.playing) this._nextTrack();
  }
  _silenceTrack() { for (const el of this.els) { try { el.pause(); } catch {} } if (this.trackGain && this.ctx) this.trackGain.gain.setTargetAtTime(0.0001, this.ctx.currentTime, 0.08); this.hasTrack = false; }
  // the song or episode on its own, without stopping the session (the top button) or its frequency
  pauseTrack() { const el = this.els[this.cur]; if (!el || !this.hasTrack) return false; try { el.pause(); } catch {} this.trackGain.gain.setTargetAtTime(0.0001, this.ctx.currentTime, 0.08); this.hasTrack = false; this.trackPaused = true; this.emit("trackstate", false); return true; }
  resumeTrack() { const el = this.els[this.cur]; if (!el || !this.playing || !this.trackPaused) return false; el.play().then(() => { this.trackGain.gain.setTargetAtTime(0.9, this.ctx.currentTime, 0.3); this.hasTrack = true; this.trackPaused = false; this.emit("trackstate", true); }).catch(() => {}); return true; }
  setLayer(on, level) { if (on !== undefined) this.layer.on = !!on; if (level !== undefined) this.layer.level = Math.min(1, Math.max(0, +level)); }
  warm() { this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)(); return this.ctx.resume(); }
  on(ev, cb) { (this.listeners[ev] ||= []).push(cb); }
  emit(ev, x) { (this.listeners[ev] || []).forEach(cb => cb(x)); }
  get trackTime() { const el = this.els[this.cur]; return el && this.hasTrack ? { t: el.currentTime, d: el.duration } : null; }

  _build() {
    const ctx = this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
    const s = this.session, pal = PALETTE[s.palette] || PALETTE.piano;
    this.master = ctx.createGain(); this.master.gain.value = 0;
    this.comp = ctx.createDynamicsCompressor(); this.comp.threshold.value = -18; this.comp.ratio.value = 4;
    this.analyser = ctx.createAnalyser(); this.analyser.fftSize = 1024;
    this.duckGain = ctx.createGain(); this.duckGain.gain.value = this.ducked ? 0.12 : 1;
    this.master.connect(this.comp).connect(this.duckGain).connect(this.analyser).connect(ctx.destination);
    this.cap = dbToGain(s.gain_dbfs);
    // reverb
    this.wet = ctx.createGain(); this.wet.gain.value = pal.wet; this.conv = ctx.createConvolver(); this.conv.buffer = impulse(ctx); this.wet.connect(this.conv).connect(this.master);
    this.dry = ctx.createGain(); this.dry.gain.value = 1; this.dry.connect(this.master);
    // entrainment bus for the generated layer: gain modulated at hz (isochronic)
    this.pulseGain = ctx.createGain(); this.pulseGain.gain.value = 1; this.pulseGain.connect(this.dry); this.pulseGain.connect(this.wet);
    this.lfo = ctx.createOscillator(); this.lfo.type = "square"; this.lfoSmooth = ctx.createBiquadFilter(); this.lfoSmooth.type = "lowpass"; this.lfoSmooth.frequency.value = 40;
    this.lfoDepth = ctx.createGain(); this.lfoDepth.gain.value = 0; this.lfo.connect(this.lfoSmooth).connect(this.lfoDepth).connect(this.pulseGain.gain); this.lfo.start();
    // a lighter pulse bus for real recordings
    this.trackPulse = ctx.createGain(); this.trackPulse.gain.value = 1; this.trackPulse.connect(this.dry);
    this.lfoDepthT = ctx.createGain(); this.lfoDepthT.gain.value = 0; this.lfoSmooth.connect(this.lfoDepthT).connect(this.trackPulse.gain);
    // binaural carrier (only audible in binaural mode)
    this.binL = ctx.createOscillator(); this.binR = ctx.createOscillator(); const pl = ctx.createStereoPanner(), pr = ctx.createStereoPanner(); pl.pan.value = -1; pr.pan.value = 1;
    this.binGain = ctx.createGain(); this.binGain.gain.value = 0; this.binL.connect(pl).connect(this.binGain); this.binR.connect(pr).connect(this.binGain); this.binGain.connect(this.dry); this.binL.start(); this.binR.start();
    // the frequency on its own (Frequencies): an isochronic tone, a clear carrier switched on and off at the pulse
    // rate, so 2 Hz (slow throbs) and 40 Hz (a fast buzz) sound plainly different; it changes the moment a band is chosen
    this.isoOsc = ctx.createOscillator(); this.isoOsc.type = "sine"; this.isoOsc.frequency.value = 200;
    this.isoGate = ctx.createGain(); this.isoGate.gain.value = 0.5; this.isoLevel = ctx.createGain(); this.isoLevel.gain.value = 0;
    this.isoLfo = ctx.createOscillator(); this.isoLfo.type = "square"; this.isoLfo.frequency.value = 10;
    this.isoSmooth = ctx.createBiquadFilter(); this.isoSmooth.type = "lowpass"; this.isoSmooth.frequency.value = 120;
    this.isoDepth = ctx.createGain(); this.isoDepth.gain.value = 0.5;
    this.isoLfo.connect(this.isoSmooth).connect(this.isoDepth).connect(this.isoGate.gain);
    this.isoOsc.connect(this.isoGate).connect(this.isoLevel).connect(this.dry); this.isoOsc.start(); this.isoLfo.start();
    // tone filter (brightness)
    this.tone = ctx.createBiquadFilter(); this.tone.type = "lowpass"; this.tone.frequency.value = 1800; this.tone.Q.value = 0.4; this.tone.connect(this.pulseGain);
    // pad voices
    this.pad = []; for (let i = 0; i < 3; i++) { const o = ctx.createOscillator(); o.type = pal.pad.type; const g = ctx.createGain(); g.gain.value = 0; const det = ctx.createOscillator(); det.type = pal.pad.type; det.detune.value = 7; const dg = ctx.createGain(); dg.gain.value = 0; o.connect(g).connect(this.tone); det.connect(dg).connect(this.tone); o.start(); det.start(); this.pad.push({ o, g, det, dg }); }
    // sub drone
    this.sub = ctx.createOscillator(); this.sub.type = "sine"; this.subGain = ctx.createGain(); this.subGain.gain.value = 0; this.sub.connect(this.subGain).connect(this.pulseGain); this.sub.start();
    // air (pink noise through a slow bandpass), with breathing swell
    this.air = ctx.createBufferSource(); this.air.buffer = pinkNoise(ctx); this.air.loop = true; this.airFilter = ctx.createBiquadFilter(); this.airFilter.type = "bandpass"; this.airFilter.frequency.value = 600; this.airFilter.Q.value = 0.7;
    this.airGain = ctx.createGain(); this.airGain.gain.value = 0; this.air.connect(this.airFilter).connect(this.airGain).connect(this.wet); this.air.start();
    // real recordings: two media elements alternate so the next one is already buffered
    this.trackFilter = ctx.createBiquadFilter(); this.trackFilter.type = "lowpass"; this.trackFilter.frequency.value = 9000; this.trackFilter.Q.value = 0.3;
    this.trackGain = ctx.createGain(); this.trackGain.gain.value = 0; this.trackFilter.connect(this.trackGain).connect(this.trackPulse);
    if (!this.els.length) {
      for (let i = 0; i < 2; i++) {
        const el = new Audio(); el.preload = "auto"; el.crossOrigin = "anonymous";
        el.addEventListener("ended", () => { if (this.els[this.cur] === el) this._nextTrack(); });
        el.addEventListener("error", () => { if (this.els[this.cur] === el && this.playing) setTimeout(() => this._nextTrack(), 800); });
        el.addEventListener("timeupdate", () => { if (this.els[this.cur] !== el || !this.hasTrack) return; const left = el.duration - el.currentTime; if (!el.loop && isFinite(left) && left < 1.6 && !el._fading) { el._fading = true; this.trackGain.gain.setTargetAtTime(0.0001, this.ctx.currentTime, 0.45); } this.emit("time", { t: el.currentTime, d: el.duration }); });
        try { el._src = ctx.createMediaElementSource(el); } catch { el._src = null; }
        this.els.push(el);
      }
    }
    for (const el of this.els) if (el._src) { try { el._src.connect(this.trackFilter); } catch {} }
    this.pal = pal; this.nextBeat = ctx.currentTime + 0.1; this.beat = 0; this.lastNote = null; this.chordIdx = 0; this.hasTrack = false;
  }
  _preload(idx) { if (this.tracks.length < 2) return; const t = this.tracks[idx % this.tracks.length]; const el = this.els[1 - this.cur]; const src = new URL(t.stream || t.preview, location.href).href; if (el.src !== src) { el.src = src; el._fading = false; try { el.load(); } catch {} } }
  _nextTrack(step = 1) {
    if (!this.playing || !this.tracks.length || !this.els.length) { this.hasTrack = false; return; }
    const prev = this.els[this.cur]; try { prev.pause(); } catch {}
    this.trackIdx = (this.trackIdx + step + this.tracks.length) % this.tracks.length; const t = this.tracks[this.trackIdx];
    const now = this.ctx.currentTime; this.trackGain.gain.cancelScheduledValues(now); this.trackGain.gain.setValueAtTime(0.0001, now);
    const el = this.els[1 - this.cur]; this.cur = 1 - this.cur; const src = new URL(t.stream || t.preview, location.href).href; if (el.src !== src) el.src = src; el._fading = false; el.loop = !!t.loop; el.currentTime = 0; el.volume = 1;
    el.play().then(() => { const n = this.ctx.currentTime; this.trackGain.gain.setTargetAtTime(0.9, n, 0.6); this.hasTrack = true; this.emit("track", { track: t, idx: this.trackIdx, next: this.tracks[(this.trackIdx + 1) % this.tracks.length] }); this._preload(this.trackIdx + 1); }).catch(() => { this.hasTrack = false; });
  }
  skip() { this._nextTrack(1); }
  back() { this._nextTrack(-1); }
  _key() { const s = this.session; return 48 + (NOTE[s.key] ?? 0); }
  _seg() { const segs = this.session.segments; let seg = segs[0], idx = 0; segs.forEach((x, i) => { if (this.elapsed >= x.start_s) { seg = x; idx = i; } }); return { seg, idx, k: Math.min(1, (this.elapsed - seg.start_s) / (seg.minutes * 60)) }; }
  _scale(mode) { return MODES[mode] || MODES.major; }

  _chord(seg) {
    const root = this._key(), scale = this._scale(seg.mode), prog = PROG[seg.mode] || PROG.major;
    const deg = prog[this.chordIdx % prog.length]; const n = scale.length;
    return [0, 2, 4].map(i => root + 12 * Math.floor((deg + i) / n) + scale[(deg + i) % n]);
  }
  _pluck(midi, when, vel = 0.5) {
    const ctx = this.ctx, p = this.pal.pluck; const f = mtof(midi); const g = ctx.createGain(); g.gain.setValueAtTime(0, when);
    const atk = p.slow ? 0.6 : 0.012; g.gain.linearRampToValueAtTime(vel * p.mix, when + atk); g.gain.exponentialRampToValueAtTime(0.0008, when + atk + p.decay);
    const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.setValueAtTime(p.cutoff, when); lp.frequency.exponentialRampToValueAtTime(Math.max(200, p.cutoff * 0.25), when + p.decay);
    g.connect(lp).connect(this.tone);
    for (const t of p.types) {
      const o = ctx.createOscillator(); if (t === "sine2") { o.type = "sine"; o.frequency.value = f * 2; } else if (t === "bell") { o.type = "sine"; o.frequency.value = f * 2.76; } else { o.type = t; o.frequency.value = f; }
      const og = ctx.createGain(); og.gain.value = t === "sine2" || t === "bell" ? 0.35 : 1 / p.types.length; o.connect(og).connect(g); o.start(when); o.stop(when + atk + p.decay + 0.1);
    }
    if (p.noise) { const n = ctx.createBufferSource(); n.buffer = this.air.buffer; const ng = ctx.createGain(); ng.gain.setValueAtTime(0.15 * vel, when); ng.gain.exponentialRampToValueAtTime(0.0005, when + 0.05); n.connect(ng).connect(g); n.start(when); n.stop(when + 0.08); }
  }
  // how loud the generated layer is right now: full when it carries the session alone, the
  // person's chosen level (or silence) under a real recording
  _layer() { return this.hasTrack || this.external || this.trackPaused ? (this.layer.on ? this.layer.level : 0) : 1; }
  setExternal(on) { this.external = !!on; }
  setFreqMode(on) { this.freqMode = !!on; }
  setFreqStyle(style, pad) { if (style) this.freqStyle = style; if (pad !== undefined) this.freqPad = !!pad; }
  // while the person talks to Reach the music steps back, so the microphone hears them and not the song
  duck(on) { this.ducked = !!on; if (this.duckGain && this.ctx) this.duckGain.gain.setTargetAtTime(on ? 0.12 : 1, this.ctx.currentTime, 0.15); }
  _tick() {
    if (!this.playing) return;
    const ctx = this.ctx, s = this.session; this.elapsed = (ctx.currentTime - this.t0) * this.speed;
    const { seg, idx, k } = this._seg();
    if (idx !== this.segIdx) { this.segIdx = idx; this.emit("segment", { seg, idx }); }
    if (this.elapsed >= s.duration_min * 60) { this.stop(); this.emit("end"); return; }
    const bpm = Math.max(40, seg.bpm + this.deltas.bpm);
    const hzBase = seg.hz_from + (seg.hz_to - seg.hz_from) * k; this.jit = (this.jit || 0) * 0.98 + (Math.random() - 0.5) * 0.02 * (seg.jitter || 0);
    const hz = this.holdHz != null ? this.holdHz : Math.max(0.5, hzBase + this.jit * 25 + this.deltas.hz);
    const depth = this.depthOverride != null ? this.depthOverride : Math.min(0.6, Math.max(0, s.pulse_depth + this.deltas.depth)); const bright = Math.min(1, Math.max(0.05, seg.brightness + this.deltas.brightness));
    const now = ctx.currentTime, lay = this._layer();
    const padK = this.freqMode ? (this.freqPad ? 0.3 : 0) : 1;     // Frequencies: the soft pad underneath only if wanted
    // entrainment
    if (s.entrainment === "binaural") { const c = 110 + 60 * bright; this.binL.frequency.setTargetAtTime(c, now, 0.2); this.binR.frequency.setTargetAtTime(c + hz, now, 0.2); this.binGain.gain.setTargetAtTime(0.08 * depth / 0.3 * (this.hasTrack ? Math.max(0.35, lay) : 1), now, 0.5); this.lfoDepth.gain.setTargetAtTime(0, now, 0.5); this.lfoDepthT.gain.setTargetAtTime(0, now, 0.5); this.trackPulse.gain.setTargetAtTime(1, now, 0.5); }
    else {
      this.lfo.frequency.setTargetAtTime(hz, now, 0.2); this.lfoSmooth.frequency.setTargetAtTime(Math.max(12, hz * 3), now, 0.2);
      this.lfoDepth.gain.setTargetAtTime(depth * 0.5, now, 0.5); this.pulseGain.gain.setTargetAtTime(1 - depth * 0.5, now, 0.5); this.binGain.gain.setTargetAtTime(0, now, 0.5);
      const td = this.pulseOnTrack ? depth * 0.5 * TRACK_PULSE : 0; this.lfoDepthT.gain.setTargetAtTime(td, now, 0.5); this.trackPulse.gain.setTargetAtTime(1 - td, now, 0.5);
    }
    if (this.freqMode) {
      const carrier = hz < 4 ? 140 : hz < 8 ? 170 : hz < 12 ? 200 : hz < 30 ? 240 : 280;
      if (this.freqStyle === "binaural") {
        // headphones: each ear gets its own tone, the brain hears the difference (the band's frequency) as a beat
        this.binL.frequency.setTargetAtTime(carrier, now, 0.05); this.binR.frequency.setTargetAtTime(carrier + hz, now, 0.05);
        this.binGain.gain.setTargetAtTime(0.16, now, 0.15); this.isoLevel.gain.setTargetAtTime(0, now, 0.15);
      } else {
        // speakers: one tone switched on and off at the band's rate (isochronic)
        this.isoOsc.frequency.setTargetAtTime(carrier, now, 0.05); this.isoLfo.frequency.setTargetAtTime(hz, now, 0.02);
        this.isoSmooth.frequency.setTargetAtTime(Math.max(20, hz * 4), now, 0.05); this.isoLevel.gain.setTargetAtTime(0.32, now, 0.15);
        this.binGain.gain.setTargetAtTime(0, now, 0.15);
      }
    } else this.isoLevel.gain.setTargetAtTime(0, now, 0.15);
    this.tone.frequency.setTargetAtTime(400 + 4200 * bright * bright, now, 0.8);
    if (this.trackFilter) this.trackFilter.frequency.setTargetAtTime(3000 + 12000 * bright, now, 0.8);
    this.airFilter.frequency.setTargetAtTime(300 + 900 * bright + 200 * Math.sin(this.elapsed * 0.07), now, 1);
    let airLevel = (0.06 + 0.06 * (1 - bright)) * (this.hasTrack ? lay * 0.5 : 1);
    if (s.breathing && this.elapsed < s.breathing.minutes * 60) { const ph = (this.elapsed * s.breathing.rate_per_min / 60) % 1; airLevel *= 0.5 + 0.5 * Math.sin(ph * 2 * Math.PI - Math.PI / 2) + 0.5; this.emit("breath", ph); }
    this.airGain.gain.setTargetAtTime(airLevel * padK, now, 0.3);
    this.pad.forEach(v => { v.g.gain.setTargetAtTime(this.pal.pad.gain * 0.5 * lay * padK, now, 1.0); v.dg.gain.setTargetAtTime(this.pal.pad.gain * 0.3 * lay, now, 1.0); });
    this.subGain.gain.setTargetAtTime(0.35 * lay * padK, now, 1.0);
    const target = seg.fade_out ? this.cap * (1 - k) : this.cap; this.master.gain.setTargetAtTime(target, now, 0.5);
    // sequencer (lookahead 0.25 s)
    const beatLen = 60 / bpm;
    while (this.nextBeat < now + 0.25) {
      const when = this.nextBeat; const b = this.beat;
      if (b % 16 === 0) { this.chordIdx++; const chord = this._chord(seg); this.pad.forEach((v, i) => { const f = mtof(chord[i] - (i === 0 ? 12 : 0)); v.o.frequency.setTargetAtTime(f, when, 0.4); v.det.frequency.setTargetAtTime(f, when, 0.4); }); this.sub.frequency.setTargetAtTime(mtof(chord[0] - 24), when, 0.5); this.emit("chord", chord); }
      const density = this.pal.density * (0.6 + 0.6 * bright) * (seg.repeat ? 0.8 : 1) * (this.hasTrack ? lay * 0.5 : 1);
      if (b % 2 === 0 && lay * padK > 0.02 && Math.random() < density) {
        const scale = this._scale(seg.mode), root = this._key() + 12; let prev = this.lastNote ?? root + scale[0];
        const choices = []; for (let o = 0; o < 2; o++) for (const d of scale) choices.push(root + 12 * o + d);
        const near = choices.filter(n => Math.abs(n - prev) <= (seg.repeat ? 4 : 7)); const n = near[Math.floor(Math.random() * near.length)] || root;
        this.lastNote = n; this._pluck(n, when, (0.35 + 0.25 * bright) * (this.hasTrack ? lay : 1)); this.emit("note", { midi: n, when });
        if (Math.random() < 0.25 * bright) this._pluck(n + (scale.includes(4) ? 4 : 3), when + beatLen * 0.5, 0.22 * (this.hasTrack ? lay : 1));
      }
      this.nextBeat += beatLen; this.beat++;
    }
    this.emit("state", { elapsed: this.elapsed, seg, idx, hz, bpm, depth, bright, layer: lay, hasTrack: this.hasTrack });
    this.timer = setTimeout(() => this._tick(), 90);
  }
  load(session) { this.session = session; this.elapsed = 0; this.deltas = { bpm: 0, hz: 0, depth: 0, brightness: 0 }; }
  async play() {
    if (!this.session) return; if (this.playing) return;
    if (this._pending) this._teardown(this._pending);
    for (const el of this.els) if (el._src) { try { el._src.disconnect(); } catch {} }
    this._build(); await this.ctx.resume(); this.t0 = this.ctx.currentTime - this.elapsed / this.speed; this.playing = true; this.segIdx = -1; this.nextBeat = this.ctx.currentTime + 0.05; this.beat = 0; this._tick(); this.emit("play");
    // resume where the song was paused; only a fresh list starts with its first track
    const el = this.els[this.cur], t = this.tracks[this.trackIdx];
    if (this.trackIdx >= 0 && t && el && el.src && el.src === new URL(t.stream || t.preview, location.href).href && el.currentTime > 0 && !el.ended) {
      el.play().then(() => { this.trackGain.gain.setTargetAtTime(0.9, this.ctx.currentTime, 0.4); this.hasTrack = true; }).catch(() => this._nextTrack());
    } else this._nextTrack();
  }
  pause() {
    if (!this.playing) return; this.playing = false; clearTimeout(this.timer);
    // capture this graph now: a new session may build its own graph before the fade ends,
    // and tearing down "this.lfo" later would stop the new one and leave the old one ringing
    const g = { master: this.master, nodes: [this.lfo, this.binL, this.binR, this.sub, this.air, this.isoOsc, this.isoLfo, ...this.pad.flatMap(v => [v.o, v.det])] };
    g.master.gain.cancelScheduledValues(this.ctx.currentTime); g.master.gain.setTargetAtTime(0, this.ctx.currentTime, 0.12);
    for (const el of this.els) { try { el.pause(); } catch {} } this.hasTrack = false;
    this._pending = g; setTimeout(() => this._teardown(g), 450); this.emit("pause");
  }
  stop() { this.pause(); this.elapsed = 0; }
  _teardown(g) { if (!g || g.done) return; g.done = true; try { g.nodes.forEach(o => { try { o.stop(); } catch {} }); g.master.disconnect(); } catch {} if (this._pending === g) this._pending = null; }
  adapt(d) { this.deltas.bpm += d.bpm_delta || 0; this.deltas.hz += d.hz_delta || 0; this.deltas.depth += d.depth_delta || 0; this.deltas.brightness += d.brightness_delta || 0; this.emit("adapt", d); }
  level() { if (!this.analyser) return 0; const b = new Uint8Array(this.analyser.fftSize); this.analyser.getByteTimeDomainData(b); let s = 0; for (let i = 0; i < b.length; i++) { const v = (b[i] - 128) / 128; s += v * v; } return Math.sqrt(s / b.length); }
}
