// After the music: a night map of the person's own city in 3D. Reach sits at the centre as a small
// glowing orb; each place Qloo suggests rises from the ground as a column of light whose height is its
// affinity, set at its real bearing and distance (Qloo coordinates) when known. Light flows from the orb
// to each place along an arc. Books stand as lit volumes on a slow carousel. The list beside it is the
// same data, ranked; choosing a card turns the camera to its column, choosing a column picks the card.
import * as THREE from "three";

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const KIND_COLOR = { place: null, food: "#f2b45c", read: "#b9a7ff" };       // null: the session's accent

const glowTex = (() => {
  const c = document.createElement("canvas"); c.width = c.height = 128; const g = c.getContext("2d");
  const r = g.createRadialGradient(64, 64, 0, 64, 64, 64); r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(0.25, "rgba(255,255,255,0.55)"); r.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = r; g.fillRect(0, 0, 128, 128); return new THREE.CanvasTexture(c);
})();

const FLOOR_VS = `varying vec3 vW; void main(){ vec4 w = modelMatrix * vec4(position,1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }`;
const FLOOR_FS = `uniform vec3 uColor; uniform float uTime; uniform float uRing; varying vec3 vW;
float line(float v, float w){ float d = abs(fract(v - 0.5) - 0.5) / fwidth(v); return 1.0 - min(d / w, 1.0); }
void main(){
  float r = length(vW.xz);
  float grid = max(line(vW.x, 1.0), line(vW.z, 1.0)) * 0.16 + max(line(vW.x * 0.25, 1.2), line(vW.z * 0.25, 1.2)) * 0.18;
  float rings = uRing > 0.0 ? line(r / uRing, 1.3) * 0.32 : 0.0;
  float wave = smoothstep(0.0, 0.6, 0.6 - abs(r - mod(uTime * 2.2, 16.0))) * 0.35;
  float fade = smoothstep(15.0, 2.0, r);
  vec3 col = uColor * (grid + rings + wave) + uColor * 0.05 * smoothstep(7.0, 0.0, r);
  gl_FragColor = vec4(col, (grid + rings + wave + 0.04) * fade);
}`;
const BEAM_VS = `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`;
const BEAM_FS = `uniform vec3 uColor; uniform float uGain; varying vec2 vUv;
void main(){ float a = pow(1.0 - vUv.y, 1.6) * (0.35 + 0.65 * uGain); gl_FragColor = vec4(uColor * (1.0 + uGain), a); }`;
const ARC_FS = `uniform vec3 uColor; uniform float uTime; uniform float uGain; varying vec2 vUv;
void main(){ float p = fract(vUv.x * 1.0 - uTime * 0.32); float pulse = smoothstep(0.0, 0.08, p) * smoothstep(0.22, 0.08, p);
  float a = (0.12 + 0.9 * pulse) * (0.4 + 0.6 * uGain) * smoothstep(0.0, 0.06, vUv.x) * smoothstep(1.0, 0.9, vUv.x);
  gl_FragColor = vec4(uColor * (1.2 + pulse), a); }`;

function bookTexture(title, sub, color) {
  const c = document.createElement("canvas"); c.width = 512; c.height = 720; const g = c.getContext("2d");
  const grd = g.createLinearGradient(0, 0, 512, 720); grd.addColorStop(0, color); grd.addColorStop(1, "#141826"); g.fillStyle = grd; g.fillRect(0, 0, 512, 720);
  const sh = g.createRadialGradient(150, 120, 10, 150, 120, 420); sh.addColorStop(0, "rgba(255,255,255,0.22)"); sh.addColorStop(1, "rgba(255,255,255,0)"); g.fillStyle = sh; g.fillRect(0, 0, 512, 720);
  g.strokeStyle = "rgba(243,214,140,0.75)"; g.lineWidth = 4; g.strokeRect(34, 34, 444, 652); g.lineWidth = 1.5; g.strokeRect(48, 48, 416, 624);
  g.fillStyle = "#ede7da"; g.textAlign = "center";
  const words = String(title || "").split(/\s+/); const lines = []; let cur = "";
  g.font = '500 64px "Cormorant Garamond", Georgia, serif';
  for (const w of words) { const t = cur ? cur + " " + w : w; if (g.measureText(t).width > 400 && cur) { lines.push(cur); cur = w; } else cur = t; }
  if (cur) lines.push(cur);
  lines.slice(0, 5).forEach((l, i) => g.fillText(l, 256, 250 + i * 66 - (Math.min(lines.length, 5) - 1) * 33));
  g.font = '400 24px "IBM Plex Sans", system-ui, sans-serif'; g.fillStyle = "rgba(237,231,218,0.7)"; if (sub) g.fillText(sub, 256, 620);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
}

