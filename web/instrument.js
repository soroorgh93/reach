// The frequency instrument: pick a band, pick how you listen, hear it, and watch sand on a vibrating plate draw
// that band's figure (a Chladni pattern) in 3D. Used on the start page and in the app's Frequencies tab.
//   speakers   isochronic tone: one pitch, its loudness pulsing at the band's rate (works on any speaker)
//   headphones binaural beat: a slightly different pitch in each ear; the brain hears the difference as a beat
// Safety: volume is capped (WHO safe listening), and the picture never flashes at the pulse rate (no photic
// flicker): the plate moves slowly whatever the band. Evidence is stated per band; entrainment is experimental.
import * as THREE from "three";

export const BANDS = [
  { id: "delta", hz: 2, mode: [2, 5], color: "#7b86ff" },
  { id: "theta", hz: 6, mode: [3, 7], color: "#b483ff" },
  { id: "alpha", hz: 10, mode: [4, 7], color: "#3fd1c0" },
  { id: "beta", hz: 16, mode: [5, 8], color: "#e8b63e" },
  { id: "gamma", hz: 40, mode: [7, 10], color: "#ff6f91" },
];
const PITCH = { low: 110, mid: 196, high: 392 };
const MAX_GAIN = 0.22;                       // about -13 dBFS at full slider: within Reach's -14 dBFS session cap
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

