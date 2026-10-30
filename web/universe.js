// The start page: Reach's whole idea in one 3D picture. A person made of light at the centre; around them, eight
// worlds, one for each thing Reach does. Light flows from the person into every world (their taste, through Qloo).
// Point at a world and it wakes; click it and the camera flies there, a short real clip plays, and one button opens
// that part of the app. The frequency world is an instrument you can play right here.
import * as THREE from "three";
import { MeshSurfaceSampler } from "./vendor/MeshSurfaceSampler.js";
import { createInstrument, BANDS } from "./instrument.js";

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const small = () => window.innerWidth < 760;
const rtl = () => document.documentElement.dir === "rtl";
// the living portrait: a photograph (made with Kling) drawn in WebGL behind the worlds. Gold and teal pulses travel
// out from her brain along the nerves, the brain breathes light, the figure moves a little against the room (depth),
// and the ring of worlds orbits her head and passes behind it. focus: the brain's centre in the photograph (0..1).
const PHOTO = { src: "./assets/hero_portrait.jpg", focus: [0.68, 0.2975], head: [0.66, 0.335, 0.15, 0.2] };
const PHOTO_VS = `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;
const PHOTO_FS = `uniform sampler2D map; uniform vec2 uRes, uOff, uSize, uFocus, uMouse; uniform float uT, uDim, uFadeB; varying vec2 vUv;
  void main(){
    vec2 px = vec2(vUv.x * uRes.x, (1.0 - vUv.y) * uRes.y);
    vec2 uv = (px - uOff) / uSize;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) { gl_FragColor = vec4(0.0); return; }
    vec3 c0 = texture2D(map, vec2(uv.x, 1.0 - uv.y)).rgb;
    float l0 = dot(c0, vec3(0.299, 0.587, 0.114));
    vec2 uv2 = uv - uMouse * 0.007 * smoothstep(0.04, 0.45, l0);
    vec3 c = texture2D(map, vec2(uv2.x, 1.0 - uv2.y)).rgb;
    float lum = dot(c, vec3(0.299, 0.587, 0.114));
    vec2 q = (uv - uFocus) * vec2(uSize.x / uSize.y, 1.0);
    float d = length(q);
    float warm = smoothstep(0.03, 0.22, c.r - c.b) * smoothstep(0.18, 0.55, lum);
    float cool = smoothstep(0.03, 0.16, c.g - c.r) * smoothstep(0.12, 0.45, lum);
    float wave = pow(0.5 + 0.5 * sin(d * 24.0 - uT * 2.3), 9.0);
    float wave2 = pow(0.5 + 0.5 * sin(d * 11.0 - uT * 1.1 + 1.7), 12.0);
    float breath = 0.5 + 0.5 * sin(uT * 1.05);
    vec3 add = vec3(1.0, 0.78, 0.40) * warm * (wave * 0.6 + wave2 * 0.35) + vec3(0.35, 0.95, 0.88) * cool * (wave * 0.5 + wave2 * 0.3);
    add += vec3(1.0, 0.82, 0.52) * exp(-d * d * 55.0) * (0.05 + 0.09 * breath);
    float edge = mix(1.0, smoothstep(1.0, 0.8, uv.y), uFadeB);
    gl_FragColor = vec4((c + add) * uDim * edge, 1.0);
  }`;

export const WORLDS = [
  { id: "music", color: 0xe0b24e, clip: "talk", go: { tab: "talk" } },
  { id: "freq", color: 0x3fd1c0, clip: null, go: { tab: "talk", plate: true }, instrument: true },
  { id: "mood", color: 0xff9a6b, clip: null, img: "brain_glass", go: { tab: "feel" } },
  { id: "hands", color: 0xffd38a, clip: null, img: "neurons_close", go: { tab: "feel" } },
  { id: "breathe", color: 0x6ad0ff, clip: "deaf", go: { tab: "watch" } },
  { id: "after", color: 0x8fd6c2, clip: "map", go: { tab: "after" } },
  { id: "world", color: 0x7c8cff, clip: "lang", go: { slide: "world" } },
  { id: "care", color: 0xd7a6ff, clip: "council", go: { judge: true } },
];

const glow = (() => { const c = document.createElement("canvas"); c.width = c.height = 128; const g = c.getContext("2d"); const r = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(0.28, "rgba(255,255,255,.5)"); r.addColorStop(1, "rgba(255,255,255,0)"); g.fillStyle = r; g.fillRect(0, 0, 128, 128); return new THREE.CanvasTexture(c); })();
const sprite = (color, s, o = 1) => { const m = new THREE.Sprite(new THREE.SpriteMaterial({ map: glow, color, transparent: true, opacity: o, depthWrite: false, blending: THREE.AdditiveBlending })); m.scale.set(s, s, 1); return m; };
const pts = (positions, color, size, opacity = 1) => { const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return new THREE.Points(g, new THREE.PointsMaterial({ size, map: glow, color, transparent: true, opacity, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true })); };
const line = (a, b, color, o = 0.5) => new THREE.Line(new THREE.BufferGeometry().setFromPoints([a, b]), new THREE.LineBasicMaterial({ color, transparent: true, opacity: o, blending: THREE.AdditiveBlending }));

// ---------------------------------------------------------------- the person of light
function person() {
  const g = new THREE.Group(); const mat = new THREE.MeshBasicMaterial();
  const parts = [ // [radius, length, x, y, z, rotZ]
    [0.34, 0.0, 0, 3.05, 0, 0], [0.12, 0.18, 0, 2.62, 0, 0], [0.42, 0.9, 0, 1.85, 0, 0], [0.36, 0.25, 0, 1.08, 0, 0],
    [0.12, 0.62, -0.62, 2.05, 0, 0.35], [0.1, 0.6, -0.85, 1.42, 0, 0.12], [0.12, 0.62, 0.62, 2.05, 0, -0.35], [0.1, 0.6, 0.85, 1.42, 0, -0.12],
    [0.16, 0.78, -0.22, 0.32, 0, 0.04], [0.13, 0.74, -0.25, -0.62, 0, 0], [0.16, 0.78, 0.22, 0.32, 0, -0.04], [0.13, 0.74, 0.25, -0.62, 0, 0]];
  const out = [];
  for (const [r, l, x, y, z, rz] of parts) {
    const m = new THREE.Mesh(l ? new THREE.CapsuleGeometry(r, l, 6, 14) : new THREE.SphereGeometry(r, 24, 16), mat); m.position.set(x, y, z); m.rotation.z = rz; m.updateMatrixWorld();
    const s = new MeshSurfaceSampler(m).build(); const n = Math.round((r * (l + r * 2)) * (small() ? 900 : 1700)); const p = new THREE.Vector3();
    for (let i = 0; i < n; i++) { s.sample(p); p.applyMatrix4(m.matrixWorld); out.push(p.x, p.y - 1.2, p.z); }
  }
  const body = pts(out, 0xffd58a, 0.058, 1); g.add(body);
  const heart = sprite(0xffb36b, 1.9, 1); heart.position.set(0, 0.75, 0.1); g.add(heart);
  const halo = sprite(0xffe7a8, 8, 0.22); halo.position.set(0, 0.4, -0.5); g.add(halo);
  g.userData = { body, heart };
  return g;
}

// ---------------------------------------------------------------- the eight worlds
function makeWorld(id, color) {
  const g = new THREE.Group(); const u = { t: 0 };
  if (id === "music") {             // a taste constellation: favourites and the artists Qloo links to them
    const nodes = []; for (let i = 0; i < 16; i++) nodes.push(new THREE.Vector3().randomDirection().multiplyScalar(0.35 + Math.random() * 0.6));
    nodes.forEach((p, i) => { const s = sprite(i < 3 ? 0xffe0a0 : color, i < 3 ? 0.55 : 0.3, 0.95); s.position.copy(p); g.add(s); });
    nodes.forEach((p, i) => { const near = nodes.map((q, j) => [q.distanceTo(p), j]).filter(x => x[1] !== i).sort((a, b) => a[0] - b[0]).slice(0, 2); near.forEach(([, j]) => { if (j > i) g.add(line(p, nodes[j], color, 0.35)); }); });
    u.spin = 0.25;
  } else if (id === "freq") {       // the plate with sand on its nodal lines
    const N = 70, P = []; for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) { const a = -1 + 2 * x / (N - 1), b = -1 + 2 * y / (N - 1); if (a * a + b * b <= 1) P.push(a, b); }
    const pos = new Float32Array(P.length / 2 * 3); for (let i = 0; i < P.length / 2; i++) { pos[i * 3] = P[i * 2] * 0.95; pos[i * 3 + 2] = P[i * 2 + 1] * 0.95; }
    const pg = new THREE.BufferGeometry(); pg.setAttribute("position", new THREE.BufferAttribute(pos, 3)); const col = new Float32Array(pos.length); pg.setAttribute("color", new THREE.BufferAttribute(col, 3));
    const sand = new THREE.Points(pg, new THREE.PointsMaterial({ size: 0.05, map: glow, vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })); g.add(sand);
    const rim = new THREE.Mesh(new THREE.TorusGeometry(0.98, 0.012, 6, 96), new THREE.MeshBasicMaterial({ color: 0xc9a24a })); rim.rotation.x = Math.PI / 2; g.add(rim);
    g.rotation.x = 0.55; u.sand = sand; u.P = P; u.mode = [4, 7]; u.from = [4, 7]; u.mix = 1;
  } else if (id === "mood") {       // the mood dial and a voice line
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.75, 0.018, 8, 120), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.8 })); g.add(ring);
    const dot = sprite(0xffffff, 0.35); g.add(dot); u.dot = dot;
    const wpos = new Float32Array(64 * 3); const wg = new THREE.BufferGeometry(); wg.setAttribute("position", new THREE.BufferAttribute(wpos, 3));
    const wave = new THREE.Line(wg, new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending })); g.add(wave); u.wave = wave;
    ["#ff9a6b", "#3fd1c0", "#7c8cff", "#e3b23c"].forEach((c, i) => { const s = sprite(c, 0.22, 0.9); s.position.set(Math.cos(i * Math.PI / 2) * 0.75, Math.sin(i * Math.PI / 2) * 0.75, 0); g.add(s); });
  } else if (id === "hands") {      // 21 landmarks of a hand making the "next song" sign
    const L = [[0, -0.9], [-0.28, -0.7], [-0.45, -0.45], [-0.58, -0.22], [-0.7, -0.02], [-0.18, -0.25], [-0.26, 0.15], [-0.32, 0.45], [-0.38, 0.75], [0.0, -0.22], [0.06, 0.2], [0.11, 0.52], [0.16, 0.85],
               [0.18, -0.25], [0.26, 0.0], [0.24, -0.18], [0.2, -0.3], [0.33, -0.32], [0.42, -0.12], [0.38, -0.3], [0.32, -0.42]];
    const LINKS = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12], [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [0, 17], [17, 18], [18, 19], [19, 20]];
    const V = L.map(([x, y]) => new THREE.Vector3(x * 0.9, y * 0.9, 0)); V.forEach((p, i) => { const s = sprite(i === 8 || i === 12 ? 0xffffff : color, i === 8 || i === 12 ? 0.3 : 0.18); s.position.copy(p); g.add(s); });
    LINKS.forEach(([a, b]) => g.add(line(V[a], V[b], color, 0.85)));
  } else if (id === "breathe") {    // six breaths a minute
    const core = new THREE.Mesh(new THREE.SphereGeometry(0.45, 32, 20), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.55 })); g.add(core);
    const aura = sprite(color, 2.6, 0.6); g.add(aura); u.core = core; u.aura = aura;
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.85, 0.01, 6, 100), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.5 })); ring.rotation.x = Math.PI / 2; g.add(ring); u.ring = ring;
  } else if (id === "after") {      // a small night city with columns of light
    for (let i = 0; i < 26; i++) { const h = 0.08 + Math.random() * 0.4, x = (Math.random() - 0.5) * 1.6, z = (Math.random() - 0.5) * 1.6; if (x * x + z * z > 0.7) continue;
      const b = new THREE.Mesh(new THREE.BoxGeometry(0.09, h, 0.09), new THREE.MeshBasicMaterial({ color: 0x1d3a3a })); b.position.set(x, h / 2 - 0.3, z); g.add(b);
      const e = new THREE.LineSegments(new THREE.EdgesGeometry(b.geometry), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.35 })); e.position.copy(b.position); g.add(e); }
    u.pillars = [];
    [[0.45, 0.2], [-0.4, 0.35], [0.1, -0.5], [-0.2, -0.1]].forEach(([x, z], i) => { const h = 0.7 + i * 0.15;
      const c = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, h, 8, 1, true), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending })); c.position.set(x, h / 2 - 0.3, z); g.add(c);
      const s = sprite(color, 0.35); s.position.set(x, h - 0.3, z); g.add(s); u.pillars.push(s); });
    g.rotation.x = 0.35;
  } else if (id === "world") {      // a dotted globe, with scripts of the world going round it
    const P = [], n = small() ? 600 : 1100; for (let i = 0; i < n; i++) { const y = 1 - (i / (n - 1)) * 2, r = Math.sqrt(1 - y * y), th = i * 2.39996; P.push(Math.cos(th) * r * 0.75, y * 0.75, Math.sin(th) * r * 0.75); }
    g.add(pts(P, color, 0.035, 0.85));
    const glyphs = ["A", "ف", "中", "ñ", "अ", "日", "한", "Ж", "ع", "ü"]; u.glyphs = [];
    glyphs.forEach((ch, i) => { const c = document.createElement("canvas"); c.width = c.height = 64; const x = c.getContext("2d"); x.fillStyle = "#e6ecff"; x.font = "40px 'Noto Sans', system-ui, sans-serif"; x.textAlign = "center"; x.textBaseline = "middle"; x.fillText(ch, 32, 34);
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false })); s.scale.set(0.26, 0.26, 1); g.add(s); u.glyphs.push({ s, a: i / glyphs.length * Math.PI * 2 }); });
    u.spin = 0.18;
  } else if (id === "care") {       // a hash chain: each block holds the one before it
    u.blocks = [];
    for (let i = 0; i < 5; i++) { const b = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(0.28, 0.28, 0.28)), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.9 }));
      b.position.set(-0.8 + i * 0.4, Math.sin(i) * 0.12, 0); g.add(b); u.blocks.push(b); if (i) g.add(line(u.blocks[i - 1].position, b.position, color, 0.5)); }
    const pulse = sprite(0xffffff, 0.35); g.add(pulse); u.pulse = pulse;
  }
  const hit = new THREE.Mesh(new THREE.SphereGeometry(1.15, 12, 8), new THREE.MeshBasicMaterial({ visible: false })); g.add(hit);
  const halo = sprite(color, 3.4, 0.12); g.add(halo);
  g.userData = { id, u, hit, halo, color };
  return g;
}

function animateWorld(w, t, awake) {
  const { id, u, halo } = w.userData; halo.material.opacity = 0.1 + awake * 0.22; const k = reduceMotion ? 0 : t;
  if (u.spin) w.rotation.y = k * u.spin;
  if (id === "freq") {
    u.mix = Math.min(1, u.mix + 0.015); const e = u.mix * u.mix * (3 - 2 * u.mix); const col = u.sand.geometry.attributes.color, pos = u.sand.geometry.attributes.position, P = u.P;
    const [a1, b1] = u.from, [a2, b2] = u.mode, c = new THREE.Color(w.userData.color), sandC = new THREE.Color(0xfff0c8);
    for (let i = 0; i < P.length / 2; i++) { const x = P[i * 2], y = P[i * 2 + 1];
      const z1 = Math.cos(a1 * Math.PI * x) * Math.cos(b1 * Math.PI * y) - Math.cos(b1 * Math.PI * x) * Math.cos(a1 * Math.PI * y);
      const z2 = Math.cos(a2 * Math.PI * x) * Math.cos(b2 * Math.PI * y) - Math.cos(b2 * Math.PI * x) * Math.cos(a2 * Math.PI * y);
      const z = z1 * (1 - e) + z2 * e; const node = 1 - Math.min(1, Math.abs(z) / 0.2);
      pos.array[i * 3 + 1] = z * 0.06 * (0.7 + 0.3 * Math.sin(k * 1.3));
      const m = node * node; col.array[i * 3] = c.r * 0.15 + sandC.r * m; col.array[i * 3 + 1] = c.g * 0.15 + sandC.g * m; col.array[i * 3 + 2] = c.b * 0.15 + sandC.b * m; }
    col.needsUpdate = true; pos.needsUpdate = true; w.rotation.y = k * 0.2;
  } else if (id === "mood") {
    const a = k * 0.6; u.dot.position.set(Math.cos(a) * 0.4, Math.sin(a * 1.3) * 0.4, 0.02);
    const p = u.wave.geometry.attributes.position; for (let i = 0; i < 64; i++) { const x = -0.6 + i / 63 * 1.2; p.array[i * 3] = x; p.array[i * 3 + 1] = -0.05 + Math.sin(i * 0.5 + k * 5) * 0.12 * Math.sin(i / 63 * Math.PI) * (0.6 + 0.4 * Math.sin(k)); p.array[i * 3 + 2] = 0; }
    p.needsUpdate = true;
  } else if (id === "hands") { w.rotation.z = Math.sin(k * 0.9) * 0.12; w.position.y = w.userData.baseY + Math.sin(k * 1.2) * 0.06; }
  else if (id === "breathe") { const br = 0.5 + 0.5 * Math.sin(k * Math.PI * 2 / 10); u.core.scale.setScalar(0.75 + br * 0.5); u.aura.material.opacity = 0.3 + br * 0.5; u.ring.scale.setScalar(0.9 + br * 0.3); }
  else if (id === "after") { u.pillars.forEach((s, i) => { s.material.opacity = 0.6 + 0.4 * Math.sin(k * 2 + i); }); w.rotation.y = k * 0.15; }
  else if (id === "world") { u.glyphs.forEach((gl) => { const a = gl.a + k * 0.4; gl.s.position.set(Math.cos(a) * 1.0, Math.sin(a * 2) * 0.25, Math.sin(a) * 1.0); }); }
  else if (id === "care") { const f = (k * 0.5) % 1; const i = Math.floor(f * 4), r = f * 4 - i; const a = u.blocks[i].position, b = u.blocks[Math.min(4, i + 1)].position; u.pulse.position.lerpVectors(a, b, r);
    u.blocks.forEach((bl, j) => { bl.rotation.y = k * 0.4 + j; bl.rotation.x = k * 0.25; }); }
}

// ---------------------------------------------------------------- the scene and the page around it
export function initUniverse({ root, tr, onOpen, onStart }) {
  const canvas = root.querySelector("#uni"), labels = root.querySelector("#unilabels"), info = root.querySelector("#uni-info");
  let r; try { r = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" }); } catch { root.classList.add("no3d"); return { start() {}, stop() {}, relang() {} }; }
  r.setPixelRatio(Math.min(small() ? 1.5 : 2, devicePixelRatio || 1)); r.setClearColor(0x000000, 0);
  const scene = new THREE.Scene(); scene.fog = new THREE.FogExp2(0x04050b, 0.018);
  const cam = new THREE.PerspectiveCamera(42, 1, 0.1, 400);
  // the sky
  const S = []; for (let i = 0; i < (small() ? 1400 : 2600); i++) { const v = new THREE.Vector3().randomDirection().multiplyScalar(60 + Math.random() * 80); S.push(v.x, v.y, v.z); }
  const sky = pts(S, 0xb8c4ff, 0.35, 0.7); scene.add(sky);
  const neb = sprite(0x3b2a7a, 70, 0.22); neb.position.set(10, 6, -40); scene.add(neb); const neb2 = sprite(0x0f5a5a, 60, 0.18); neb2.position.set(-30, -10, -50); scene.add(neb2);
  // the person and the ring of worlds
  const stage = new THREE.Group(); scene.add(stage);
  const you = person(); you.scale.setScalar(1.3); stage.add(you);
  // the portrait, when its picture loads: drawn first, full screen; the particle figure gives way to her
  const photo = { ready: false, dim: 1, mouse: new THREE.Vector2(), scale: 1, pos: new THREE.Vector3() };
  { const tex = new THREE.TextureLoader().load(PHOTO.src, (t) => { photo.img = [t.image.width, t.image.height]; photo.ready = true; root.classList.add("photo"); sky.material.opacity = 0.22; neb.visible = neb2.visible = false;
      you.userData.body.visible = false; you.children.forEach(c => { if (c !== you.userData.heart) c.visible = false; }); });
    tex.colorSpace = THREE.SRGBColorSpace; tex.generateMipmaps = false; tex.minFilter = THREE.LinearFilter;
    photo.u = { map: { value: tex }, uRes: { value: new THREE.Vector2(1, 1) }, uOff: { value: new THREE.Vector2() }, uSize: { value: new THREE.Vector2(1, 1) },
                uFocus: { value: new THREE.Vector2(PHOTO.focus[0], PHOTO.focus[1]) }, uMouse: { value: new THREE.Vector2() }, uT: { value: 0 }, uDim: { value: 1 }, uFadeB: { value: 0 } };
    photo.bg = new THREE.Scene(); photo.cam = new THREE.Camera();
    photo.bg.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({ uniforms: photo.u, vertexShader: PHOTO_VS, fragmentShader: PHOTO_FS, depthTest: false, depthWrite: false }))); }
  // her head and neck, invisible: they only hide what passes behind them, so the ring goes round her
  const occ = new THREE.MeshBasicMaterial({ colorWrite: false });
  const occHead = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 24), occ), occNeck = new THREE.Mesh(new THREE.CylinderGeometry(1, 1.25, 1, 24), occ);
  occHead.renderOrder = occNeck.renderOrder = -1; occHead.visible = occNeck.visible = false; scene.add(occHead, occNeck);
  const ring = new THREE.Group(); stage.add(ring);
  const R = 5.6, worlds = WORLDS.map((w, i) => { const g = makeWorld(w.id, w.color); const a = i / WORLDS.length * Math.PI * 2; g.userData.a = a; g.userData.baseY = 0.6 + Math.sin(i * 1.7) * 0.6; ring.add(g); return g; });
  const orbit = new THREE.Mesh(new THREE.TorusGeometry(R, 0.008, 6, 240), new THREE.MeshBasicMaterial({ color: 0xc9a24a, transparent: true, opacity: 0.28 })); orbit.rotation.x = Math.PI / 2; orbit.position.y = 0.6; stage.add(orbit);
  // light flowing from the person into every world
  const flows = worlds.map((w) => ({ w, curve: null }));
  const FN = small() ? 260 : 520, fpos = new Float32Array(FN * 3), fcol = new Float32Array(FN * 3), fmeta = [];
  for (let i = 0; i < FN; i++) { const k = i % worlds.length; fmeta.push({ k, t: Math.random(), v: 0.08 + Math.random() * 0.1 }); const c = new THREE.Color(worlds[k].userData.color); fcol.set([c.r, c.g, c.b], i * 3); }
  const fg = new THREE.BufferGeometry(); fg.setAttribute("position", new THREE.BufferAttribute(fpos, 3)); fg.setAttribute("color", new THREE.BufferAttribute(fcol, 3));
  stage.add(new THREE.Points(fg, new THREE.PointsMaterial({ size: 0.09, map: glow, vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })));
  // labels: real buttons, so a keyboard and a screen reader reach every world
  labels.innerHTML = WORLDS.map((w, i) => `<button class="ul" data-w="${i}" style="--c:#${w.color.toString(16).padStart(6, "0")}"><b></b><span></span></button>`).join("");
  const labelEls = [...labels.querySelectorAll(".ul")];
  function text() { labelEls.forEach((el, i) => { el._w = 0; el.querySelector("b").textContent = tr("u_" + WORLDS[i].id + "_t"); el.querySelector("span").textContent = tr("u_" + WORLDS[i].id + "_s"); }); if (focus >= 0) fillInfo(focus); if (inst) inst.relang(); }
  // camera: an overview that drifts, or a close look at one world
  let focus = -1, hover = -1, az = 0.3, running = false, inst = null, wide = true, shot = null;
  const camPos = new THREE.Vector3(0, 4.2, 17), camLook = new THREE.Vector3(0, 0.6, 0), wantPos = camPos.clone(), wantLook = camLook.clone();
  let mx = 0, my = 0; addEventListener("pointermove", (e) => { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; }, { passive: true });
  r.autoClear = false;
  function fit() { const w = canvas.clientWidth, h = canvas.clientHeight; if (!w || !h) return; r.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix(); wide = w / h > 1.2; }
  new ResizeObserver(fit).observe(canvas); fit();
  const ray = new THREE.Raycaster(), m2 = new THREE.Vector2();
  function pickAt(e) { const rc = canvas.getBoundingClientRect(); m2.set(((e.clientX - rc.left) / rc.width) * 2 - 1, -((e.clientY - rc.top) / rc.height) * 2 + 1); ray.setFromCamera(m2, cam);
    const h = ray.intersectObjects(worlds.map(w => w.userData.hit), false)[0]; return h ? worlds.indexOf(h.object.parent) : -1; }
  canvas.addEventListener("pointermove", (e) => { hover = pickAt(e); canvas.style.cursor = hover >= 0 ? "pointer" : ""; });
  canvas.addEventListener("click", (e) => { const i = pickAt(e); if (i >= 0) open(i); else if (focus >= 0) back(); });
  labels.addEventListener("click", (e) => { const b = e.target.closest(".ul"); if (b) open(+b.dataset.w); });
  labels.addEventListener("pointerover", (e) => { const b = e.target.closest(".ul"); hover = b ? +b.dataset.w : -1; });
  labels.addEventListener("pointerout", () => { hover = -1; });
  addEventListener("keydown", (e) => { if (e.key === "Escape" && focus >= 0 && !root.hidden) back(); });
  function fillInfo(i) {
    const w = WORLDS[i];
    info.querySelector(".ui-k").textContent = tr("u_" + w.id + "_s"); info.querySelector("h2").textContent = tr("u_" + w.id + "_t"); info.querySelector("p").textContent = tr("u_" + w.id + "_d");
    info.querySelector(".ui-open").textContent = tr(w.go.judge ? "u_open_judge" : "u_open");
    info.style.setProperty("--c", "#" + w.color.toString(16).padStart(6, "0"));
  }
  function open(i) {
    focus = i; fillInfo(i); root.classList.add("focused"); info.hidden = false; info.dataset.w = WORLDS[i].id;
    const media = info.querySelector(".ui-media"); media.innerHTML = ""; if (inst) { inst.stop(); inst.pause(); inst = null; }
    if (WORLDS[i].instrument) { const box = document.createElement("div"); media.appendChild(box); inst = createInstrument(box, { tr, compact: true, onBand: (b) => { const u = worlds[1].userData.u; u.from = u.mode; u.mode = b.mode; u.mix = 0; } }); inst.start(); }
    else if (WORLDS[i].img) { media.innerHTML = `<img class="ui-photo" src="./assets/${WORLDS[i].img}.jpg" alt="">`; }
    else if (WORLDS[i].clip) { media.innerHTML = `<video src="./assets/reel/${WORLDS[i].clip}.webm" poster="./assets/reel/${WORLDS[i].clip}.jpg" muted loop playsinline autoplay></video>`; const v = media.querySelector("video"); v.play().catch(() => {}); }
    labelEls.forEach((el, j) => el.classList.toggle("dim", j !== i));
    info.querySelector(".ui-open").focus({ preventScroll: true });
  }
  function back() { focus = -1; root.classList.remove("focused"); info.hidden = true; if (inst) { inst.stop(); inst.pause(); inst = null; } info.querySelector(".ui-media").innerHTML = ""; labelEls.forEach(el => el.classList.remove("dim")); }
  info.querySelector(".ui-back").addEventListener("click", back);
  info.querySelector(".ui-open").addEventListener("click", () => { if (focus >= 0) { const go = WORLDS[focus].go; if (inst) inst.stop(); onOpen(go); } });
  const v3 = new THREE.Vector3(), t0 = performance.now();
  function frame() {
    if (!running) return; requestAnimationFrame(frame);
    const t = (performance.now() - t0) / 1000, k = reduceMotion ? 0 : t;
    if (focus < 0 && !reduceMotion) az += 0.0009;
    worlds.forEach((w, i) => { const a = w.userData.a + az; w.position.set(Math.cos(a) * R, w.userData.baseY + (reduceMotion ? 0 : Math.sin(t * 0.6 + i) * 0.12), Math.sin(a) * R);
      const awake = i === focus || i === hover ? 1 : 0; w.userData.awake = (w.userData.awake || 0) + (awake - (w.userData.awake || 0)) * 0.1;
      w.scale.setScalar(1 + w.userData.awake * 0.18); animateWorld(w, t, w.userData.awake); });
    you.userData.body.material.opacity = 0.88 + 0.12 * Math.sin(k * 1.3); you.userData.heart.material.opacity = 0.6 + 0.35 * Math.sin(k * 2.4); you.rotation.y = Math.sin(k * 0.2) * 0.25;
    // flows: from the person's heart, up and over, into each world
    const heart = new THREE.Vector3(0, 0.98, 0);
    for (let i = 0; i < FN; i++) { const m = fmeta[i]; m.t = (m.t + m.v / 60) % 1; const w = worlds[m.k].position; const mid = heart.clone().lerp(w, 0.5); mid.y += 1.6;
      const q = 1 - m.t; v3.set(q * q * heart.x + 2 * q * m.t * mid.x + m.t * m.t * w.x, q * q * heart.y + 2 * q * m.t * mid.y + m.t * m.t * w.y, q * q * heart.z + 2 * q * m.t * mid.z + m.t * m.t * w.z);
      fpos[i * 3] = v3.x; fpos[i * 3 + 1] = v3.y; fpos[i * 3 + 2] = v3.z; }
    fg.attributes.position.needsUpdate = true;
    // camera
    const shift = photo.ready ? 0 : wide ? (rtl() ? -4.7 : 4.7) : 0;                   // the copy is on the left on wide screens (right in Persian and Arabic): the universe sits on the other side
    if (focus >= 0) {   // fly out beyond the world and look back in at it (the person behind it); the card covers the left (or the bottom on a phone)
      const wp = worlds[focus].getWorldPosition(new THREE.Vector3()); const dir = wp.clone().setY(0).normalize(); const side = new THREE.Vector3(-dir.z, 0, dir.x);
      const flat = WORLDS[focus].id === "freq", D = wide ? 4.6 : 9.5, up = flat ? 2.4 : 1.1;
      wantPos.copy(wp).addScaledVector(dir, D).add(new THREE.Vector3(0, up, 0));
      wantLook.copy(wp).addScaledVector(side, wide ? (rtl() ? -1.35 : 1.35) : 0).add(new THREE.Vector3(0, wide ? 0 : -3.4, 0)); }
    else { const ph = !wide && canvas.clientHeight > canvas.clientWidth; const d = ph ? 33 : small() ? 21 : 19.5;
      wantPos.set(-shift + mx * 1.4, (ph ? 15 : photo.ready ? 9.5 : 4.4) - my * 1.2, d); wantLook.set(-shift, ph ? -7.5 : 0.5, 0); }
    camPos.lerp(wantPos, 0.045); camLook.lerp(wantLook, 0.05); cam.position.copy(camPos); cam.lookAt(camLook);
    if (shot) shot(t, cam);                                          // a scripted camera, for rendering the film and stills (scripts/render_media.js)
    if (photo.ready) placePhoto(k);
    // labels follow their worlds
    const W = canvas.clientWidth, H = canvas.clientHeight;
    const hero = photo.ready && wide && focus < 0 ? heroBox() : null;     // over the portrait, a label never sits on the headline or the buttons
    worlds.forEach((w, i) => { w.getWorldPosition(v3); v3.y -= 1.25; v3.project(cam); const el = labelEls[i]; let vis = v3.z < 1 && Math.abs(v3.x) < 1.05 && Math.abs(v3.y) < 1.05;
      if (hero && vis) { const lx = (v3.x * 0.5 + 0.5) * W, ly = (-v3.y * 0.5 + 0.5) * H, hw2 = (el._w || 120) / 2; if (lx - hw2 < hero.right + 12 && ly > hero.top - 20 && ly < hero.bottom) vis = false; }
      const hw = (el._w || (el._w = el.offsetWidth || 120)) / 2, px = Math.min(W - hw - 6, Math.max(hw + 6, (v3.x * 0.5 + 0.5) * W));   // never cut off at the screen's edge
      el.style.transform = `translate(${px.toFixed(1)}px, ${((-v3.y * 0.5 + 0.5) * H).toFixed(1)}px) translate(-50%, 0)`; el.style.opacity = vis ? (focus >= 0 && focus !== i ? "0.25" : "1") : "0"; el.classList.toggle("on", i === hover || i === focus); });
    r.clear(); if (photo.ready) r.render(photo.bg, photo.cam); r.render(scene, cam);
  }
  // the photograph covers the screen (its right edge kept on wide screens, centred on her head on narrow ones);
  // the stage sits where her brain is, scaled so the ring of worlds circles her head; worlds behind her fade
  const camDir = new THREE.Vector3(), tmp = new THREE.Vector3();
  let heroAt = 0, heroRect = null; const heroEl = root.querySelector(".wl-hero");
  function heroBox() { const now = performance.now(); if (!heroRect || now - heroAt > 500) { heroAt = now; const b = heroEl && heroEl.getBoundingClientRect(); heroRect = b && { right: b.left + Math.min(b.width, 620), top: b.top + 60, bottom: b.bottom - 40 }; } return heroRect; }
  function placePhoto(k) {
    const W = canvas.clientWidth, H = canvas.clientHeight, [iw, ih] = photo.img, narrow = W / H < 1.15;
    const s = narrow ? Math.max(W / iw, H * 0.6 / ih) : Math.max(W / iw, H / ih), dw = iw * s, dh = ih * s;   // a phone: her head fills the top, the copy sits below
    const offX = narrow ? Math.min(0, Math.max(W - dw, W * 0.5 - PHOTO.focus[0] * dw)) : W - dw;
    const offY = narrow ? 0 : (H - dh) * 0.2;
    const u = photo.u; u.uFadeB.value = narrow ? 1 : 0; u.uRes.value.set(W, H); u.uOff.value.set(offX, offY); u.uSize.value.set(dw, dh); u.uT.value = k;
    photo.mouse.lerp(new THREE.Vector2(mx, my), 0.06); u.uMouse.value.copy(photo.mouse);
    photo.dim += ((focus >= 0 ? 0.32 : 1) - photo.dim) * 0.06; u.uDim.value = photo.dim;
    if (focus >= 0) return;                                           // a world is open: the camera flies, the stage stays where it is
    const Fx = offX + PHOTO.focus[0] * dw, Fy = offY + PHOTO.focus[1] * dh;
    const dist = camPos.distanceTo(camLook), upp = 2 * dist * Math.tan(THREE.MathUtils.degToRad(cam.fov / 2)) / H;   // world units per pixel at the stage
    const ndc = tmp.set(Fx / W * 2 - 1, -(Fy / H * 2 - 1), 0.5).unproject(cam).sub(cam.position).normalize();
    const target = cam.position.clone().addScaledVector(ndc, dist);
    const S = THREE.MathUtils.clamp((narrow ? 0.43 : 0.27) * W * upp / R, 0.3, 1.6); photo.scale += (S - photo.scale) * 0.2;
    stage.scale.setScalar(photo.scale);
    photo.pos.copy(target).sub(new THREE.Vector3(0, 0.98 * photo.scale, 0)); stage.position.lerp(photo.pos, 0.25);
    // the occluders: her head round the brain, her neck below it, sized from the photograph
    const [hx, hy, hr, nr] = PHOTO.head, Hx = offX + hx * dw, Hy = offY + hy * dh;
    const hp = cam.position.clone().addScaledVector(tmp.set(Hx / W * 2 - 1, -(Hy / H * 2 - 1), 0.5).unproject(cam).sub(cam.position).normalize(), dist + 0.6);
    occHead.position.copy(hp); occHead.scale.set(hr * dw * upp, hr * dw * upp * 1.2, hr * dw * upp); occHead.visible = true;
    const Nx = offX + (hx + 0.015) * dw, Ny = offY + 0.8 * dh, np = cam.position.clone().addScaledVector(tmp.set(Nx / W * 2 - 1, -(Ny / H * 2 - 1), 0.5).unproject(cam).sub(cam.position).normalize(), dist + 0.6);
    occNeck.position.copy(hp).lerp(np, 0.5); occNeck.scale.set(nr * 0.5 * dw * upp, hp.distanceTo(np) * 1.2, nr * 0.5 * dw * upp); occNeck.lookAt(cam.position); occNeck.rotateX(Math.PI / 2);
    // worlds behind her head are quieter
    cam.getWorldDirection(camDir);
    worlds.forEach((w) => { w.getWorldPosition(tmp); const behind = THREE.MathUtils.smoothstep(tmp.sub(stage.position).dot(camDir) / (R * photo.scale), -0.3, 0.6);
      const f = 1 - 0.6 * behind; if (!w.userData.mats) { w.userData.mats = []; w.traverse(o => { if (o.material && o.material.transparent) w.userData.mats.push([o.material, o.material.opacity]); }); }
      if (Math.abs((w.userData.f || 1) - f) > 0.01) { w.userData.f = f; w.userData.mats.forEach(([m, o]) => { m.opacity = o * f; }); } });
  }
  text();
  return { setShot(fn) { shot = fn; }, start() { if (running) return; running = true; fit(); requestAnimationFrame(frame); }, stop() { running = false; if (inst) { inst.stop(); inst.pause(); } }, relang: text, open, back };
}
