// The film: one WebGL stage behind the whole page. Sets (human, neurons, genome, earth,
// galaxy) live at the origin and are cross-faded; the camera dollies between keyframes
// driven by scroll, so scrolling reads as cuts in a film rather than a web page.
import * as THREE from "three";
import { MeshSurfaceSampler } from "./vendor/MeshSurfaceSampler.js";

export const GOLD = 0xc9a24a, TEAL = 0x3fd1c0, IVORY = 0xede7da, RED = 0xd64545;
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const isSmall = window.innerWidth < 900;
const Q = isSmall ? 0.5 : 1;           // particle budget multiplier

const spriteTex = (() => {
  const c = document.createElement("canvas"); c.width = c.height = 64; const g = c.getContext("2d");
  const r = g.createRadialGradient(32, 32, 0, 32, 32, 32); r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(0.35, "rgba(255,255,255,0.55)"); r.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = r; g.fillRect(0, 0, 64, 64); const t = new THREE.CanvasTexture(c); return t;
})();

function pointsMat(size, opacity = 1, color = 0xffffff) {
  return new THREE.PointsMaterial({ size, map: spriteTex, vertexColors: true, transparent: true, opacity, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true, color });
}
function starfield(n, radius) {
  const g = new THREE.BufferGeometry(), pos = new Float32Array(n * 3), col = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const v = new THREE.Vector3().randomDirection().multiplyScalar(radius * (0.5 + 0.5 * Math.random())); pos.set([v.x, v.y, v.z], i * 3);
    const k = Math.random(); col.set(k < 0.15 ? [1, 0.85, 0.6] : k < 0.3 ? [0.6, 0.9, 1] : [0.85, 0.85, 0.9], i * 3);
  }
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  return new THREE.Points(g, pointsMat(0.9, 0.8));
}
const ease = (k) => k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;

// ------------------------------------------------------------------ sets
class HumanSet {
  constructor() {
    this.group = new THREE.Group();
    // a figure of capsules, sampled into light
    const mat = new THREE.MeshBasicMaterial();
    const parts = [
      [0.46, 0.12, 0, 7.25, 0, 0, 0, 0],            // head
      [0.17, 0.22, 0, 6.6, 0, 0, 0, 0],             // neck
      [0.8, 1.5, 0, 5.15, 0, 0, 0, 0],              // torso
      [0.7, 0.7, 0, 3.75, 0, 0, 0, 0],              // hips
      [0.24, 2.3, -1.2, 4.55, 0, 0, 0, -0.16],      // arms, hanging slightly out
      [0.24, 2.3, 1.2, 4.55, 0, 0, 0, 0.16],
      [0.3, 2.7, -0.4, 1.65, 0, 0, 0, -0.04],       // legs
      [0.3, 2.7, 0.4, 1.65, 0, 0, 0, 0.04],
    ];
    const samples = [];
    for (const [r, len, x, y, z, rx, ry, rz] of parts) {
      const geo = new THREE.CapsuleGeometry(r, len, 6, 14); const m = new THREE.Mesh(geo, mat);
      m.position.set(x, y, z); m.rotation.set(rx, ry, rz); m.updateMatrixWorld();
      const sampler = new MeshSurfaceSampler(m).build(); const n = Math.floor(2200 * Q * (r * len + 0.3));
      const p = new THREE.Vector3();
      for (let i = 0; i < n; i++) { sampler.sample(p); p.applyMatrix4(m.matrixWorld); samples.push(p.x, p.y, p.z); }
    }
    const N = samples.length / 3; this.N = N;
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(samples), 3));
    const col = new Float32Array(N * 3); g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    this.base = new Float32Array(samples); this.col = col;
    this.points = new THREE.Points(g, pointsMat(0.11)); this.group.add(this.points);
    // inner wiring: lines between near points (a nervous system)
    const lp = []; const M = Math.floor(900 * Q);
    for (let i = 0; i < M; i++) { const a = Math.floor(Math.random() * N), b = Math.floor(Math.random() * N); const d = Math.hypot(samples[a * 3] - samples[b * 3], samples[a * 3 + 1] - samples[b * 3 + 1], samples[a * 3 + 2] - samples[b * 3 + 2]); if (d < 1.4) lp.push(samples[a * 3], samples[a * 3 + 1], samples[a * 3 + 2], samples[b * 3], samples[b * 3 + 1], samples[b * 3 + 2]); }
    const lg = new THREE.BufferGeometry(); lg.setAttribute("position", new THREE.BufferAttribute(new Float32Array(lp), 3));
    this.lines = new THREE.LineSegments(lg, new THREE.LineBasicMaterial({ color: TEAL, transparent: true, opacity: 0.18, blending: THREE.AdditiveBlending })); this.group.add(this.lines);
    this.heart = new THREE.Vector3(-0.15, 5.5, 0.4);
    this.heartLight = new THREE.PointLight(GOLD, 0, 10); this.heartLight.position.copy(this.heart); this.group.add(this.heartLight);
    this.group.position.y = -3.9;
    this.level = 0; this.bpm = 62;
  }
  update(t, audioLevel) {
    const beat = (t * this.bpm / 60) % 1; const pulse = Math.exp(-beat * 6) * (0.55 + audioLevel * 2);
    const c = this.col, b = this.base, h = this.heart;
    for (let i = 0; i < this.N; i++) {
      const dx = b[i * 3] - h.x, dy = b[i * 3 + 1] - h.y, dz = b[i * 3 + 2] - h.z; const d = Math.sqrt(dx * dx + dy * dy + dz * dz);
      const wave = Math.max(0, 1 - Math.abs(d - beat * 6.5) * 0.9) * pulse;
      const base = 0.35 + 0.25 * Math.sin(t * 0.7 + i * 0.01);
      c[i * 3] = Math.min(1, base * 1.0 + wave * 1.0); c[i * 3 + 1] = Math.min(1, base * 0.82 + wave * 0.7); c[i * 3 + 2] = Math.min(1, base * 0.55 + wave * 0.2);
    }
    this.points.geometry.attributes.color.needsUpdate = true;
    this.heartLight.intensity = 6 * pulse;
    this.group.rotation.y = Math.sin(t * 0.15) * 0.25;
  }
}