export class AfterScene {
  constructor(canvas, labels) {
    this.canvas = canvas; this.labels = labels; this.ok = false; this.items = []; this.kind = "place"; this.sel = -1; this.onPick = null;
    try { this.r = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" }); } catch { return; }
    this.ok = true;
    this.r.setPixelRatio(Math.min(2, window.devicePixelRatio || 1)); this.r.setClearColor(0x000000, 0);
    this.scene = new THREE.Scene(); this.scene.fog = new THREE.FogExp2(0x06070d, 0.045);
    this.cam = new THREE.PerspectiveCamera(38, 1, 0.1, 200);
    this.az = 0.6; this.el = 0.74; this.dist = 21; this.azT = this.az; this.target = new THREE.Vector3(0, 0.8, 0); this.targetT = this.target.clone();
    this.accent = new THREE.Color("#3fd1c0");
    // the city floor
    this.floorMat = new THREE.ShaderMaterial({ vertexShader: FLOOR_VS, fragmentShader: FLOOR_FS, transparent: true, depthWrite: false,
      uniforms: { uColor: { value: this.accent.clone() }, uTime: { value: 0 }, uRing: { value: 0 } } });
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(40, 40, 1, 1), this.floorMat); floor.rotation.x = -Math.PI / 2; this.scene.add(floor);
    // Reach: the orb at the centre
    this.orb = new THREE.Group();
    this.core = new THREE.Mesh(new THREE.SphereGeometry(0.42, 48, 32), new THREE.MeshBasicMaterial({ color: 0xfff2c9, fog: false })); this.orb.add(this.core);
    this.halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: 0xffe7a8, fog: false, transparent: true, opacity: 0.9, depthWrite: false, blending: THREE.AdditiveBlending })); this.halo.scale.set(3.4, 3.4, 1); this.orb.add(this.halo);
    this.orb.position.y = 0.9; this.scene.add(this.orb);
    this.pulses = [0, 1, 2].map(i => { const m = new THREE.Mesh(new THREE.RingGeometry(0.96, 1, 96), new THREE.MeshBasicMaterial({ color: 0xffe7a8, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending })); m.rotation.x = -Math.PI / 2; m.position.y = 0.02; m.userData.ph = i / 3; this.scene.add(m); return m; });
    // fireflies
    const n = 260, pos = new Float32Array(n * 3); for (let i = 0; i < n; i++) { const a = Math.random() * Math.PI * 2, rr = 1.5 + Math.random() * 12; pos.set([Math.cos(a) * rr, 0.2 + Math.random() * 5, Math.sin(a) * rr], i * 3); }
    const fg = new THREE.BufferGeometry(); fg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this.flies = new THREE.Points(fg, new THREE.PointsMaterial({ size: 0.09, map: glowTex, color: 0xffe7a8, transparent: true, opacity: 0.55, depthWrite: false, blending: THREE.AdditiveBlending })); this.scene.add(this.flies);
    this.world = new THREE.Group(); this.scene.add(this.world);
    this.ray = new THREE.Raycaster(); this.hits = [];
    this.t0 = performance.now(); this.running = false; this.built = 0;
    this._resize = () => this.resize(); new ResizeObserver(this._resize).observe(canvas.parentElement);
    this._input();
  }
  setAccent(hex) { if (!this.ok) return; this.accent.set(hex); this.floorMat.uniforms.uColor.value.set(hex); this.rebuildColors(); }
  colorOf(kind) { return new THREE.Color(KIND_COLOR[kind] || this.accent); }
  resize() { if (!this.ok) return; const c = this.canvas; const w = c.clientWidth, h = c.clientHeight; if (!w || !h) return; this.r.setSize(w, h, false); this.cam.aspect = w / h; this.cam.updateProjectionMatrix(); this.wide = w / h > 1.15;
    // labels stay clear of the list and the tab bar
    const side = c.parentElement.querySelector(".afside"), cr = c.getBoundingClientRect(), sr = side ? side.getBoundingClientRect() : null;
    this.flip = !!(sr && sr.left - cr.left > cr.width / 2);            // right-to-left: the list sits on the right
    this.safe = this.wide && sr ? (this.flip ? { left: 0, right: sr.left - cr.left - 12, top: 130 - cr.top } : { left: sr.right - cr.left + 12, top: 130 - cr.top }) : { left: 0, top: 6 }; }
  _input() {
    let drag = null;
    this.canvas.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, az: this.azT, moved: false }; this.canvas.setPointerCapture(e.pointerId); });
    this.canvas.addEventListener("pointermove", (e) => { if (!drag) return; const dx = e.clientX - drag.x; if (Math.abs(dx) > 4) drag.moved = true; this.azT = drag.az - dx * 0.006; this.userAt = performance.now(); });
    this.canvas.addEventListener("pointerup", (e) => { const d = drag; drag = null; if (d && !d.moved) this._click(e); });
  }
  _click(e) {
    const rc = this.canvas.getBoundingClientRect(); const m = new THREE.Vector2(((e.clientX - rc.left) / rc.width) * 2 - 1, -((e.clientY - rc.top) / rc.height) * 2 + 1);
    this.ray.setFromCamera(m, this.cam); const hit = this.ray.intersectObjects(this.hits, false)[0];
    if (hit && this.onPick) this.onPick(hit.object.userData.i);
  }
  clear() { while (this.world.children.length) { const o = this.world.children.pop(); o.traverse(x => { if (x.geometry) x.geometry.dispose(); if (x.material) { if (x.material.map && x.material.map !== glowTex) x.material.map.dispose(); x.material.dispose(); } }); } this.hits = []; this.nodes = []; this.labels.innerHTML = ""; }
  // positions: real bearing and distance when Qloo gave coordinates, else a golden-angle spiral by rank
  layout(items, centre) {
    const geo = centre && items.filter(x => x.lat != null && x.lon != null).length >= Math.max(1, items.length - 1);
    let pts;
    if (geo) {
      const k = Math.cos(centre.lat * Math.PI / 180);
      pts = items.map(x => x.lat == null ? null : [(x.lon - centre.lon) * 111.32 * k, -(x.lat - centre.lat) * 110.57]);
      const far = Math.max(0.5, ...pts.filter(Boolean).map(p => Math.hypot(p[0], p[1])));
      const s = 7.2 / far; this.kmPerUnit = 1 / s;
      pts = pts.map((p, i) => { if (!p) { const a = i * 2.39996; return [Math.cos(a) * 5, Math.sin(a) * 5]; } let x = p[0] * s, z = p[1] * s; const r = Math.hypot(x, z); if (r < 2.4) { const a = Math.atan2(z, x) || i * 2.39996; x = Math.cos(a) * 2.4; z = Math.sin(a) * 2.4; } return [x, z]; });
      // a ring every round number of kilometres, so distance reads at a glance
      const step = [0.5, 1, 2, 5, 10, 20][[0.5, 1, 2, 5, 10, 20].findIndex(v => far / v <= 5) >>> 0] || 5; this.floorMat.uniforms.uRing.value = step * s; this.ringKm = step;
    } else {
      this.floorMat.uniforms.uRing.value = 0; this.ringKm = null;
      pts = items.map((x, i) => { const a = 0.9 + i * 2.39996, r = 3 + (1 - Math.min(1, Math.max(0, (x.affinity || 0.5) - 0.5) * 2)) * 4 + i * 0.35; return [Math.cos(a) * r, Math.sin(a) * r]; });
    }
    return pts;
  }
  show(kind, items, centre) {
    if (!this.ok) return; this.clear(); this.carousel = null; this.spinT = null; this.targetT.set(0, 0.8, 0); this.kind = kind; this.items = items; this.sel = -1; this.built = performance.now();
    if (kind === "read") return this._books(items);
    const pts = this.layout(items, centre); const col = this.colorOf(kind);
    items.forEach((it, i) => {
      const [x, z] = pts[i]; const h = 1.1 + Math.max(0, Math.min(1, ((it.affinity || 0.6) - 0.5) * 2)) * 2.6;
      const g = new THREE.Group(); g.position.set(x, 0, z);
      const beamMat = new THREE.ShaderMaterial({ vertexShader: BEAM_VS, fragmentShader: BEAM_FS, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, uniforms: { uColor: { value: col.clone() }, uGain: { value: 0 } } });
      const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 1, 16, 1, true), beamMat); beam.position.y = 0.5; beam.scale.y = 0.001;
      const glowMat = beamMat.clone(); glowMat.uniforms = { uColor: { value: col.clone() }, uGain: { value: 0 } };
      const glow = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 1, 24, 1, true), glowMat); glow.position.y = 0.5; glow.scale.y = 0.001; glow.material.opacity = 0.4;
      const top = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: col.clone(), fog: false, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })); top.scale.set(1.2, 1.2, 1);
      const cap = new THREE.Mesh(new THREE.SphereGeometry(0.13, 24, 16), new THREE.MeshBasicMaterial({ color: col.clone().lerp(new THREE.Color(0xffffff), 0.5), fog: false }));
      const base = new THREE.Mesh(new THREE.RingGeometry(0.28, 0.36, 48), new THREE.MeshBasicMaterial({ color: col.clone(), transparent: true, opacity: 0.8, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending })); base.rotation.x = -Math.PI / 2; base.position.y = 0.02;
      const hit = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 0.6, h + 0.8, 8), new THREE.MeshBasicMaterial({ visible: false })); hit.position.y = (h + 0.8) / 2; hit.userData.i = i; this.hits.push(hit);
      g.add(beam, glow, top, cap, base, hit); this.world.add(g);
      // the arc from Reach to the place
      const end = new THREE.Vector3(x, 0.05, z), mid = new THREE.Vector3(x / 2, 0.9 + Math.hypot(x, z) * 0.28, z / 2);
      const curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(0, 0.6, 0), mid, end);
      const arcMat = new THREE.ShaderMaterial({ vertexShader: BEAM_VS, fragmentShader: ARC_FS, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: { uColor: { value: col.clone() }, uTime: { value: i * 0.7 }, uGain: { value: 0 } } });
      const arc = new THREE.Mesh(new THREE.TubeGeometry(curve, 64, 0.022, 6, false), arcMat); this.world.add(arc);
      const lab = document.createElement("div"); lab.className = "afl"; lab.innerHTML = `<b></b><span></span>`; lab.querySelector("b").textContent = it.name || ""; lab.querySelector("span").textContent = it._meta || ""; this.labels.appendChild(lab);
      this.nodes.push({ g, beam, glow, top, cap, base, arc, h, lab, delay: i * 0.12, col });
    });
  }
  _books(items) {
    this.floorMat.uniforms.uRing.value = 0; this.ringKm = null;
    const col = this.colorOf("read"); this.carousel = new THREE.Group(); this.world.add(this.carousel);
    const n = Math.max(1, items.length), spread = 1.25;
    items.forEach((it, i) => {
      const a = this.az + (n === 1 ? 0 : (i / (n - 1) - 0.5) * spread * 2) * 0.9;            // around the side the camera looks from
      const tex = bookTexture(it.name, it.year ? String(it.year) : "", ["#5b4aa8", "#2f7186", "#8a4a78"][i % 3]);
      const side = new THREE.MeshBasicMaterial({ color: col.clone().multiplyScalar(0.45), fog: false });
      const front = new THREE.MeshBasicMaterial({ map: tex, fog: false });
      const book = new THREE.Mesh(new THREE.BoxGeometry(1.9, 2.7, 0.3), [side, side, side, side, front, side]);
      const g = new THREE.Group(); g.position.set(Math.sin(a) * 4.2, 2.0, Math.cos(a) * 4.2); g.add(book);
      const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: col.clone(), fog: false, transparent: true, opacity: 0.35, depthWrite: false, blending: THREE.AdditiveBlending })); glow.scale.set(4.6, 5.2, 1); glow.position.z = -0.5; g.add(glow);
      const base = new THREE.Mesh(new THREE.RingGeometry(0.7, 0.78, 64), new THREE.MeshBasicMaterial({ color: col.clone(), transparent: true, opacity: 0.6, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending })); base.rotation.x = -Math.PI / 2; base.position.set(g.position.x, 0.02, g.position.z);
      const beamMat = new THREE.ShaderMaterial({ vertexShader: BEAM_VS, fragmentShader: BEAM_FS, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, uniforms: { uColor: { value: col.clone() }, uGain: { value: 0 } } });
      const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.75, 0.65, 32, 1, true), beamMat); beam.position.set(g.position.x, 0.33, g.position.z);
      book.userData.i = i; this.hits.push(book);
      this.carousel.add(g); this.world.add(base, beam);
      const lab = document.createElement("div"); lab.className = "afl"; lab.innerHTML = `<b></b><span></span>`; lab.querySelector("b").textContent = it.name || ""; lab.querySelector("span").textContent = it._meta || ""; this.labels.appendChild(lab);
      this.nodes.push({ g, book, glow, base, beamB: beam, lab, delay: i * 0.15, col, a, home: g.position.clone() });
    });
  }
  rebuildColors() { if (this.items && this.items.length && this.kind !== "read") this.show(this.kind, this.items, this._centre); }
  select(i) {
    if (!this.ok) return; this.sel = i; const n = this.nodes && this.nodes[i]; if (!n) return;
    if (this.kind === "read") { this.azT = n.a; return; }
    const p = n.g.position; this.azT = Math.atan2(p.x, p.z) + (this.wide ? 0.55 : 0.25); this.targetT.set(p.x * 0.45, 0.9, p.z * 0.45);
  }
  start() { if (!this.ok || this.running) return; this.running = true; this.resize(); const tick = () => { if (!this.running) return; this.frame(); requestAnimationFrame(tick); }; requestAnimationFrame(tick); }
  stop() { this.running = false; }
  frame() {
    const now = performance.now(), t = (now - this.t0) / 1000, since = (now - this.built) / 1000;
    if (!reduceMotion && (!this.userAt || now - this.userAt > 4000) && this.sel < 0 && this.kind !== "read") this.azT += 0.0009;
    this.az += (this.azT - this.az) * 0.05; this.target.lerp(this.targetT, 0.05);
    const d = this.wide ? this.dist : this.dist * 1.25;
    this.cam.position.set(this.target.x + Math.sin(this.az) * Math.cos(this.el) * d, this.target.y + Math.sin(this.el) * d, this.target.z + Math.cos(this.az) * Math.cos(this.el) * d);
    // on wide screens the list covers the left: look a little to the left so the city sits on the right
    const look = this.target.clone(); if (this.wide) { const side = new THREE.Vector3(Math.cos(this.az), 0, -Math.sin(this.az)); look.addScaledVector(side, this.flip ? 3.2 : -3.2); }
    this.cam.lookAt(look);
    this.floorMat.uniforms.uTime.value = t;
    const breathe = reduceMotion ? 1 : 1 + 0.06 * Math.sin(t * 1.3); this.core.scale.setScalar(breathe); this.halo.material.opacity = 0.75 + 0.2 * Math.sin(t * 1.3);
    this.pulses.forEach(m => { const k = reduceMotion ? 0.4 : (t * 0.28 + m.userData.ph) % 1; m.scale.setScalar(0.6 + k * 4.5); m.material.opacity = (1 - k) * 0.35; });
    if (!reduceMotion) this.flies.rotation.y = t * 0.012;
    const W = this.canvas.clientWidth, H = this.canvas.clientHeight, v = new THREE.Vector3();
    (this.nodes || []).forEach((n, i) => {
      const grow = reduceMotion ? 1 : Math.min(1, Math.max(0, (since - n.delay) / 1.1)); const e = 1 - Math.pow(1 - grow, 3);
      const on = this.sel === i ? 1 : 0; n.gain = (n.gain || 0) + (on - (n.gain || 0)) * 0.12;
      if (this.kind === "read") {
        const fwd = new THREE.Vector3(this.cam.position.x - n.home.x, 0, this.cam.position.z - n.home.z).normalize().multiplyScalar(n.gain * 1.4);
        n.g.position.set(n.home.x + fwd.x, 2.0 + n.gain * 0.35 + (reduceMotion ? 0 : Math.sin(t * 0.9 + i) * 0.08) + (e - 1) * 2, n.home.z + fwd.z);
        n.g.lookAt(this.cam.position.x, n.g.position.y + (this.cam.position.y - n.g.position.y) * 0.55, this.cam.position.z);
        n.g.scale.setScalar(0.001 + e * (1 + n.gain * 0.1)); n.glow.material.opacity = 0.22 + n.gain * 0.5; n.beamB.material.uniforms.uGain.value = n.gain;
        v.set(n.g.position.x, n.g.position.y - 1.55, n.g.position.z);
      } else {
        const h = n.h * e; n.beam.scale.y = Math.max(0.001, h); n.beam.position.y = h / 2; n.glow.scale.y = Math.max(0.001, h); n.glow.position.y = h / 2;
        n.top.position.y = h + 0.05; n.cap.position.y = h + 0.05; const s = 1 + n.gain * 0.9 + (reduceMotion ? 0 : 0.08 * Math.sin(t * 2 + i)); n.top.scale.set(1.2 * s, 1.2 * s, 1);
        n.beam.material.uniforms.uGain.value = n.gain; n.glow.material.uniforms.uGain.value = n.gain * 0.6; n.arc.material.uniforms.uGain.value = Math.max(e * 0.6, n.gain); n.arc.material.uniforms.uTime.value = t + i * 0.7;
        n.base.scale.setScalar(1 + n.gain * 0.8 + (reduceMotion ? 0 : 0.15 * Math.sin(t * 1.6 + i)));
        v.set(n.g.position.x, h + 0.55, n.g.position.z);
      }
      v.project(this.cam); const x = (v.x * 0.5 + 0.5) * W, y = (-v.y * 0.5 + 0.5) * H;
      n.lab.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -100%)`; const sf = this.safe || { left: 0, top: 0 }; const shown = this.kind !== "read" && (this.wide || this.sel === i || (this.sel < 0 && i === 0)); n.lab.style.opacity = shown && v.z < 1 && grow > 0.6 && x > sf.left + 60 && (sf.right == null || x < sf.right - 60) && y > sf.top + 40 ? String(0.55 + n.gain * 0.45) : "0"; n.lab.classList.toggle("on", this.sel === i);
    });
    this.r.render(this.scene, this.cam);
  }
}

// ------------------------------------------------------------------ the panel
const svg = (d) => `<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const ICON = {
  place: svg('<path d="M12 21s-6-5.3-6-10.5A6 6 0 0 1 18 10.5C18 15.7 12 21 12 21z"/><circle cx="12" cy="10.5" r="2.2"/>'),
  park: svg('<path d="M12 3c-3.3 2.4-5 5.3-5 8.2A5 5 0 0 0 12 16a5 5 0 0 0 5-4.8C17 8.3 15.3 5.4 12 3z"/><path d="M12 9v12M9.5 12.5 12 15l2.5-2.5"/>'),
  botanical_garden: svg('<path d="M12 21v-8"/><path d="M12 13c0-4 3-6.5 7-6.5 0 4-3 6.5-7 6.5zM12 13c0-3.4-2.6-5.5-6-5.5 0 3.4 2.6 5.5 6 5.5z"/>'),
  library: svg('<path d="M4 20h16M6 17V8M10 17V8M14 17V8M18 17V8M3 8l9-5 9 5"/>'),
  book_store: svg('<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5zM4 20.5A2.5 2.5 0 0 0 6.5 23H20"/>'),
  museum: svg('<path d="M3 21h18M4 10h16M12 3 3 8h18zM6 10v8M10 10v8M14 10v8M18 10v8"/>'),
  coffee_shop: svg('<path d="M4 9h12v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5zM16 10h1.5a2.5 2.5 0 0 1 0 5H16M8 3c-.8 1.2.8 2 0 3.2M12 3c-.8 1.2.8 2 0 3.2"/>'),
  food: svg('<path d="M3 12h18a9 9 0 0 1-18 0zM7 8c0-1.5 1-1.5 1-3M12 8c0-1.5 1-1.5 1-3M17 8c0-1.5 1-1.5 1-3"/>'),
  read: svg('<path d="M12 6c-2-1.5-5-2-8-1.5V19c3-.5 6 0 8 1.5 2-1.5 5-2 8-1.5V4.5c-3-.5-6 0-8 1.5zM12 6v14.5"/>'),
};
ICON.cafe = ICON.coffee_shop; ICON.cultural_center = ICON.museum; ICON.record_store = svg('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.5"/><path d="M12 3a9 9 0 0 1 9 9"/>');
export function initAfter(ctx) {
  const { $, tr, L, esc, API, profileQS, goal, accent, openTab } = ctx;
  const canvas = $("#afcanvas"), labels = $("#aflabels");
  const scene = new AfterScene(canvas, labels);
  const st = { data: null, kind: "place", key: "", busy: false };
  const K = { place: "places", food: "food", read: "read" }, list = (d, k) => (d && d[K[k]]) || [];
  const cat = (s) => { const m = tr(L(), "af_cat." + s); return m && m !== "af_cat." + s ? m : String(s || "").replace(/_/g, " ").replace(/^./, c => c.toUpperCase()); };
  const fmt = (k, o) => String(tr(L(), k)).replace(/\{(\w+)\}/g, (_, x) => o[x] ?? "");
  function meta(x) {
    const bits = [];
    if (x.kind === "read") { if (x.year) bits.push(String(x.year)); bits.push(tr(L(), "af_book")); }
    else { if (x.kitchen) bits.push(fmt("af_kitchen", { k: x.kitchen })); else if (x.category) bits.push(cat(x.category)); if (x.km != null) bits.push(fmt("af_km", { n: x.km })); if (x.rating) bits.push("★ " + x.rating); }
    return bits.join("  ·  ");
  }
  function empty(msg, action) {
    $("#aflist").innerHTML = `<li class="afempty"><p>${esc(msg)}</p>${action ? `<button class="ghost small" data-afgo="${esc(action)}">${esc(tr(L(), "af_set_city"))}</button>` : ""}</li>`;
    scene.show(st.kind, [], null);
  }
  function render() {
    const d = st.data; const g = goal();
    document.querySelectorAll("#afseg button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.af === st.kind)));
    $("#afwhy").textContent = tr(L(), "af_goal." + g) || "";
    $("#afsent").textContent = tr(L(), "af_sent");
    if (!d) { $("#aflede").textContent = tr(L(), "af_lede_nocity"); $("#aflist").innerHTML = `<li class="afempty"><p class="afload">${esc(tr(L(), "af_loading"))}</p></li>`; return; }
    $("#aflede").textContent = d.city ? fmt(d.when === "tomorrow" ? "af_lede_tomorrow" : "af_lede_today", { city: d.city }) : tr(L(), "af_lede_nocity");
    if (d.reason === "no_favourites") return empty(tr(L(), "af_nofav"));
    const items = list(d, st.kind).map(x => ({ ...x, _meta: meta(x) }));
    document.querySelectorAll("#afseg button").forEach(b => { const n = list(d, b.dataset.af).length; b.querySelector("small").textContent = n ? String(n) : ""; });
    if (!items.length) {
      if (st.kind !== "read" && !d.city) return empty(tr(L(), "af_nocity"), "me");
      return empty(d.mode === "fixture" ? tr(L(), "af_offline") : fmt("af_none", { city: d.city || "" }));
    }
    $("#aflist").innerHTML = items.map((x, i) => {
      const why = (x.because || []).slice(0, 2).map(b => `<i>${esc(fmt("af_close", { f: b.name }))}</i>`).join("") || (x.close_to ? `<i>${esc(fmt("af_close", { f: x.close_to }))}</i>` : "");
      const pic = x.image ? `<span class="afimg" style="background-image:url('${esc(x.image)}')"></span>` : `<span class="afimg none">${ICON[x.kind === "place" ? (ICON[x.category] ? x.category : "place") : x.kind]}</span>`;
      const link = x.kind === "read" ? `https://www.google.com/search?tbm=bks&q=${encodeURIComponent(x.name || "")}` : x.map;
      return `<li class="afcard" data-i="${i}" style="--d:${i * 70}ms"><button class="afpick" data-i="${i}">${pic}<span class="aftext"><b>${esc(x.name)}</b><small>${esc(x._meta)}</small><span class="afbecause">${why}</span></span><span class="afmatch" title="${esc(tr(L(), "af_aff_note"))}">${(x.affinity || 0).toFixed(2)}<small>${esc(tr(L(), "af_match"))}</small></span></button><a class="afmap" href="${esc(link)}" target="_blank" rel="noopener">${esc(tr(L(), x.kind === "read" ? "af_find" : "af_map"))}</a></li>`;
    }).join("");
    scene._centre = d.centre; scene.show(st.kind, items, d.centre);
  }
  function pick(i, from) {
    document.querySelectorAll("#aflist .afcard").forEach(c => c.classList.toggle("on", +c.dataset.i === i));
    scene.select(i);
    if (from === "scene") { const c = document.querySelector(`#aflist .afcard[data-i="${i}"]`); if (c) c.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" }); }
  }
  scene.onPick = (i) => pick(i, "scene");
  $("#aflist").addEventListener("click", (e) => { const b = e.target.closest(".afpick"); if (b) pick(+b.dataset.i, "list"); const go = e.target.closest("[data-afgo]"); if (go) openTab(go.dataset.afgo); });
  $("#afseg").addEventListener("click", (e) => { const b = e.target.closest("button[data-af]"); if (!b) return; st.kind = b.dataset.af; render(); });
  async function load(force) {
    const qs = profileQS(); if (!qs) { st.data = { reason: "no_favourites" }; render(); return; }
    const g = goal(), key = qs + "|" + g;
    if (!force && key === st.key && st.data) { render(); return; }
    st.key = key; st.data = null; render();
    let d = null; try { d = await (await fetch(`${API}/api/after?${qs}&goal=${encodeURIComponent(g)}&hour=${new Date().getHours()}`)).json(); } catch {}
    if (st.key !== key) return;
    st.data = d || { reason: "no_results", places: [], food: [], read: [] };
    if (!list(st.data, st.kind).length) st.kind = ["place", "food", "read"].find(k => list(st.data, k).length) || st.kind;
    render();
  }
  return {
    open() { document.body.classList.add("aftermode"); scene.setAccent(accent()); scene.start(); load(false); },
    close() { document.body.classList.remove("aftermode"); scene.stop(); },
    relang() { if (st.data !== undefined) render(); },
    scene,
  };
}
