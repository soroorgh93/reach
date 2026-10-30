// tracker.js — OUR hand tracker. No pretrained model, no network: classical computer vision on the webcam pixels.
//
//   1. calibrate(): the player holds a hand inside a box for ~1 s; we learn the skin colour (Cr/Cb mean ± k·σ).
//   2. every frame: skin mask (160×120) → open/close morphology → connected components → blobs.
//   3. the face is the big static blob; hands are assigned to blobs by proximity to their last position.
//   4. per hand: palm centre + radius by iterative erosion (a cheap distance transform), fingertips from the
//      radial profile of the contour (peaks > 1.6·R), pinch from a *hole* inside the hand silhouette
//      (thumb + index closing a loop), openness from hull area / blob area.
//   5. 21 pseudo-landmarks for the StrokeTCN: palm centre + 20 radial contour samples (consistent ordering by angle).
//
// Output matches input.js: hands with x,y (mirrored 0..1), gesture, pinch, landmarks[21]{x,y,z}; head yaw from the face blob.

const W = 160, H = 120, N = W * H;

export class SkinTracker {
  constructor() {
    this.canvas = document.createElement("canvas"); this.canvas.width = W; this.canvas.height = H;
    this.ctx = this.canvas.getContext("2d", { willReadFrequently: true });
    this.mask = new Uint8Array(N); this.tmp = new Uint8Array(N); this.labels = new Int32Array(N);
    this.skin = { cr: 150, cb: 110, sCr: 9, sCb: 9 }; this.calibrated = false; this.calSamples = [];
    this.hands = [null, null]; // [racket, god] trackers: {x,y,area,...}
    this.face = null; this.debug = { blobs: [] };
    this.minArea = 120; this.k = 2.6;
  }

