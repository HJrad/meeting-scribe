"""Stage 3 — pyannote speaker-diarization-3.1.

Constraints:
  - Use token=  (not use_auth_token=)
  - Load audio via torchaudio; pass {"waveform": …, "sample_rate": …}
  - Resolve annotation via hasattr fallbacks (.diarization / .segmentation)
"""

import torch
import torchaudio

from .cache import Cache

def _device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _unwrap_annotation(obj):
    """
    Return the pyannote Annotation (has .itertracks) regardless of how the
    pipeline wraps its output.  Handles:
      - bare Annotation returned directly
      - dataclass / namedtuple with a known field name
      - any wrapper: walk all fields / __dict__ looking for itertracks
    """
    if hasattr(obj, "itertracks"):
        return obj

    # Known field names across pyannote versions
    for attr in ("diarization", "annotation", "segmentation"):
        candidate = getattr(obj, attr, None)
        if candidate is not None and hasattr(candidate, "itertracks"):
            return candidate

    # Generic fallback: namedtuple fields
    if hasattr(obj, "_fields"):
        for field in obj._fields:
            candidate = getattr(obj, field)
            if hasattr(candidate, "itertracks"):
                return candidate

    # Generic fallback: instance __dict__
    for candidate in vars(obj).values():
        if hasattr(candidate, "itertracks"):
            return candidate

    raise RuntimeError(
        f"Cannot find an Annotation inside {type(obj).__name__}. "
        f"Fields: {getattr(obj, '_fields', None) or list(vars(obj).keys())}"
    )


def diarize(wav_path: str, hf_token: str, cache: Cache, audio_hash: str, num_speakers: int = 2) -> list:
    """Return list of {start, end, speaker} dicts; result is cached."""
    if cache.exists(audio_hash, "diarization", "json"):
        segs = cache.load_json(audio_hash, "diarization")
        speakers = {s["speaker"] for s in segs}
        print(f"  [cache hit] {len(segs)} segments, speakers: {speakers}")
        return segs

    from pyannote.audio import Pipeline  # deferred

    device = _device()
    print(f"  Loading pyannote/speaker-diarization-3.1 (device={device}) …")
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )
    pipeline = pipeline.to(device)

    # Load via torchaudio — never pass a raw file path to pyannote
    waveform, sample_rate = torchaudio.load(wav_path)
    audio_input = {"waveform": waveform, "sample_rate": sample_rate}

    print(f"  Running diarization (num_speakers={num_speakers}) …")
    raw_result = pipeline(audio_input, num_speakers=num_speakers)

    annotation = _unwrap_annotation(raw_result)

    segments = [
        {"start": segment.start, "end": segment.end, "speaker": label}
        for segment, _track, label in annotation.itertracks(yield_label=True)
    ]

    cache.save_json(audio_hash, "diarization", segments)
    speakers = {s["speaker"] for s in segments}
    print(f"  Done — {len(segments)} segments, speakers: {speakers}")
    return segments
