"""Stage 1 — convert any audio to 16 kHz mono WAV via ffmpeg."""

import shutil
import subprocess
from pathlib import Path

from .cache import Cache

FFMPEG_HOMEBREW = "/opt/homebrew/opt/ffmpeg/bin/ffmpeg"


def _ffmpeg_bin() -> str:
    if Path(FFMPEG_HOMEBREW).exists():
        return FFMPEG_HOMEBREW
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError(
        "ffmpeg not found. Install with: brew install ffmpeg"
    )


def convert_to_wav(audio_path: str, cache: Cache, audio_hash: str) -> str:
    """Return path to cached 16 kHz mono WAV, converting if needed."""
    if cache.exists(audio_hash, "audio", "wav"):
        out = str(cache.path(audio_hash, "audio", "wav"))
        print(f"  [cache hit] {out}")
        return out

    out = str(cache.path(audio_hash, "audio", "wav"))
    cmd = [
        _ffmpeg_bin(), "-y",
        "-i", audio_path,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        out,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed:\n{result.stderr}")

    print(f"  Converted → {out}")
    return out