  // ---- 1. calibration: average the Cr/Cb inside the centre box over several frames
  calibrateFrame(src, box = { x: 0.3, y: 0.25, w: 0.4, h: 0.5 }) {
    this.ctx.drawImage(src, 0, 0, W, H);
    const d = this.ctx.getImageData(0, 0, W, H).data;
    const x0 = (box.x * W) | 0, y0 = (box.y * H) | 0, x1 = ((box.x + box.w) * W) | 0, y1 = ((box.y + box.h) * H) | 0;
    const crs = [], cbs = [];
    for (let y = y0; y < y1; y += 2) for (let x = x0; x < x1; x += 2) {
      const i = (y * W + x) * 4, r = d[i], g = d[i + 1], b = d[i + 2];
      const yy = 0.299 * r + 0.587 * g + 0.114 * b; if (yy < 40 || yy > 245) continue;
      const pcr = 128 + 0.5 * r - 0.4187 * g - 0.0813 * b, pcb = 128 - 0.1687 * r - 0.3313 * g + 0.5 * b;
      // broad skin prior (all skin tones live here; grey walls, blue shirts and black hair do not)
      if (pcr < 133 || pcr > 185 || pcb < 77 || pcb > 135 || r < g || r < b) continue;
      crs.push(pcr); cbs.push(pcb);
    }
    if (crs.length < 40) return false;
    // robust centre: median, then trimmed std
    const med = (a) => { const s = [...a].sort((p, q) => p - q); return s[s.length >> 1]; };
    const mCr = med(crs), mCb = med(cbs);
    const trimmed = (a, m) => a.filter((v) => Math.abs(v - m) < 18);
    const tCr = trimmed(crs, mCr), tCb = trimmed(cbs, mCb);
    const std = (a, m) => Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / Math.max(1, a.length));
    this.calSamples.push({ cr: mCr, cb: mCb, sCr: Math.max(4, std(tCr, mCr)), sCb: Math.max(4, std(tCb, mCb)) });
    if (this.calSamples.length >= 12) {
      const avg = (k) => this.calSamples.reduce((s, c) => s + c[k], 0) / this.calSamples.length;
      this.skin = { cr: avg("cr"), cb: avg("cb"), sCr: avg("sCr"), sCb: avg("sCb") };
      this.calibrated = true; this.calSamples = [];
      return true;
    }
    return false;
  }

  // ---- 2. skin mask + morphology
  _mask(d) {
    const { cr, cb, sCr, sCb } = this.skin, k = this.k, m = this.mask;
    for (let p = 0, i = 0; p < N; p++, i += 4) {
      const r = d[i], g = d[i + 1], b = d[i + 2];
      const yy = 0.299 * r + 0.587 * g + 0.114 * b;
      const pcr = 128 + 0.5 * r - 0.4187 * g - 0.0813 * b, pcb = 128 - 0.1687 * r - 0.3313 * g + 0.5 * b;
      m[p] = (yy > 35 && Math.abs(pcr - cr) < k * sCr && Math.abs(pcb - cb) < k * sCb) ? 1 : 0;
    }
    this._erode(m, this.tmp); this._dilate(this.tmp, m); this._dilate(m, this.tmp); this._erode(this.tmp, m);
  }
  _erode(a, b) { for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) { const p = y * W + x; b[p] = (x > 0 && y > 0 && x < W - 1 && y < H - 1 && a[p] && a[p - 1] && a[p + 1] && a[p - W] && a[p + W]) ? 1 : 0; } }
  _dilate(a, b) { for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) { const p = y * W + x; b[p] = (a[p] || (x > 0 && a[p - 1]) || (x < W - 1 && a[p + 1]) || (y > 0 && a[p - W]) || (y < H - 1 && a[p + W])) ? 1 : 0; } }

  // ---- 3. connected components (4-neighbour flood fill with an explicit stack)
  _blobs() {
    const L = this.labels.fill(0), m = this.mask, blobs = [], stack = new Int32Array(N); let id = 0;
    for (let s = 0; s < N; s++) {
      if (!m[s] || L[s]) continue;
      id++; let sp = 0; stack[sp++] = s; L[s] = id;
      let area = 0, sx = 0, sy = 0, minx = W, maxx = 0, miny = H, maxy = 0;
      while (sp) {
        const p = stack[--sp], x = p % W, y = (p / W) | 0; area++; sx += x; sy += y;
        if (x < minx) minx = x; if (x > maxx) maxx = x; if (y < miny) miny = y; if (y > maxy) maxy = y;
        if (x > 0 && m[p - 1] && !L[p - 1]) { L[p - 1] = id; stack[sp++] = p - 1; }
        if (x < W - 1 && m[p + 1] && !L[p + 1]) { L[p + 1] = id; stack[sp++] = p + 1; }
        if (y > 0 && m[p - W] && !L[p - W]) { L[p - W] = id; stack[sp++] = p - W; }
        if (y < H - 1 && m[p + W] && !L[p + W]) { L[p + W] = id; stack[sp++] = p + W; }
      }
      if (area >= this.minArea) blobs.push({ id, area, cx: sx / area, cy: sy / area, minx, maxx, miny, maxy });
    }
    return blobs.sort((a, b) => b.area - a.area);
  }

  // ---- 4. per-blob analysis: palm, radial profile, fingertips, hole (pinch)
  _analyze(blob) {
    const L = this.labels, id = blob.id;
    // palm centre: erode the blob repeatedly; the last surviving pixels are the thickest part
    let cur = new Uint8Array(N); for (let p = 0; p < N; p++) cur[p] = L[p] === id ? 1 : 0;
    let nxt = new Uint8Array(N), iters = 0, cx = blob.cx, cy = blob.cy;
    for (; iters < 40; iters++) {
      let n = 0, sx = 0, sy = 0;
      for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) { const p = y * W + x; const v = cur[p] && cur[p - 1] && cur[p + 1] && cur[p - W] && cur[p + W] && cur[p - W - 1] && cur[p - W + 1] && cur[p + W - 1] && cur[p + W + 1]; nxt[p] = v ? 1 : 0; if (v) { n++; sx += x; sy += y; } }
      if (n === 0) break;
      cx = sx / n; cy = sy / n; const t = cur; cur = nxt; nxt = t; nxt.fill(0);
    }
    const R = Math.max(3, iters + 1); // palm radius in pixels (erosion count)
    // radial profile: farthest blob pixel per angular bin (72 bins)
    const BINS = 72, prof = new Float32Array(BINS).fill(0);
    for (let y = blob.miny; y <= blob.maxy; y++) for (let x = blob.minx; x <= blob.maxx; x++) {
      const p = y * W + x; if (L[p] !== id) continue;
      // boundary pixels only
      if (x > 0 && x < W - 1 && y > 0 && y < H - 1 && L[p - 1] === id && L[p + 1] === id && L[p - W] === id && L[p + W] === id) continue;
      const dx = x - cx, dy = y - cy, r = Math.hypot(dx, dy); const b = ((Math.atan2(dy, dx) + Math.PI) / (2 * Math.PI) * BINS) | 0;
      const bi = Math.min(BINS - 1, Math.max(0, b)); if (r > prof[bi]) prof[bi] = r;
    }
    // smooth + peaks
    const sm = new Float32Array(BINS); for (let i = 0; i < BINS; i++) sm[i] = (prof[(i + BINS - 1) % BINS] + prof[i] + prof[(i + 1) % BINS]) / 3;
    const tips = [];
    for (let i = 0; i < BINS; i++) {
      const v = sm[i]; if (v < 1.6 * R) continue;
      let peak = true; for (let d = -3; d <= 3; d++) if (d !== 0 && sm[(i + d + BINS) % BINS] > v) { peak = false; break; }
      if (peak && !tips.some((t) => Math.min(Math.abs(t.bin - i), BINS - Math.abs(t.bin - i)) < 5)) tips.push({ bin: i, r: v });
    }
    // hole inside the bbox: background pixels not reachable from the bbox border = pinch loop
    let hole = 0;
    {
      const x0 = Math.max(0, blob.minx - 1), x1 = Math.min(W - 1, blob.maxx + 1), y0 = Math.max(0, blob.miny - 1), y1 = Math.min(H - 1, blob.maxy + 1);
      const seen = this.tmp; seen.fill(0); const st = []; let bg = 0;
      for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) { const p = y * W + x; if (L[p] !== id) { bg++; if (x === x0 || x === x1 || y === y0 || y === y1) { seen[p] = 1; st.push(p); } } }
      let reached = 0;
      while (st.length) { const p = st.pop(); reached++; const x = p % W, y = (p / W) | 0;
        for (const q of [p - 1, p + 1, p - W, p + W]) { const qx = q % W, qy = (q / W) | 0; if (qx < x0 || qx > x1 || qy < y0 || qy > y1 || Math.abs(qx - x) + Math.abs(qy - y) !== 1) continue; if (L[q] !== id && !seen[q]) { seen[q] = 1; st.push(q); } } }
      hole = bg - reached; // enclosed background pixels
    }
    const openness = Math.min(1, Math.max(0, (blob.area / (Math.PI * R * R) - 1.3) / 2.2)); // 0 fist … 1 spread palm
    // 21 pseudo-landmarks: palm centre + 20 contour samples by angle (normalized screen coords, mirrored)
    const lm = [{ x: cx / W, y: cy / H, z: 0 }];
    for (let i = 0; i < 20; i++) { const b = ((i / 20) * BINS) | 0; const a = (b / BINS) * 2 * Math.PI - Math.PI; const r = Math.max(sm[b], R); lm.push({ x: (cx + Math.cos(a) * r) / W, y: (cy + Math.sin(a) * r) / H, z: 0 }); }
    return { cx: cx / W, cy: cy / H, R: R / W, tips: tips.length, hole: hole / Math.max(1, blob.area), openness, lm, area: blob.area / N };
  }

  // ---- 5. frame update: returns { hands: [racket|null, god|null], head: {present, yaw, pitch} }
  update(src, dt = 1 / 30) {
    this.ctx.drawImage(src, 0, 0, W, H);
    const d = this.ctx.getImageData(0, 0, W, H).data;
    this._mask(d);
    const blobs = this._blobs();
    this.debug.blobs = blobs;
    // face: the largest blob whose centre is in the upper 65 % and which moved little
    let face = null;
    if (blobs.length) {
      const cands = blobs.filter((b) => b.cy / H < 0.65 && b.area > 0.02 * N);
      if (cands.length) {
        face = cands[0];
        if (this.face) { const near = cands.find((b) => Math.hypot(b.cx - this.face.cx, b.cy - this.face.cy) < 25); if (near) face = near; }
      }
    }
    // assign hand blobs: everything that is not the face
    const rest = blobs.filter((b) => b !== face);
    const assign = [null, null];
    for (let h = 0; h < 2; h++) {
      const prev = this.hands[h]; if (!prev) continue;
      let best = null, bd = 40; for (const b of rest) { if (assign.includes(b)) continue; const dd = Math.hypot(b.cx - prev.px * W, b.cy - prev.py * H); if (dd < bd) { bd = dd; best = b; } }
      assign[h] = best;
    }
    const free = rest.filter((b) => !assign.includes(b));
    if (!assign[0] && free.length) { assign[0] = free[0]; free.shift(); }
    if (!assign[1] && free.length) { assign[1] = free[0]; }
    // mirrored view: the racket hand should be the one on the RIGHT of the mirrored image (= left in raw pixels... mirrored x = 1 - raw x)
    if (assign[0] && assign[1] && (1 - assign[0].cx / W) < (1 - assign[1].cx / W)) { const t = assign[0]; assign[0] = assign[1]; assign[1] = t; }
    const out = [null, null];
    for (let h = 0; h < 2; h++) {
      const b = assign[h]; if (!b) { this.hands[h] = null; continue; }
      const a = this._analyze(b);
      const prev = this.hands[h];
      const x = 1 - a.cx, y = a.cy;
      const vx = prev ? (x - prev.x) / dt : 0, vy = prev ? (y - prev.y) / dt : 0;
      const pinch = a.hole > 0.035 ? 1 : 0;
      let gesture = "open";
      if (pinch) gesture = "pinch"; else if (a.tips <= 1 && a.openness < 0.35) gesture = "fist"; else if (a.tips >= 4 || a.openness > 0.75) gesture = "palm"; else if (a.tips === 2) gesture = "victory"; else if (a.tips === 1) gesture = "point";
      out[h] = { present: true, x, y, px: a.cx, py: a.cy, vx, vy, pinch, gesture, landmarks: a.lm.map((p) => ({ x: p.x, y: p.y, z: 0 })) /* raw (un-mirrored) like MediaPipe; input.js mirrors */, size: a.R * 2, tips: a.tips, openness: a.openness, hole: a.hole };
      this.hands[h] = out[h];
    }
    this.face = face;
    const head = face ? { present: true, yaw: Math.max(-1, Math.min(1, -(face.cx / W - 0.5) * 4)), pitch: Math.max(-1, Math.min(1, (0.35 - face.cy / H) * 3)) } : { present: false, yaw: 0, pitch: 0 };
    return { hands: out, head, blobs };
  }
}
