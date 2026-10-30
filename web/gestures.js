// Hand gestures for the player. Two readers, same interface:
//   * MediaPipe GestureRecognizer (a pretrained hand-landmark model + gesture classifier: open palm,
//     fist, victory, thumbs up / down, pointing), loaded on demand from a CDN, then run on device.
//     GPU first; if the GPU delegate fails (common on some laptops), the same model on the CPU (WASM).
//   * the author's own skin-colour tracker (web/vendor/tracker.js) only when the model cannot load at
//     all (offline, blocked CDN). It is told where the face is so a head turn is never read as a hand.
// read(video, faceBox) -> { present, gesture, vx, x, y, landmarks, score, source } with gesture in
//   palm | fist | pinch | victory | point | thumb_up | thumb_down | null
import { SkinTracker } from "./vendor/tracker.js";

const MP_VERSION = "0.10.14";
const BUNDLES = [`https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VERSION}`, `https://unpkg.com/@mediapipe/tasks-vision@${MP_VERSION}`];
const MODEL = "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task";
const MP_NAMES = { Open_Palm: "palm", Closed_Fist: "fist", Victory: "victory", Pointing_Up: "point", Thumb_Up: "thumb_up", Thumb_Down: "thumb_down", ILoveYou: "palm" };
export const HAND_LINKS = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12], [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [0, 17], [17, 18], [18, 19], [19, 20]];

export class GestureReader {
  constructor() { this.mode = null; this.mp = null; this.skin = null; this.calibrated = false; this.lastX = null; this.lastT = 0; this.vx = 0; this.loading = null; this.status = "off"; this.error = null; this.delegate = null; this.lastTs = 0; }
  async start(onStatus) {
    if (this.mode) return this.mode;
    const say = (s) => { this.status = s; if (onStatus) onStatus(s); };
    this.loading = this.loading || (async () => {
      say("loading");
      for (const base of BUNDLES) {
        try {
          const mod = await Promise.race([import(/* @vite-ignore */ `${base}/vision_bundle.mjs`), new Promise((_, rej) => setTimeout(() => rej(new Error("timeout loading the hand model")), 12000))]);
          const vision = await mod.FilesetResolver.forVisionTasks(`${base}/wasm`);
          for (const delegate of ["GPU", "CPU"]) {
            try {
              this.mp = await mod.GestureRecognizer.createFromOptions(vision, { baseOptions: { modelAssetPath: MODEL, delegate }, runningMode: "VIDEO", numHands: 1,
                minHandDetectionConfidence: 0.5, minHandPresenceConfidence: 0.5, minTrackingConfidence: 0.5 });
              this.delegate = delegate; this.mode = "mediapipe"; say("ready"); return this.mode;
            } catch (e) { this.error = (e && e.message) || String(e); console.warn(`MediaPipe ${delegate} delegate failed:`, this.error); }
          }
        } catch (e) { this.error = (e && e.message) || String(e); console.warn("MediaPipe bundle failed from", base, this.error); }
      }
      this.skin = new SkinTracker(); this.calibrated = false; this.mode = "skin"; say("fallback");
      return this.mode;
    })();
    return this.loading;
  }
  // horizontal velocity of the hand centre in frame widths per second
  _velocity(x, now) { if (this.lastX != null && now > this.lastT) { const v = (x - this.lastX) / ((now - this.lastT) / 1000); this.vx = this.vx * 0.5 + v * 0.5; } this.lastX = x; this.lastT = now; return this.vx; }
  read(video, faceBox) {
    let now = performance.now();
    if (this.mode === "mediapipe" && this.mp) {
      if (now <= this.lastTs) now = this.lastTs + 1;          // the model needs strictly increasing timestamps
      this.lastTs = now;
      let r; try { r = this.mp.recognizeForVideo(video, now); } catch (e) { this.error = (e && e.message) || String(e); return { present: false, gesture: null, vx: 0, source: "mediapipe" }; }
      const lm = r.landmarks && r.landmarks[0]; if (!lm) { this.lastX = null; this.vx = 0; return { present: false, gesture: null, vx: 0, source: "mediapipe" }; }
      const cx = lm.reduce((s, p) => s + p.x, 0) / lm.length, cy = lm.reduce((s, p) => s + p.y, 0) / lm.length;
      const g = r.gestures && r.gestures[0] && r.gestures[0][0]; const name = g && g.score > 0.5 ? (MP_NAMES[g.categoryName] || null) : null;
      // pinch: thumb tip (4) close to index tip (8), relative to the hand's size
      const size = Math.hypot(lm[0].x - lm[9].x, lm[0].y - lm[9].y) || 0.1;
      const pinch = Math.hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y) / size < 0.28 && name !== "fist" && name !== "palm";
      return { present: true, gesture: pinch ? "pinch" : name, score: g ? g.score : 0, vx: this._velocity(cx, now), x: cx, y: cy, landmarks: lm, source: "mediapipe " + (this.delegate || "").toLowerCase() };
    }
    if (this.mode === "skin" && this.skin) {
      if (!this.calibrated) { if (this.skin.calibrateFrame(video)) this.calibrated = true; return { present: false, gesture: null, vx: 0, calibrating: !this.calibrated, source: "skin" }; }
      const out = this.skin.update(video, 0.1); const hs = (out.hands || []).filter(h => h && h.present);
      // never the face: drop a blob whose centre falls inside the face box (grown by 25 %)
      const W = video.videoWidth || 1, H = video.videoHeight || 1;
      const notFace = hs.filter(h => { if (!faceBox) return true; const gx = faceBox.width * 0.25, gy = faceBox.height * 0.25; const px = (h.px ?? h.x * W), py = (h.py ?? h.y * H); return !(px > faceBox.x - gx && px < faceBox.x + faceBox.width + gx && py > faceBox.y - gy && py < faceBox.y + faceBox.height + gy); });
      const h = notFace[0]; if (!h) { this.lastX = null; this.vx = 0; return { present: false, gesture: null, vx: 0, source: "skin" }; }
      const g = h.gesture === "open" ? "palm" : h.gesture; return { present: true, gesture: g, vx: this._velocity(h.x, now), x: h.x, y: h.y, source: "skin" };
    }
    return { present: false, gesture: null, vx: 0, source: this.mode || "none" };
  }
  stop() { if (this.mp) { try { this.mp.close(); } catch {} } this.mp = null; this.skin = null; this.mode = null; this.loading = null; this.lastX = null; this.vx = 0; this.status = "off"; }
}
