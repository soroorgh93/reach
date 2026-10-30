"""Render the guided-tour narration with Kokoro (offline neural TTS, Apache-2.0).
    pip install kokoro-onnx soundfile
    python make_voice.py --model kokoro-v1.0.onnx --voices voices-v1.0.bin --steps guide_steps.json --out web/assets/guide
Writes <out>/<lang>/nNN.mp3 (needs ffmpeg) and <out>/manifest.json with durations."""
import argparse, json, subprocess, shutil
from pathlib import Path
import soundfile as sf
from kokoro_onnx import Kokoro

VOICE = {"en": ("af_heart", "en-us", 0.96), "es": ("ef_dora", "es", 0.95), "zh": ("zf_xiaoxiao", "cmn", 0.95)}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--model"); ap.add_argument("--voices"); ap.add_argument("--steps"); ap.add_argument("--out"); ap.add_argument("--langs", default="en,es,zh"); ap.add_argument("--only", type=int, default=None)
    a = ap.parse_args(); k = Kokoro(a.model, a.voices); steps = json.load(open(a.steps, encoding="utf-8")); out = Path(a.out)
    man = json.loads((out / "manifest.json").read_text()) if (out / "manifest.json").exists() else {}
    ff = shutil.which("ffmpeg")
    for lang in a.langs.split(","):
        voice, code, speed = VOICE[lang]; d = out / lang; d.mkdir(parents=True, exist_ok=True); man.setdefault(lang, {})
        for i, st in enumerate(steps[lang]):
            if a.only is not None and i != a.only: continue
            samples, sr = k.create(st["s"], voice=voice, speed=speed, lang=code)
            wav = d / f"n{i:02d}.wav"; sf.write(wav, samples, sr)
            mp3 = d / f"n{i:02d}.mp3"
            subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(wav), "-af", "loudnorm=I=-17:TP=-1.5,afade=t=in:d=0.05", "-ar", "44100", "-ac", "1", "-b:a", "80k", str(mp3)], check=True); wav.unlink()
            man[lang][f"n{i:02d}"] = round(len(samples) / sr, 2); print(lang, i, man[lang][f"n{i:02d}"], "s", flush=True)
    (out / "manifest.json").write_text(json.dumps(man, indent=1))

if __name__ == "__main__":
    main()
