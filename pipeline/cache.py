"""SHA-256-keyed disk cache for each pipeline stage."""

import hashlib
import json
from pathlib import Path
from typing import Any


class Cache:
    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    def audio_hash(self, audio_path: str) -> str:
        h = hashlib.sha256()
        with open(audio_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:20]

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def path(self, audio_hash: str, stage: str, ext: str) -> Path:
        return self.cache_dir / f"{audio_hash}_{stage}.{ext}"

    def exists(self, audio_hash: str, stage: str, ext: str) -> bool:
        return self.path(audio_hash, stage, ext).exists()

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def save_json(self, audio_hash: str, stage: str, data: Any) -> None:
        p = self.path(audio_hash, stage, "json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_json(self, audio_hash: str, stage: str) -> Any:
        p = self.path(audio_hash, stage, "json")
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    # ------------------------------------------------------------------
    # NumPy arrays (global, not per-audio)
    # ------------------------------------------------------------------

    def save_npy(self, name: str, array) -> None:
        import numpy as np
        np.save(self.cache_dir / f"{name}.npy", array)

    def load_npy(self, name: str):
        import numpy as np
        return np.load(self.cache_dir / f"{name}.npy")

    def npy_exists(self, name: str) -> bool:
        return (self.cache_dir / f"{name}.npy").exists()

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def clear_audio(self, audio_hash: str) -> None:
        targets = [
            self.path(audio_hash, "audio", "wav"),
            self.path(audio_hash, "transcript", "json"),
            self.path(audio_hash, "diarization", "json"),
            self.path(audio_hash, "speaker_map", "json"),
        ]
        targets.extend(self.cache_dir.glob(f"{audio_hash}_transcript_*.json"))
        for p in targets:
            if p.exists():
                p.unlink()
                print(f"  [cache] Cleared {p.name}")
