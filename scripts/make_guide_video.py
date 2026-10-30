"""Render the narrated guided tour as a video (a woman's voice, captions on screen).

The browser runs the real app in guide render mode (?tour=1&render=1), this script steps
through the sixteen chapters, records the page, speaks each caption with a neural voice and
muxes the two. Nothing is faked: what you see is the app composing live.

    pip install playwright edge-tts imageio-ffmpeg
    python -m playwright install chromium
    # with the server running on http://localhost:8001 (live Qloo key set) :
    python scripts/make_guide_video.py --url http://localhost:8001 --lang en
    -> docs/reach-guided-tour-en.mp4

Voices (female, neural) by language: en Aria, es Elvira, fa Dilara, zh Xiaoxiao (edge-tts).
Without network for edge-tts the script falls back to Windows' own voice (SAPI, female), then
to espeak-ng, then to silence with captions only. ffmpeg comes from PATH or imageio-ffmpeg.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICES = {"en": "en-US-AriaNeural", "es": "es-ES-ElviraNeural", "fa": "fa-IR-DilaraNeural", "zh": "zh-CN-XiaoxiaoNeural"}


def ffmpeg_exe() -> str:
    for name in ("ffmpeg", "ffmpeg.exe"):
        if shutil.which(name):
            return shutil.which(name)
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        sys.exit("ffmpeg not found: install it or `pip install imageio-ffmpeg`")


def steps_for(lang: str) -> list[dict]:
    """Read the guide captions straight from web/i18n_extra.js (the single source of truth)."""
    src = (ROOT / "web" / "i18n_extra.js").read_text(encoding="utf-8")
    block = src.split(f"\n  {lang}: {{", 1)[1].split("guide_steps: [", 1)[1].split("\n    ],", 1)[0]
    out = []
    for m in re.finditer(r'\{\s*t:\s*"((?:[^"\\]|\\.)*)",\s*s:\s*"((?:[^"\\]|\\.)*)"\s*\}', block):
        out.append({"t": json.loads('"' + m.group(1) + '"'), "s": json.loads('"' + m.group(2) + '"')})
    if not out:
        sys.exit(f"no guide steps found for {lang}")
    return out


def duration_of(path: Path, ff: str) -> float:
    probe = ff.replace("ffmpeg", "ffprobe") if "ffprobe" not in ff else ff
    if shutil.which(probe) or Path(probe).exists():
        try:
            out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=30).stdout.strip()
            return float(out)
        except Exception:
            pass
    # ffmpeg -i prints the duration on stderr
    r = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) if m else 0.0


async def tts_edge(text: str, voice: str, out: Path) -> bool:
    try:
        import edge_tts  # type: ignore
    except ImportError:
        return False
    try:
        await edge_tts.Communicate(text, voice, rate="-4%").save(str(out))
        return out.exists() and out.stat().st_size > 1000
    except Exception as e:  # noqa: BLE001
        print("edge-tts failed:", e)
        return False


def tts_sapi(text: str, lang: str, out: Path) -> bool:
    if os.name != "nt":
        return False
    culture = {"en": "en-US", "es": "es-ES", "fa": "fa-IR", "zh": "zh-CN"}[lang]
    ps = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {{ $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female, [System.Speech.Synthesis.VoiceAge]::Adult, 0, [System.Globalization.CultureInfo]::GetCultureInfo('{culture}')) }} catch {{}}
$s.Rate = -1
$s.SetOutputToWaveFile('{out}')
$s.Speak([IO.File]::ReadAllText('{out.with_suffix(".txt")}', [Text.Encoding]::UTF8))
$s.Dispose()
"""
    out.with_suffix(".txt").write_text(text, encoding="utf-8")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    return r.returncode == 0 and out.exists() and out.stat().st_size > 1000


def tts_espeak(text: str, lang: str, out: Path) -> bool:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        return False
    voice = {"en": "en-us+f3", "es": "es+f3", "fa": "fa+f3", "zh": "cmn+f3"}[lang]
    r = subprocess.run([exe, "-v", voice, "-s", "150", "-w", str(out), text], capture_output=True)
    return r.returncode == 0 and out.exists()