class NeuronSet {
  constructor() {
    this.group = new THREE.Group(); const segs = []; const tips = [];
    const grow = (p, dir, len, depth) => {
      if (depth <= 0 || len < 0.25) { tips.push(p.clone()); return; }
      const q = p.clone().add(dir.clone().multiplyScalar(len)); segs.push(p.x, p.y, p.z, q.x, q.y, q.z);
      const k = depth > 4 ? 2 : (Math.random() < 0.6 ? 2 : 1);
      for (let i = 0; i < k; i++) { const d = dir.clone().add(new THREE.Vector3().randomDirection().multiplyScalar(0.55)).normalize(); grow(q, d, len * 0.78, depth - 1); }
    };
    const somas = [];
    for (let s = 0; s < (isSmall ? 4 : 7); s++) {
      const c = new THREE.Vector3((Math.random() - 0.5) * 16, (Math.random() - 0.5) * 9, (Math.random() - 0.5) * 10); somas.push(c);
      for (let d = 0; d < 6; d++) grow(c, new THREE.Vector3().randomDirection(), 1.6, 6);
    }
    const lg = new THREE.BufferGeometry(); lg.setAttribute("position", new THREE.BufferAttribute(new Float32Array(segs), 3));
    this.lines = new THREE.LineSegments(lg, new THREE.LineBasicMaterial({ color: 0x7fd6ff, transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending })); this.group.add(this.lines);
    const sg = new THREE.BufferGeometry(); const sp = new Float32Array(somas.length * 3), sc = new Float32Array(somas.length * 3);
    somas.forEach((c, i) => { sp.set([c.x, c.y, c.z], i * 3); sc.set([1, 0.8, 0.45], i * 3); });
    sg.setAttribute("position", new THREE.BufferAttribute(sp, 3)); sg.setAttribute("color", new THREE.BufferAttribute(sc, 3));
    this.somas = new THREE.Points(sg, pointsMat(2.2)); this.group.add(this.somas);
    const tg = new THREE.BufferGeometry(); const tp = new Float32Array(tips.length * 3), tc = new Float32Array(tips.length * 3);
    tips.forEach((p, i) => { tp.set([p.x, p.y, p.z], i * 3); tc.set([0.5, 0.85, 1], i * 3); });
    tg.setAttribute("position", new THREE.BufferAttribute(tp, 3)); tg.setAttribute("color", new THREE.BufferAttribute(tc, 3));
    this.tips = new THREE.Points(tg, pointsMat(0.35, 0.8)); this.group.add(this.tips);
    // signals: sparks travelling along random segments
    this.segs = segs; const S = Math.floor(160 * Q); const pg = new THREE.BufferGeometry(); const pp = new Float32Array(S * 3), pc = new Float32Array(S * 3);
    this.sparks = []; for (let i = 0; i < S; i++) { this.sparks.push({ s: Math.floor(Math.random() * segs.length / 6), t: Math.random() }); pc.set([1, 0.9, 0.6], i * 3); }
    pg.setAttribute("position", new THREE.BufferAttribute(pp, 3)); pg.setAttribute("color", new THREE.BufferAttribute(pc, 3));
    this.sparkPts = new THREE.Points(pg, pointsMat(0.5)); this.group.add(this.sparkPts);
    this.hz = 10;
  }
  update(t, dt, audioLevel) {
    const pos = this.sparkPts.geometry.attributes.position.array, s = this.segs;
    const speed = 0.5 + this.hz / 20 + audioLevel * 2;
    this.sparks.forEach((k, i) => { k.t += dt * speed; if (k.t > 1) { k.t = 0; k.s = Math.floor(Math.random() * s.length / 6); } const o = k.s * 6; pos[i * 3] = s[o] + (s[o + 3] - s[o]) * k.t; pos[i * 3 + 1] = s[o + 1] + (s[o + 4] - s[o + 1]) * k.t; pos[i * 3 + 2] = s[o + 2] + (s[o + 5] - s[o + 2]) * k.t; });
    this.sparkPts.geometry.attributes.position.needsUpdate = true;
    const flash = 0.5 + 0.5 * Math.sin(t * this.hz * 2 * Math.PI * 0.25);
    this.somas.material.size = 2.0 + 1.2 * flash + audioLevel * 3; this.lines.material.opacity = 0.28 + 0.15 * flash;
    this.group.rotation.y = t * 0.04; this.group.rotation.x = Math.sin(t * 0.1) * 0.1;
  }
}

