"""Participant identification from per-person voice reference samples."""

from __future__ import annotations

import io
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import torch
import torchaudio

from .cache import Cache

_FFMPEG_HOMEBREW = "/opt/homebrew/opt/ffmpeg/bin/ffmpeg"
MIN_CHUNK_SEC = 0.5
MAX_CHUNKS_PER_SPEAKER = 20
DEFAULT_THRESHOLD = 0.65


def participants_with_voice_samples(participants: list[dict]) -> list[dict]:
    """Return participants that define voice_sample or voice_samples."""
    result = []
    for participant in participants:
        samples = _voice_samples_for(participant)
        if participant.get("name") and samples:
            result.append({**participant, "voice_samples": samples})
    return result


def identify_participants(
    turns: list,
    wav_path: str,
    cache: Cache,
    audio_hash: str,
    participants: list[dict],
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    """Return {diarization_label: participant_name} using voice embeddings."""
    references = participants_with_voice_samples(participants)
    if not references:
        return {}

    speakers = sorted({turn["speaker"] for turn in turns})
    if not speakers:
        return {}

    print(f"  Voice references found for: {', '.join(p['name'] for p in references)}")

    speaker_embeddings = _speaker_embeddings(wav_path, turns, speakers, cache, audio_hash)
    reference_embeddings = {}
    for participant in references:
        try:
            reference_embeddings[participant["name"]] = _reference_embedding(participant, cache)
        except Exception as exc:
            print(f"  WARNING: Could not use voice sample for {participant['name']}: {exc}")

    if not reference_embeddings:
        return {}

    scores = []
    for speaker, speaker_emb in speaker_embeddings.items():
        print(f"  {speaker}:")
        for name, reference_emb in reference_embeddings.items():
            score = cosine_sim(speaker_emb, reference_emb)
            scores.append((score, speaker, name))
            print(f"    {name:<20} similarity = {score:.4f}")

    assigned_speakers = set()
    assigned_names = set()
    mapping = {}
    for score, speaker, name in sorted(scores, reverse=True):
        if score < threshold or speaker in assigned_speakers or name in assigned_names:
            continue
        mapping[speaker] = name
        assigned_speakers.add(speaker)
        assigned_names.add(name)

    if mapping:
        print("  Participant identification:")
        for speaker, name in mapping.items():
            best_score = max(score for score, s, n in scores if s == speaker and n == name)
            print(f"    {speaker} -> {name} ({best_score:.4f})")
    else:
        print(f"  WARNING: No voice match met threshold {threshold:.2f}; keeping speakers generic.")

    generic_index = 1
    for speaker in speakers:
        if speaker in mapping:
            continue
        while f"Speaker {generic_index}" in mapping.values():
            generic_index += 1
        mapping[speaker] = f"Speaker {generic_index}"
        generic_index += 1

    return mapping


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    a = a / (np.linalg.norm(a) + 1e-9)
    b = b / (np.linalg.norm(b) + 1e-9)
    return float(np.dot(a, b))


def _speaker_embeddings(
    wav_path: str,
    turns: list,
    speakers: list[str],
    cache: Cache,
    audio_hash: str,
) -> dict[str, np.ndarray]:
    embeddings = {}
    waveform, sample_rate = torchaudio.load(wav_path)
    waveform = _to_mono_16k(waveform, sample_rate)
    encoder = _get_encoder()

    for speaker in speakers:
        cache_name = f"{audio_hash}_speaker_{_safe_name(speaker)}"
        if cache.npy_exists(cache_name):
            embeddings[speaker] = cache.load_npy(cache_name)
            continue

        chunks = []
        for turn in (turn for turn in turns if turn["speaker"] == speaker):
            start = int(turn["start"] * 16000)
            end = min(int(turn["end"] * 16000), waveform.shape[1])
            if (end - start) < int(MIN_CHUNK_SEC * 16000):
                continue
            chunks.append(waveform[:, start:end])
            if len(chunks) >= MAX_CHUNKS_PER_SPEAKER:
                break

        if not chunks:
            continue

        chunk_embeddings = []
        for chunk in chunks:
            try:
                chunk_embeddings.append(_embed(encoder, chunk))
            except Exception:
                pass

        if chunk_embeddings:
            embedding = np.mean(chunk_embeddings, axis=0)
            cache.save_npy(cache_name, embedding)
            embeddings[speaker] = embedding

    return embeddings


def _reference_embedding(participant: dict, cache: Cache) -> np.ndarray:
    encoder = _get_encoder()
    embeddings = []
    for sample_path in participant.get("voice_samples", []):
        path = Path(sample_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(str(path))

        sample_hash = _file_hash(path)
        cache_name = f"participant_{_safe_name(participant['name'])}_{sample_hash}"
        if cache.npy_exists(cache_name):
            embeddings.append(cache.load_npy(cache_name))
            continue

        waveform, sample_rate = _load_audio_file(str(path))
        waveform = _to_mono_16k(waveform, sample_rate)
        embedding = _embed(encoder, waveform)
        cache.save_npy(cache_name, embedding)
        embeddings.append(embedding)

    if not embeddings:
        raise ValueError("no usable voice samples")
    return np.mean(embeddings, axis=0)


def _voice_samples_for(participant: dict) -> list[str]:
    raw = participant.get("voice_samples") or participant.get("voice_sample") or []
    if isinstance(raw, str):
        return [raw]
    return [str(item) for item in raw if item]


_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is not None:
        return _encoder

    try:
        from speechbrain.inference.speaker import EncoderClassifier
    except ImportError:
        from speechbrain.pretrained import EncoderClassifier

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  Loading SpeechBrain ECAPA-TDNN ({device}) ...")
    _encoder = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        run_opts={"device": device},
    )
    return _encoder


def _embed(encoder, waveform: torch.Tensor) -> np.ndarray:
    device = next(encoder.parameters()).device
    with torch.no_grad():
        embedding = encoder.encode_batch(waveform.to(device))
    return embedding.squeeze().cpu().numpy()


def _to_mono_16k(waveform: torch.Tensor, sample_rate: int) -> torch.Tensor:
    if sample_rate != 16000:
        waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    return waveform


def _load_audio_file(path: str) -> tuple[torch.Tensor, int]:
    try:
        return torchaudio.load(path)
    except Exception:
        pass

    command = [
        _ffmpeg_bin(), "-y",
        "-i", path,
        "-ar", "16000", "-ac", "1",
        "-f", "wav", "pipe:1",
    ]
    proc = subprocess.run(command, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace"))
    return torchaudio.load(io.BytesIO(proc.stdout), format="wav")


def _ffmpeg_bin() -> str:
    if Path(_FFMPEG_HOMEBREW).exists():
        return _FFMPEG_HOMEBREW
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("ffmpeg not found")


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unknown"


def _file_hash(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]