def narrate(steps: list[dict], lang: str, outdir: Path, ff: str) -> list[dict]:
    outdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, st in enumerate(steps):
        mp3, wav = outdir / f"n{i:02d}.mp3", outdir / f"n{i:02d}.wav"
        path, how = None, "silence"
        rec = ROOT / "web" / "assets" / "guide" / lang / f"n{i:02d}.mp3"   # the app's own recorded narration (Kokoro)
        if rec.exists():
            path, how = rec, "kokoro (recorded)"
        elif asyncio.run(tts_edge(st["s"], VOICES[lang], mp3)):
            path, how = mp3, "edge-tts " + VOICES[lang]
        elif tts_sapi(st["s"], lang, wav):
            path, how = wav, "windows voice"
        elif tts_espeak(st["s"], lang, wav):
            path, how = wav, "espeak-ng"
        dur = duration_of(path, ff) if path else max(3.0, len(st["s"].split()) * 0.36 + 1.2)
        rows.append({"i": i, "path": str(path) if path else None, "dur": dur, "how": how})
        print(f"narration {i:02d}  {dur:5.1f} s  {how}  {st['t']}")
    return rows


async def record(url: str, lang: str, rows: list[dict], outdir: Path, width: int, height: int, persona: str | None) -> tuple[Path, list[float]]:
    from playwright.async_api import async_playwright  # type: ignore
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required", "--enable-webgl", "--ignore-gpu-blocklist", "--use-gl=angle"])
        ctx = await browser.new_context(viewport={"width": width, "height": height}, record_video_dir=str(outdir), record_video_size={"width": width, "height": height}, locale=lang)
        page = await ctx.new_page()
        t0 = time.monotonic()
        await page.goto(f"{url}/?tour=1&render=1&lang={lang}", wait_until="load")
        await page.wait_for_function("window.__reach && window.__reach.guide && window.__reach.guide.open", timeout=30000)
        if persona:
            await page.evaluate("(id) => { const p = window.__reach.state.personas.find(x => x.id === id); if (p) window.__reach.loadPersona(p); }", persona)
        starts: list[float] = []
        for r in rows:
            await page.evaluate("(i) => window.__reach.guide.goto(i)", r["i"])
            starts.append(time.monotonic() - t0 + 0.25)
            await page.wait_for_timeout(int((r["dur"] + 0.9) * 1000))
        await page.wait_for_timeout(800)
        video_path = await page.video.path()
        await ctx.close(); await browser.close()
        return Path(video_path), starts


def mux(ff: str, video: Path, rows: list[dict], starts: list[float], out: Path) -> None:
    inputs, filters, labels = ["-i", str(video)], [], []
    k = 1
    for r, t in zip(rows, starts):
        if not r["path"]:
            continue
        inputs += ["-i", r["path"]]
        filters.append(f"[{k}:a]adelay={int(t * 1000)}|{int(t * 1000)},aresample=48000[a{k}]"); labels.append(f"[a{k}]"); k += 1
    cmd = [ff, "-y", "-loglevel", "error", "-stats", *inputs]
    if labels:
        filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0,volume=1.4,alimiter=limit=0.95[aout]")
        cmd += ["-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[aout]", "-c:a", "aac", "-b:a", "160k"]
    else:
        cmd += ["-map", "0:v"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-shortest", str(out)]
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--lang", default="en", choices=list(VOICES))
    ap.add_argument("--persona", default=None, help="persona id to load before the tour (default: the app's own demo patient)")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    width, height = (int(x) for x in a.size.lower().split("x"))
    ff = ffmpeg_exe()
    work = ROOT / "docs" / "guide" / a.lang
    steps = steps_for(a.lang)
    rows = narrate(steps, a.lang, work, ff)
    video, starts = asyncio.run(record(a.url, a.lang, rows, work, width, height, a.persona))
    out = Path(a.out) if a.out else ROOT / "docs" / f"reach-guided-tour-{a.lang}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    mux(ff, video, rows, starts, out)
    total = sum(r["dur"] + 0.9 for r in rows)
    print(f"\nwrote {out}  ({total / 60:.1f} min, {len(rows)} chapters, voice: {rows[0]['how']})")


if __name__ == "__main__":
    main()