class GenomeSet {
  constructor() {
    this.group = new THREE.Group();
    const bases = "ATGCGTACGATCGATCGGTACCGATTACGGCATCGATCGTTAGCCGATCGATGCATGCCGATATCGCGATCGGATCCGTAAGCTAGCATGCATTGACCGTA";
    const colors = { A: new THREE.Color(TEAL), T: new THREE.Color(GOLD), G: new THREE.Color(IVORY), C: new THREE.Color(0x7aa2ff) };
    const L = bases.length, pitch = 0.3, R = 1.15;
    const sphereG = new THREE.SphereGeometry(0.1, 12, 12), rungG = new THREE.CylinderGeometry(0.03, 0.03, 1, 8);
    const bb = new THREE.MeshStandardMaterial({ color: 0xcdc5b4, roughness: 0.35, metalness: 0.55 });
    this.rungs = [];
    for (let i = 0; i < L; i++) {
      const a = i * 0.6, y = (i - L / 2) * pitch;
      const p1 = new THREE.Vector3(Math.cos(a) * R, y, Math.sin(a) * R), p2 = p1.clone().negate().setY(y);
      const s1 = new THREE.Mesh(sphereG, bb), s2 = new THREE.Mesh(sphereG, bb); s1.position.copy(p1); s2.position.copy(p2); this.group.add(s1, s2);
      const b = bases[i], comp = { A: "T", T: "A", G: "C", C: "G" }[b]; const mid = p1.clone().add(p2).multiplyScalar(0.5);
      for (const [base, from, to] of [[b, p1, mid], [comp, mid, p2]]) {
        const m = new THREE.Mesh(rungG, new THREE.MeshStandardMaterial({ color: colors[base], emissive: colors[base], emissiveIntensity: 0.3, roughness: 0.4 }));
        m.position.copy(from.clone().add(to).multiplyScalar(0.5)); m.scale.y = from.distanceTo(to); m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), to.clone().sub(from).normalize());
        this.group.add(m); this.rungs.push(m);
      }
    }
    const key = new THREE.DirectionalLight(0xfff1d6, 2.2); key.position.set(4, 6, 6); const rim = new THREE.DirectionalLight(TEAL, 1.4); rim.position.set(-6, -3, -4);
    this.group.add(key, rim, new THREE.AmbientLight(0x404040, 1.1));
    this.group.rotation.z = 0.35; this.group.position.x = isSmall ? 0 : 2.8;
  }
  update(t, audioLevel) {
    this.group.rotation.y = t * 0.25;
    const k = Math.floor((t * 6) % this.rungs.length);
    for (let i = 0; i < this.rungs.length; i += 1) this.rungs[i].material.emissiveIntensity = 0.25 + (Math.abs(i - k) < 6 ? 0.9 * (1 - Math.abs(i - k) / 6) : 0) + audioLevel;
  }
}

