// On-device mood reading. Camera frames and microphone audio never leave the browser:
// what goes to the server is seven expression probabilities and three prosody numbers,
// and only after the person switched each sensor on. Everything is an estimate the person
// can correct by dragging the mood dial.
let faceApiLoading = null;
function loadFaceApi() {
  faceApiLoading = faceApiLoading || new Promise((ok, no) => { const sc = document.createElement("script"); sc.src = "./vendor/faceapi/face-api.min.js"; sc.onload = () => (window.faceapi ? ok() : no(new Error("face model not loaded"))); sc.onerror = () => { faceApiLoading = null; no(new Error("face model not loaded")); }; document.head.appendChild(sc); });
  return faceApiLoading;
}
const EXPR = ["neutral", "happy", "sad", "angry", "fearful", "disgusted", "surprised"];

export class FaceReader {
  constructor(video) { this.video = video; this.ready = false; this.expr = null; this.stream = null; this.timer = null; this.onRead = null; }
  async start() {
    if (!window.faceapi) await loadFaceApi();          // 650 KB, fetched only when the person turns the camera on
    if (!this.ready) { await Promise.all([faceapi.nets.tinyFaceDetector.loadFromUri("./vendor/faceapi"), faceapi.nets.faceExpressionNet.loadFromUri("./vendor/faceapi")]); this.ready = true; }
    this.stream = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240, facingMode: "user" }, audio: false });
    this.video.srcObject = this.stream; await this.video.play();
    const loop = async () => {
      if (!this.stream) return;
      try {
        const det = await faceapi.detectSingleFace(this.video, new faceapi.TinyFaceDetectorOptions({ inputSize: 224, scoreThreshold: 0.4 })).withFaceExpressions();
        if (det) { const e = {}; EXPR.forEach(k => e[k] = +det.expressions[k].toFixed(3)); this.expr = this.expr ? Object.fromEntries(EXPR.map(k => [k, +(0.6 * this.expr[k] + 0.4 * e[k]).toFixed(3)])) : e; if (this.onRead) this.onRead(this.expr, det.detection.box); }
        else if (this.onRead) this.onRead(null, null);
      } catch (err) { console.warn("face", err); }
      this.timer = setTimeout(loop, 700);
    };
    loop();
  }
  stop() { clearTimeout(this.timer); if (this.stream) { this.stream.getTracks().forEach(t => t.stop()); this.stream = null; } this.video.srcObject = null; this.expr = null; }
}

export class VoiceReader {
  constructor() { this.ctx = null; this.stream = null; this.an = null; this.feat = null; this.timer = null; this.onRead = null; this.hist = []; }
  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false });
    this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)(); await this.ctx.resume();
    const src = this.ctx.createMediaStreamSource(this.stream); this.an = this.ctx.createAnalyser(); this.an.fftSize = 2048; src.connect(this.an);
    this.buf = new Float32Array(this.an.fftSize); this.hist = []; this.voiced = 0; this.frames = 0;
    const loop = () => {
      if (!this.stream) return;
      this.an.getFloatTimeDomainData(this.buf);
      let s = 0; for (let i = 0; i < this.buf.length; i++) s += this.buf[i] * this.buf[i]; const rms = Math.sqrt(s / this.buf.length);
      const f0 = rms > 0.01 ? this._pitch(this.buf, this.ctx.sampleRate) : 0;
      this.frames++; if (f0 > 0) this.voiced++;
      this.hist.push({ rms, f0 }); if (this.hist.length > 60) this.hist.shift();
      const voiced = this.hist.filter(h => h.f0 > 0); const energy = Math.min(1, (this.hist.reduce((a, h) => a + h.rms, 0) / this.hist.length) * 12);
      const pv = voiced.length > 4 ? Math.min(1, (Math.max(...voiced.map(h => h.f0)) - Math.min(...voiced.map(h => h.f0))) / 180) : 0;
      // speech rate proxy: how often energy crosses its running mean
      let cross = 0; const mean = this.hist.reduce((a, h) => a + h.rms, 0) / this.hist.length; for (let i = 1; i < this.hist.length; i++) if ((this.hist[i].rms > mean) !== (this.hist[i - 1].rms > mean)) cross++;
      const rate = Math.min(1, cross / 20);
      this.feat = { energy: +energy.toFixed(3), pitch_var: +pv.toFixed(3), rate: +rate.toFixed(3), f0: Math.round(f0), rms: +rms.toFixed(4) };
      if (this.onRead) this.onRead(this.feat);
      this.timer = setTimeout(loop, 100);
    };
    loop();
  }
  _pitch(buf, rate) {  // autocorrelation, 80-400 Hz
    const minLag = Math.floor(rate / 400), maxLag = Math.floor(rate / 80); let best = 0, bestLag = 0;
    for (let lag = minLag; lag < maxLag; lag += 2) { let c = 0; for (let i = 0; i < 1024; i += 2) c += buf[i] * buf[i + lag]; if (c > best) { best = c; bestLag = lag; } }
    let e = 0; for (let i = 0; i < 1024; i += 2) e += buf[i] * buf[i]; return best > e * 0.45 && bestLag ? rate / bestLag : 0;
  }
  stop() { clearTimeout(this.timer); if (this.stream) { this.stream.getTracks().forEach(t => t.stop()); this.stream = null; } this.feat = null; }
}

export function speechRecognizer(lang, onText) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition; if (!SR) return null;
  const r = new SR(); r.lang = { en: "en-US", es: "es-ES", fa: "fa-IR", zh: "zh-CN" }[lang] || "en-US"; r.interimResults = true; r.continuous = false;
  r.onresult = (e) => { let t = ""; for (const res of e.results) t += res[0].transcript; onText(t, e.results[e.results.length - 1].isFinal); };
  return r;
}