class Plate {
  constructor(canvas) {
    this.canvas = canvas; this.ok = false;
    try { this.r = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true }); } catch { return; }
    this.ok = true; this.r.setPixelRatio(Math.min(2, devicePixelRatio || 1)); this.r.setClearColor(0, 0);
    this.scene = new THREE.Scene(); this.cam = new THREE.PerspectiveCamera(34, 1, 0.1, 50);
    const N = 120, pos = [], uv = [];
    for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
      const u = -1 + (2 * x + 1) / N, v = -1 + (2 * y + 1) / N; if (u * u + v * v > 0.98) continue;
      pos.push(u * 2, 0, v * 2); uv.push(u, v);
    }
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute("puv", new THREE.Float32BufferAttribute(uv, 2));
    this.uni = { uA: { value: new THREE.Vector2(4, 7) }, uB: { value: new THREE.Vector2(4, 7) }, uMix: { value: 1 }, uTime: { value: 0 }, uAmp: { value: 0.12 },
                 uColor: { value: new THREE.Color("#3fd1c0") }, uSand: { value: new THREE.Color("#fff2c9") }, uPx: { value: 2.2 } };
    const vs = `attribute vec2 puv; uniform vec2 uA, uB; uniform float uMix, uTime, uAmp, uPx; varying float vNode; varying float vR;
      float z(vec2 m, vec2 p){ float PI=3.14159265; return cos(m.x*PI*p.x)*cos(m.y*PI*p.y) - cos(m.y*PI*p.x)*cos(m.x*PI*p.y); }
      void main(){ float za = z(uA, puv), zb = z(uB, puv); float zz = mix(za, zb, uMix);
        float breathe = 0.65 + 0.35 * sin(uTime * 1.1);
        vec3 p = position; p.y = zz * uAmp * breathe;
        vNode = 1.0 - smoothstep(0.0, 0.16, abs(zz)); vR = length(puv);
        vec4 mv = modelViewMatrix * vec4(p, 1.0); gl_Position = projectionMatrix * mv;
        gl_PointSize = uPx * (0.6 + 1.6 * vNode) * (10.0 / -mv.z); }`;
    const fs = `uniform vec3 uColor, uSand; varying float vNode; varying float vR;
      void main(){ vec2 c = gl_PointCoord - 0.5; float d = length(c); if (d > 0.5) discard;
        float a = smoothstep(0.5, 0.0, d); vec3 col = mix(uColor * 0.35, uSand, vNode);
        gl_FragColor = vec4(col, a * (0.18 + 0.82 * vNode) * smoothstep(1.0, 0.92, vR)); }`;
    this.pts = new THREE.Points(g, new THREE.ShaderMaterial({ vertexShader: vs, fragmentShader: fs, uniforms: this.uni, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.scene.add(this.pts);
    const rim = new THREE.Mesh(new THREE.TorusGeometry(2.02, 0.012, 8, 160), new THREE.MeshBasicMaterial({ color: 0xc9a24a, transparent: true, opacity: 0.7 })); rim.rotation.x = Math.PI / 2; this.scene.add(rim);
    const rim2 = rim.clone(); rim2.material = rim.material.clone(); rim2.material.opacity = 0.18; rim2.scale.setScalar(1.08); this.scene.add(rim2);
    this.rim = rim; this.t0 = performance.now(); this.running = false; this.az = 0;
    new ResizeObserver(() => this.fit()).observe(canvas); this.fit();
  }
  fit() { if (!this.ok) return; const w = this.canvas.clientWidth, h = this.canvas.clientHeight; if (!w || !h) return; this.r.setSize(w, h, false); this.cam.aspect = w / h; this.cam.updateProjectionMatrix(); }
  setBand(b) { if (!this.ok) return; this.uni.uA.value.copy(this.uni.uMix.value >= 1 ? this.uni.uB.value : this.uni.uA.value.clone().lerp(this.uni.uB.value, this.uni.uMix.value)); this.uni.uB.value.set(b.mode[0], b.mode[1]); this.uni.uMix.value = 0; this.target = new THREE.Color(b.color); }
  setLevel(on) { this.level = on ? 1 : 0; }
  start() { if (!this.ok || this.running) return; this.running = true; const tick = () => { if (!this.running) return; this.frame(); requestAnimationFrame(tick); }; requestAnimationFrame(tick); }
  stop() { this.running = false; }
  frame() {
    const t = (performance.now() - this.t0) / 1000;
    this.uni.uTime.value = reduceMotion ? 0 : t; this.uni.uMix.value = Math.min(1, this.uni.uMix.value + 0.012);
    if (this.target) this.uni.uColor.value.lerp(this.target, 0.05);
    const want = (this.level ? 0.22 : 0.1); this.uni.uAmp.value += (want - this.uni.uAmp.value) * 0.04;
    if (!reduceMotion) this.az += 0.0016;
    const d = 6.4; this.cam.position.set(Math.sin(this.az) * d * 0.55, 3.6, Math.cos(this.az) * d * 0.55 + 2.6); this.cam.lookAt(0, -0.2, 0);
    this.uni.uPx.value = Math.max(1.6, Math.min(3.2, this.canvas.clientWidth / 260));
    this.r.render(this.scene, this.cam);
  }
}

class Tone {
  // one Web Audio graph per instrument: built on the first Play (browsers allow sound only after a tap)
  constructor() { this.ctx = null; this.on = false; this.style = "iso"; this.band = BANDS[2]; this.pitch = "mid"; this.pad = false; this.vol = 0.6; }
  ensure() {
    if (this.ctx) return; const C = window.AudioContext || window.webkitAudioContext; this.ctx = new C();
    const c = this.ctx; this.out = c.createGain(); this.out.gain.value = 0; this.out.connect(c.destination);
    this.merge = c.createChannelMerger(2); this.merge.connect(this.out);
    this.gL = c.createGain(); this.gR = c.createGain(); this.gL.connect(this.merge, 0, 0); this.gR.connect(this.merge, 0, 1);
    this.oL = c.createOscillator(); this.oR = c.createOscillator(); this.oL.type = this.oR.type = "sine"; this.oL.connect(this.gL); this.oR.connect(this.gR); this.oL.start(); this.oR.start();
    // the isochronic pulse: a low-frequency oscillator shaping the loudness (smoothed, so it is never a click)
    this.lfo = c.createOscillator(); this.lfo.type = "sine"; this.lfoGain = c.createGain(); this.lfo.connect(this.lfoGain); this.lfo.start();
    this.amp = c.createGain(); this.amp.gain.value = 0.5; this.lfoGain.connect(this.amp.gain);
    this.oI = c.createOscillator(); this.oI.type = "sine"; this.oI.connect(this.amp); this.amp.connect(this.gL); this.amp.connect(this.gR); this.oI.start();
    // the soft pad: two detuned triangles an octave below, low-passed
    this.padGain = c.createGain(); this.padGain.gain.value = 0; const lp = c.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 700; this.padGain.connect(lp); lp.connect(this.gL); lp.connect(this.gR);
    this.p1 = c.createOscillator(); this.p2 = c.createOscillator(); this.p1.type = this.p2.type = "triangle"; this.p1.connect(this.padGain); this.p2.connect(this.padGain); this.p1.start(); this.p2.start();
    this.apply();
  }
  apply() {
    if (!this.ctx) return; const c = this.ctx, now = c.currentTime, f = PITCH[this.pitch], b = this.band.hz, T = 0.08;
    const bin = this.style === "binaural";
    this.oL.frequency.setTargetAtTime(f, now, T); this.oR.frequency.setTargetAtTime(f + b, now, T);
    this.oI.frequency.setTargetAtTime(f, now, T); this.lfo.frequency.setTargetAtTime(b, now, T);
    // binaural: the two ears' tones on, the pulsed tone off; speakers: the reverse
    const oLg = bin ? 1 : 0; this.oL.disconnect(); this.oR.disconnect(); if (bin) { this.oL.connect(this.gL); this.oR.connect(this.gR); }
    this.amp.gain.setTargetAtTime(bin ? 0 : 0.5, now, T); this.lfoGain.gain.setTargetAtTime(bin ? 0 : 0.5, now, T);
    this.p1.frequency.setTargetAtTime(f / 2, now, T); this.p2.frequency.setTargetAtTime(f / 2 * 1.006, now, T);
    this.padGain.gain.setTargetAtTime(this.pad ? 0.35 : 0, now, 0.3);
    this.gL.gain.setTargetAtTime(oLg ? 0.55 : 0.55, now, T); this.gR.gain.setTargetAtTime(0.55, now, T);
    this.out.gain.setTargetAtTime(this.on ? MAX_GAIN * this.vol : 0, now, 0.25);
  }
  async play() { this.ensure(); if (this.ctx.state === "suspended") await this.ctx.resume(); this.on = true; this.apply(); }
  stop() { this.on = false; this.apply(); }
}

// text: tr(key) -> string; the keys are listed in i18n_after.js (fq_*)
export function createInstrument(root, { tr, compact = false, onBand } = {}) {
  root.classList.add("fq"); if (compact) root.classList.add("compact");
  root.innerHTML = `
    <div class="fq-stage"><canvas class="fq-canvas"></canvas><div class="fq-read"><b class="fq-hz">10 Hz</b><span class="fq-name"></span></div></div>
    <div class="fq-panel">
      <div class="fq-row fq-bands" role="group"></div>
      <div class="fq-row"><span class="fq-k" data-k="fq_listen"></span><div class="fq-seg" data-g="style"><button data-v="iso" aria-pressed="true"><span aria-hidden="true">🔈</span> <span data-k="fq_speakers"></span></button><button data-v="binaural" aria-pressed="false"><span aria-hidden="true">🎧</span> <span data-k="fq_phones"></span></button></div></div>
      <div class="fq-row"><span class="fq-k" data-k="fq_pitch"></span><div class="fq-seg" data-g="pitch"><button data-v="low" aria-pressed="false" data-k="fq_low"></button><button data-v="mid" aria-pressed="true" data-k="fq_mid"></button><button data-v="high" aria-pressed="false" data-k="fq_high"></button></div>
        <label class="fq-pad"><input type="checkbox"><span data-k="fq_pad"></span></label></div>
      <div class="fq-row fq-go"><button class="fq-play" aria-pressed="false"><span class="fq-icon">▶</span><span class="fq-pl" data-k="fq_play"></span></button>
        <label class="fq-vol"><span data-k="fq_volume"></span><input type="range" min="0" max="1" step="0.01" value="0.6"></label></div>
      <p class="fq-ev"></p>
      <p class="fq-note" data-k="fq_note"></p>
    </div>`;
  const $ = (s) => root.querySelector(s), $$ = (s) => [...root.querySelectorAll(s)];
  const plate = new Plate($(".fq-canvas")), tone = new Tone();
  const bandsEl = $(".fq-bands");
  bandsEl.innerHTML = BANDS.map(b => `<button data-band="${b.id}" style="--c:${b.color}" aria-pressed="${b.id === "alpha"}"><b>${b.hz} Hz</b><span data-k="fq_${b.id}"></span></button>`).join("");
  function text() {
    $$("[data-k]").forEach(el => { el.textContent = tr(el.dataset.k); });
    const b = tone.band; $(".fq-hz").textContent = `${b.hz} Hz`; $(".fq-name").textContent = `${b.id} · ${tr("fq_" + b.id)}`;
    $(".fq-ev").textContent = tr("fq_ev_" + b.id); $(".fq-pl").textContent = tr(tone.on ? "fq_stop" : "fq_play");
  }
  function pick(id) {
    const b = BANDS.find(x => x.id === id) || BANDS[2]; tone.band = b; tone.apply(); plate.setBand(b);
    $$(".fq-bands button").forEach(x => x.setAttribute("aria-pressed", String(x.dataset.band === id))); root.style.setProperty("--fq", b.color); text(); if (onBand) onBand(b);
  }
  bandsEl.addEventListener("click", (e) => { const x = e.target.closest("[data-band]"); if (x) { pick(x.dataset.band); if (!tone.on) play(); } });
  root.addEventListener("click", (e) => { const x = e.target.closest(".fq-seg button"); if (!x) return; const g = x.parentElement.dataset.g;
    x.parentElement.querySelectorAll("button").forEach(y => y.setAttribute("aria-pressed", String(y === x))); tone[g] = x.dataset.v; tone.apply(); text(); });
  $(".fq-pad input").addEventListener("change", (e) => { tone.pad = e.target.checked; tone.apply(); });
  $(".fq-vol input").addEventListener("input", (e) => { tone.vol = +e.target.value; tone.apply(); });
  async function play() { await tone.play(); plate.setLevel(true); $(".fq-play").setAttribute("aria-pressed", "true"); $(".fq-icon").textContent = "❚❚"; root.classList.add("on"); text(); }
  function stop() { tone.stop(); plate.setLevel(false); $(".fq-play").setAttribute("aria-pressed", "false"); $(".fq-icon").textContent = "▶"; root.classList.remove("on"); text(); }
  $(".fq-play").addEventListener("click", () => { if (tone.on) stop(); else play(); });
  pick("alpha");
  return { start() { plate.start(); }, pause() { plate.stop(); }, stop, play, pick, relang: text, get playing() { return tone.on; } };
}