export class EarthSet {
  constructor() {
    this.group = new THREE.Group();
    // the Earth's 2 MB of pictures load the first time the Earth is on screen, not with the page
    const mat = new THREE.MeshPhongMaterial({ color: 0x1b2a44, normalScale: new THREE.Vector2(0.6, 0.6), specular: new THREE.Color(0x334455), shininess: 18, emissive: new THREE.Color(0x0f1626), emissiveIntensity: 1.0 });
    this.mat = mat; this.loaded = false;
    this.earth = new THREE.Mesh(new THREE.SphereGeometry(3, 96, 96), mat);
    this.clouds = new THREE.Mesh(new THREE.SphereGeometry(3.035, 64, 64), new THREE.MeshLambertMaterial({ transparent: true, opacity: 0, depthWrite: false }));
    const glow = new THREE.Mesh(new THREE.SphereGeometry(3.25, 64, 64), new THREE.ShaderMaterial({ side: THREE.BackSide, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, uniforms: { c: { value: new THREE.Color(0x3f8dd1) } },
      vertexShader: `varying vec3 vN; varying vec3 vP; void main(){ vN = normalize(normalMatrix*normal); vP = (modelViewMatrix*vec4(position,1.)).xyz; gl_Position = projectionMatrix*vec4(vP,1.);}`,
      fragmentShader: `uniform vec3 c; varying vec3 vN; varying vec3 vP; void main(){ float f = pow(1.0 - abs(dot(normalize(-vP), vN)), 3.5); gl_FragColor = vec4(c, f*0.9); }` }));
    this.tilt = new THREE.Group(); this.tilt.add(this.earth, this.clouds, glow); this.tilt.rotation.z = THREE.MathUtils.degToRad(-23.4); this.group.add(this.tilt);
    const sun = new THREE.DirectionalLight(0xfff2dc, 2.4); sun.position.set(8, 3, 6); this.group.add(sun, new THREE.AmbientLight(0x223344, 0.5));
    this.markers = new THREE.Group(); this.earth.add(this.markers); this.target = null;
  }
  static toVec(lat, lon, r) { const phi = THREE.MathUtils.degToRad(90 - lat), th = THREE.MathUtils.degToRad(lon + 180); return new THREE.Vector3(-r * Math.sin(phi) * Math.cos(th), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(th)); }
  setMarkers(list) {
    this.markers.clear();
    for (const m of list) { const p = EarthSet.toVec(m.lat, m.lon, 3.02); const dot = new THREE.Mesh(new THREE.SphereGeometry(0.04, 10, 10), new THREE.MeshBasicMaterial({ color: GOLD })); dot.position.copy(p); const ring = new THREE.Mesh(new THREE.RingGeometry(0.07, 0.09, 32), new THREE.MeshBasicMaterial({ color: GOLD, side: THREE.DoubleSide, transparent: true, opacity: 0.8 })); ring.position.copy(p); ring.lookAt(p.clone().multiplyScalar(2)); ring.userData.ph = Math.random() * 6; this.markers.add(dot, ring); }
  }
  face(lat, lon, precise = false) { this.target = { lat, lon }; this.precise = precise; }
  // red border of a country (GeoJSON MultiPolygon in lon/lat) and a pulsing pin on the city
  highlight(feature, pin) {
    this.clearHighlight(); if (!feature) return;
    const g = new THREE.Group(); const polys = feature.geometry.type === "Polygon" ? [feature.geometry.coordinates] : feature.geometry.coordinates;
    const mk = (r, op) => { const pts = []; for (const poly of polys) { const ring = poly[0]; for (let i = 1; i < ring.length; i++) { pts.push(EarthSet.toVec(ring[i - 1][1], ring[i - 1][0], r), EarthSet.toVec(ring[i][1], ring[i][0], r)); } }
      const geo = new THREE.BufferGeometry().setFromPoints(pts); const m = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0xff3b3b, transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false })); m.userData.base = op; return m; };
    g.add(mk(3.012, 1), mk(3.02, 0.55), mk(3.032, 0.25));
    if (pin) { const p = EarthSet.toVec(pin.lat, pin.lon, 3.03); const dot = new THREE.Mesh(new THREE.SphereGeometry(0.035, 12, 12), new THREE.MeshBasicMaterial({ color: 0xff3b3b })); dot.position.copy(p);
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.05, 0.065, 40), new THREE.MeshBasicMaterial({ color: 0xff5a5a, side: THREE.DoubleSide, transparent: true, opacity: 0.9, depthWrite: false })); ring.position.copy(p); ring.lookAt(p.clone().multiplyScalar(2)); ring.userData.pin = true; g.add(dot, ring); }
    // how close to come: a small country lets the camera dive deeper
    let x0 = 180, x1 = -180, y0 = 90, y1 = -90; for (const poly of polys) for (const [x, y] of poly[0]) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
    const span = Math.min(60, Math.max(x1 - x0, (y1 - y0) * 1.3)); this.zoomDist = 3 + Math.min(2.4, Math.max(0.55, span * 0.055));
    g.userData.t0 = performance.now(); this.hl = g; this.earth.add(g);
  }
  clearHighlight() { if (this.hl) { this.earth.remove(this.hl); this.hl.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); }); this.hl = null; } }
  ensure() {
    if (this.loaded) return; this.loaded = true;
    const L = new THREE.TextureLoader(), m = this.mat, c = this.clouds.material;
    const tex = (n) => { const t = L.load(`./assets/${n}`, () => { m.needsUpdate = true; c.needsUpdate = true; }); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t; };
    m.color.set(0xffffff); m.map = tex("earth_atmos_2048.jpg"); m.normalMap = L.load("./assets/earth_normal_2048.jpg"); m.specularMap = L.load("./assets/earth_specular_2048.jpg"); m.emissiveMap = tex("earth_lights_2048.png"); m.needsUpdate = true;
    c.map = tex("earth_clouds_1024.png"); c.opacity = 0.5; c.needsUpdate = true;
  }
  update(t, dt) {
    this.ensure();
    if (this.target) { const p = EarthSet.toVec(this.target.lat, this.target.lon, 1); const ty = -Math.atan2(p.x, p.z); let d = ty - this.earth.rotation.y; d = Math.atan2(Math.sin(d), Math.cos(d)); const kk = Math.min(1, dt * (this.precise ? 5.5 : 1.5)); this.earth.rotation.y += d * kk; this.tilt.rotation.x += (Math.asin(p.y) * (this.precise ? 1 : 0.9) - this.tilt.rotation.x) * kk; }
    else if (!reduceMotion) this.earth.rotation.y += dt * 0.05;
    { const zt = this.precise ? 0 : THREE.MathUtils.degToRad(-23.4); this.tilt.rotation.z += (zt - this.tilt.rotation.z) * Math.min(1, dt * 1.5); }
    this.clouds.rotation.y = this.earth.rotation.y * 1.06 + 0.4;
    this.markers.children.forEach(c => { if (c.userData.ph !== undefined) { const s = 1 + 0.35 * Math.sin(t * 2 + c.userData.ph); c.scale.set(s, s, s); } });
    if (this.hl) { const k = Math.min(1, (performance.now() - this.hl.userData.t0) / 900); this.hl.children.forEach(o => { if (o.userData.base !== undefined) o.material.opacity = o.userData.base * k * (0.75 + 0.25 * Math.sin(t * 3)); if (o.userData.pin) { const ph = (t * 0.9) % 1; o.scale.setScalar(1 + ph * 2.2); o.material.opacity = 0.9 * (1 - ph); } }); }
  }
}

