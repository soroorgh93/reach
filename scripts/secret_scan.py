"""Fails when a key, token or private env file is in the files git would commit.

    python scripts/secret_scan.py          # scans `git ls-files` (or every file when git is absent)

Checks: env / .env / .qloo_key / zip files tracked at all; known key shapes (Google AIza..., Anthropic
sk-ant-..., OpenAI sk-..., GitHub ghp_/github_pat_, AWS AKIA..., private keys); and any KEY=value line
for the variables Reach reads (QLOO_API_KEY, YOUTUBE_API_KEY, ...) with a value filled in."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEVER = re.compile(r"(^|/)(\.env|env|\.qloo_key)$|\.zip$|(^|/)bench_detail\.local\.json$")
SHAPES = [
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Anthropic key", re.compile(r"sk-ant-[0-9A-Za-z_\-]{20,}")),
    ("OpenAI key", re.compile(r"\bsk-(proj-)?[0-9A-Za-z]{32,}")),
    ("GitHub token", re.compile(r"\b(ghp_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{40,})")),
    ("AWS key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
FILLED = re.compile(r"^[ \t]*(QLOO_API_KEY|YOUTUBE_API_KEY|ANTHROPIC_API_KEY|OPENAI_API_KEY)[ \t]*[=:][ \t]*['\"]?([^'\"\s#]{8,})", re.M)
SKIP_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp3", ".mp4", ".webm", ".ico", ".task", ".woff", ".woff2", ".ttf", ".bin"}


def files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [l for l in out.splitlines() if l]
    except (OSError, subprocess.CalledProcessError):
        return [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts]


def main() -> int:
    bad: list[str] = []
    for f in files():
        f = f.replace("\\", "/")
        if NEVER.search(f):
            bad.append(f"{f}: this file must never be committed (it is in .gitignore)")
            continue
        p = ROOT / f
        if p.suffix.lower() in SKIP_EXT or not p.is_file() or p.stat().st_size > 3_000_000:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, rx in SHAPES:
            if rx.search(text):
                bad.append(f"{f}: looks like a {name}")
        for m in FILLED.finditer(text):
            if f.endswith(".env.example") and not m.group(2).strip():
                continue
            bad.append(f"{f}: {m.group(1)} has a value")
    if bad:
        print("Secret scan FAILED:\n  " + "\n  ".join(bad))
        return 1
    print("Secret scan: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