class GalaxySet {
  constructor() {
    this.group = new THREE.Group();
    const N = Math.floor(60000 * Q); const g = new THREE.BufferGeometry(); const pos = new Float32Array(N * 3), col = new Float32Array(N * 3);
    const arms = 2, b = 0.28;
    for (let i = 0; i < N; i++) {
      const arm = i % arms; const r = Math.pow(Math.random(), 0.7) * 26 + 0.3; const th = Math.log(r / 0.3) / b + arm * Math.PI + (Math.random() - 0.5) * (0.9 + r * 0.02);
      const spread = (Math.random() - 0.5) * (0.4 + r * 0.08); const x = Math.cos(th) * r + spread, z = Math.sin(th) * r + (Math.random() - 0.5) * (0.4 + r * 0.08), y = (Math.random() - 0.5) * (0.2 + 2.4 * Math.exp(-r / 5));
      pos.set([x, y, z], i * 3);
      const core = Math.exp(-r / 6); const c = new THREE.Color().setHSL(0.09 - 0.03 * core + (Math.random() < 0.1 ? 0.48 : 0), 0.6, 0.5 + 0.35 * core + Math.random() * 0.2);
      col.set([c.r, c.g, c.b], i * 3);
    }
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    this.points = new THREE.Points(g, pointsMat(0.42, 1)); this.group.add(this.points);
    const core = new THREE.Mesh(new THREE.SphereGeometry(2.2, 24, 24), new THREE.MeshBasicMaterial({ color: 0xffe2b0, transparent: true, opacity: 0.22, blending: THREE.AdditiveBlending })); this.group.add(core);
    const haze = new THREE.Points(starfield(Math.floor(3000 * Q), 1).geometry, pointsMat(3.5, 0.08)); haze.scale.setScalar(5); this.group.add(haze);
    // the Sun and its orbit, planets along for the ride
    this.sunR = 14; this.sun = new THREE.Mesh(new THREE.SphereGeometry(0.4, 16, 16), new THREE.MeshBasicMaterial({ color: 0xfff1c4 })); this.group.add(this.sun);
    const orbit = new THREE.Mesh(new THREE.RingGeometry(this.sunR - 0.02, this.sunR + 0.02, 180), new THREE.MeshBasicMaterial({ color: GOLD, transparent: true, opacity: 0.25, side: THREE.DoubleSide })); orbit.rotation.x = Math.PI / 2; this.group.add(orbit);
    this.planets = []; const pc = [0xbfc6ff, 0xffd9a8, 0x7fd0ff, 0xff9a7a];
    pc.forEach((c, i) => { const m = new THREE.Mesh(new THREE.SphereGeometry(0.07 + i * 0.015, 10, 10), new THREE.MeshBasicMaterial({ color: c })); this.group.add(m); this.planets.push({ m, r: 0.55 + i * 0.32, w: 2.2 - i * 0.35, ph: Math.random() * 6 }); });
    this.trail = []; const tg = new THREE.BufferGeometry(); tg.setAttribute("position", new THREE.BufferAttribute(new Float32Array(4 * 120 * 3), 3));
    this.trails = new THREE.LineSegments(tg, new THREE.LineBasicMaterial({ color: IVORY, transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending })); this.group.add(this.trails);
    this.group.rotation.x = 0.55; this.phase = 0; this.bpm = 60;
  }
  update(t, dt, audioLevel) {
    this.group.rotation.y += dt * (0.015 + audioLevel * 0.05);
    this.phase += dt * 0.12; const a = this.phase; const sx = Math.cos(a) * this.sunR, sz = Math.sin(a) * this.sunR; this.sun.position.set(sx, 0, sz);
    const tp = this.trails.geometry.attributes.position.array; let k = 0;
    this.planets.forEach((p, i) => { const ang = t * p.w + p.ph; p.m.position.set(sx + Math.cos(ang) * p.r, Math.sin(ang * 0.7) * 0.08, sz + Math.sin(ang) * p.r);
      for (let j = 0; j < 120; j++) { const tt = t - j * 0.08, aa = this.phase - j * 0.08 * 0.12, an = tt * p.w + p.ph; const cx = Math.cos(aa) * this.sunR, cz = Math.sin(aa) * this.sunR; tp[k++] = cx + Math.cos(an) * p.r; tp[k++] = Math.sin(an * 0.7) * 0.08; tp[k++] = cz + Math.sin(an) * p.r; } });
    this.trails.geometry.attributes.position.needsUpdate = true; this.trails.geometry.setDrawRange(0, 4 * 120);
    this.points.material.size = 0.42 + audioLevel * 0.35;
  }
}


class StudioSet {
  // The plate: a Chladni figure of the pulse frequency. Like sand on a vibrating plate, light gathers on
  // the nodal lines, so every band draws its own figure (delta a few wide rings, gamma a fine lattice),
  // in the band's own colour, and morphs to the next figure when the frequency changes. The plate breathes
  // with the beat and lifts with the sound; a ring of 96 bars around it is the live spectrum.
  constructor() {
    this.group = new THREE.Group();
    const N = isSmall ? 84 : 150; this.N = N; const S = 11;
    const g = new THREE.BufferGeometry(); const pos = new Float32Array(N * N * 3), col = new Float32Array(N * N * 3);
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) { const k = (i * N + j) * 3; pos[k] = (i / (N - 1) - 0.5) * S; pos[k + 1] = 0; pos[k + 2] = (j / (N - 1) - 0.5) * S; col[k] = 0.9; col[k + 1] = 0.85; col[k + 2] = 0.75; }
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    this.points = new THREE.Points(g, pointsMat(isSmall ? 0.13 : 0.115, 1)); this.group.add(this.points);
    this.ring = new THREE.Mesh(new THREE.RingGeometry(6.05, 6.12, 180), new THREE.MeshBasicMaterial({ color: GOLD, transparent: true, opacity: 0.5, side: THREE.DoubleSide, blending: THREE.AdditiveBlending })); this.ring.rotation.x = -Math.PI / 2; this.ring.position.y = -0.02; this.group.add(this.ring);
    // spectrum ring: 96 thin bars standing on a circle
    this.bars = new THREE.Group(); this.nb = 96; const barG = new THREE.BoxGeometry(0.06, 1, 0.06); barG.translate(0, 0.5, 0);
    for (let i = 0; i < this.nb; i++) { const m = new THREE.Mesh(barG, new THREE.MeshBasicMaterial({ color: i % 3 ? TEAL : GOLD, transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending })); const a = i / this.nb * Math.PI * 2; m.position.set(Math.cos(a) * 6.5, 0, Math.sin(a) * 6.5); m.scale.y = 0.05; this.bars.add(m); }
    this.group.add(this.bars);
    // dust
    const D = Math.floor(600 * Q); const dg = new THREE.BufferGeometry(); const dp = new Float32Array(D * 3), dc = new Float32Array(D * 3);
    for (let i = 0; i < D; i++) { dp.set([(Math.random() - 0.5) * 14, Math.random() * 5, (Math.random() - 0.5) * 14], i * 3); dc.set([0.85, 0.75, 0.5], i * 3); }
    dg.setAttribute("position", new THREE.BufferAttribute(dp, 3)); dg.setAttribute("color", new THREE.BufferAttribute(dc, 3));
    this.dust = new THREE.Points(dg, pointsMat(isSmall ? 0.03 : 0.045, 0.35)); this.group.add(this.dust);
    this.group.add(new THREE.AmbientLight(0x404040, 1));
    this.hz = 10; this.bpm = 60; this.level = 0; this.phase = 0; this.spectrum = null;
    this.tint = new THREE.Color(TEAL); this.tintTarget = new THREE.Color(TEAL);
    this.nm = this._nm(10); this.nmFrom = this.nm; this.morph = 1; this.boost = 1;
  }
  // the figure for a frequency: more nodal lines as the frequency rises, a different family per band
  _nm(hz) {
    const T = [[0.5, 1, 2], [4, 2, 3], [6, 2, 5], [8, 3, 5], [10, 3, 7], [12, 4, 7], [16, 5, 8], [22, 6, 9], [30, 7, 11], [40, 9, 12], [50, 10, 13]];
    let r = T[0]; for (const x of T) if (hz >= x[0]) r = x; return [r[1], r[2]];
  }
  setAccent(c) { /* the plate takes the band's colour, see setBand */ }
  setBand(hex) { this.tintTarget.set(hex); }
  update(t, dt, audioLevel) {
    this.tint.lerp(this.tintTarget, Math.min(1, dt * 2.5));
    this.level += (audioLevel - this.level) * 0.25;
    const want = this._nm(this.hz); if (want[0] !== this.nm[0] || want[1] !== this.nm[1]) { this.nmFrom = this.morph < 1 ? this.nm : this.nm; this.nm = want; this.morph = 0; }
    this.morph = Math.min(1, this.morph + dt * 1.2); const mk = this.morph * this.morph * (3 - 2 * this.morph);
    const beat = (t * this.bpm / 60) % 1, pulse = Math.exp(-beat * 4);
    const amp = 0.18 + this.level * 2.2 + pulse * 0.12;
    this.phase += dt * (0.8 + Math.min(this.hz, 40) * 0.25);
    const [n, m] = this.nm, [n0, m0] = this.nmFrom, ph = Math.sin(this.phase);
    const pos = this.points.geometry.attributes.position.array, col = this.points.geometry.attributes.color.array, N = this.N;
    const tr = this.tint.r, tg = this.tint.g, tb = this.tint.b, glow = 0.85 + 0.35 * pulse + this.level * 0.8;
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) {
      const k = i * N + j, x = i / (N - 1), z = j / (N - 1);
      let v = Math.cos(n * Math.PI * x) * Math.cos(m * Math.PI * z) - Math.cos(m * Math.PI * x) * Math.cos(n * Math.PI * z);
      if (mk < 1) { const v0 = Math.cos(n0 * Math.PI * x) * Math.cos(m0 * Math.PI * z) - Math.cos(m0 * Math.PI * x) * Math.cos(n0 * Math.PI * z); v = v0 + (v - v0) * mk; }
      pos[k * 3 + 1] = v * amp * ph;
      const line = Math.exp(-Math.abs(v) * 7);            // the nodal lines, where sand would gather
      const b = (0.12 + 1.1 * line) * glow;
      col[k * 3] = Math.min(1.4, tr * b + 0.08 * line); col[k * 3 + 1] = Math.min(1.4, tg * b + 0.08 * line); col[k * 3 + 2] = Math.min(1.4, tb * b + 0.08 * line);
    }
    this.points.geometry.attributes.position.needsUpdate = true; this.points.geometry.attributes.color.needsUpdate = true;
    this.ring.material.color.copy(this.tint); this.ring.scale.setScalar(1 + pulse * 0.015);
    const sp = this.spectrum;
    this.bars.children.forEach((bar, i) => { const v = sp ? sp[Math.floor(i / this.nb * sp.length * 0.5)] / 255 : 0; const target = 0.04 + v * v * 1.6 + pulse * 0.1; bar.scale.y += (target - bar.scale.y) * 0.3; bar.material.opacity = 0.3 + v * 0.7; if (i % 3 === 0) bar.material.color.copy(this.tint); });
    this.bars.rotation.y = -t * 0.05; this.points.rotation.y = Math.sin(t * 0.07) * 0.12;
    const dp = this.dust.geometry.attributes.position.array; for (let i = 1; i < dp.length; i += 3) { dp[i] += dt * (0.08 + this.level * 0.6); if (dp[i] > 5) dp[i] = 0; } this.dust.geometry.attributes.position.needsUpdate = true;
  }
}
// ------------------------------------------------------------------ director
export class Film {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: !isSmall, alpha: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6)); this.renderer.setClearColor(0x06070d, 0);
    this.scene = new THREE.Scene(); this.scene.fog = new THREE.FogExp2(0x06070d, 0.012);
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.05, 600);
    this.stars = starfield(Math.floor(5000 * Q), 220); this.scene.add(this.stars);
    this.sets = { human: new HumanSet(), neurons: new NeuronSet(), genome: new GenomeSet(), earth: new EarthSet(), galaxy: new GalaxySet(), studio: new StudioSet() };
    for (const s of Object.values(this.sets)) { s.group.visible = false; this.scene.add(s.group); }
    // keyframes per slide: which set, camera from->to (dolly during the slide), fov
    this.shots = {
      human:   { set: "human",   from: [0, 1.2, 17],  to: [0, 0.3, 10],    look: [0, 0.3, 0], fov: 40 },
      neurons: { set: "neurons", from: [0, 0, 22],    to: [2, 1, 9],       look: [0, 0, 0],   fov: 50 },
      genome:  { set: "genome",  from: [0, 0, 14],    to: [3, 1.5, 7],     look: [0, 0, 0],   fov: 42 },
      earth:   { set: "earth",   from: [0, 2, 14],    to: [0, 0.6, 6.0],   look: [0, 0.4, 0], fov: 40 },
      galaxy:  { set: "galaxy",  from: [0, 34, 40],   to: [6, 9, 22],      look: [0, 0, 0],   fov: 50 },
      touch:   { set: null,      from: [0, 0, 20],    to: [0, 0, 20],      look: [0, 0, 0],   fov: 40 },
      app:     { set: "studio",  from: [-2.5, 7.2, 12.5], to: [2, 6.2, 10.8], look: [0, -1.2, 0], fov: 44 },
      plate:   { set: "studio",  from: [0, 10.5, 9.5], to: [0.8, 9.2, 8.2],  look: [0, -0.6, 0], fov: 46 },
      world:   { set: "earth",   from: [0, 2, 14],    to: [0, 0.6, 6.0],   look: [0, 0.4, 0], fov: 40 },
      clinic:  { set: "galaxy",  from: [0, 20, 40],   to: [0, 20, 40],     look: [0, 0, 0],   fov: 50, dim: 0.3 },
    };
    this.current = "human"; this.progress = 0; this.fade = { from: null, to: "human", k: 1 }; this.audioLevel = 0; this.mouse = { x: 0, y: 0 };
    this.zoom = 0; this.zoomK = 0;   // Earth chapter: 0 = orbit, 1 = down over a city
    this.accent = new THREE.Color(GOLD);
    this.clock = new THREE.Clock(); this.cut = 0;
    window.addEventListener("pointermove", e => { this.mouse.x = (e.clientX / window.innerWidth - 0.5); this.mouse.y = (e.clientY / window.innerHeight - 0.5); }, { passive: true });
    this.sets.human.group.visible = true;
  }
  // name = slide name, k = 0..1 progress through that slide (for the dolly)
  zoomTo(k) { this.zoom = Math.min(1, Math.max(0, k)); }
  setAccent(hex) { this.accent.set(hex); if (this.sets.studio.setAccent) this.sets.studio.setAccent(this.accent); }
  setShot(name, k) {
    if (!this.shots[name]) return;
    if (name !== this.current) { this.fade = { from: this.current, to: name, k: 0 }; this.current = name; this.cut = 1; }
    this.progress = k;
  }
  resize() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (this.canvas.width !== Math.floor(w * this.renderer.getPixelRatio())) { this.renderer.setSize(w, h, false); this.camera.aspect = w / h; this.camera.updateProjectionMatrix(); }
  }
  render() {
    this.resize();
    const dt = Math.min(this.clock.getDelta(), 0.05), t = this.clock.elapsedTime;
    const shot = this.shots[this.current];
    // cross-fade sets
    if (this.fade.k < 1) { this.fade.k = Math.min(1, this.fade.k + dt * 1.4); }
    const fromSet = this.fade.from && this.shots[this.fade.from].set, toSet = shot.set;
    for (const [n, s] of Object.entries(this.sets)) {
      let op = 0; if (n === toSet) op = ease(this.fade.k); if (n === fromSet && n !== toSet) op = 1 - ease(this.fade.k);
      s.group.visible = op > 0.01; s.group.traverse(o => { if (o.material && o.material.transparent !== undefined && o.userData.baseOp === undefined) o.userData.baseOp = o.material.opacity ?? 1; if (o.material && o.userData.baseOp !== undefined) o.material.opacity = o.userData.baseOp * op * (shot.dim ? shot.dim : 1); });
    }
    // camera
    const e = ease(Math.min(Math.max(this.progress, 0), 1));
    const f = shot.from, to = shot.to, lk = shot.look;
    let px = f[0] + (to[0] - f[0]) * e + this.mouse.x * 0.8, py = f[1] + (to[1] - f[1]) * e - this.mouse.y * 0.5, pz = f[2] + (to[2] - f[2]) * e;
    let lx = lk[0], ly = lk[1], lz = lk[2];
    // Earth: drop from orbit to a city and back (zoomK eases toward zoom)
    if ((this.current === "earth" || this.current === "world") && this.sets.earth.precise) { py *= 0.25; ly = 0; }
    const zt = this.current === "earth" || this.current === "world" ? this.zoom : 0; this.zoomK += (zt - this.zoomK) * (reduceMotion ? 1 : Math.min(1, dt * 1.1));
    if (this.zoomK > 0.001) { const z = ease(this.zoomK), zd = this.sets.earth.zoomDist || 3.95; px = px * (1 - z) + (this.mouse.x * 0.1) * z; py = py * (1 - z) + 0 * z; pz = pz * (1 - z) + zd * z; ly = ly * (1 - z); }
    this.camera.position.lerp(new THREE.Vector3(px, py, pz), reduceMotion ? 1 : Math.min(1, dt * 2.2));
    this.camera.lookAt(lx, ly, lz);
    if (Math.abs(this.camera.fov - shot.fov) > 0.1) { this.camera.fov += (shot.fov - this.camera.fov) * Math.min(1, dt * 2); this.camera.updateProjectionMatrix(); }
    // sets
    const L = this.audioLevel;
    if (this.sets.human.group.visible) this.sets.human.update(t, L);
    if (this.sets.neurons.group.visible) this.sets.neurons.update(t, dt, L);
    if (this.sets.genome.group.visible) this.sets.genome.update(t, L);
    if (this.sets.earth.group.visible) this.sets.earth.update(t, dt);
    if (this.sets.galaxy.group.visible) this.sets.galaxy.update(t, dt, L);
    if (this.sets.studio.group.visible) this.sets.studio.update(t, dt, L);
    this.stars.rotation.y += dt * 0.004;
    // cut flash
    if (this.cut > 0) { this.cut = Math.max(0, this.cut - dt * 3); }
    this.renderer.render(this.scene, this.camera);
  }
}
