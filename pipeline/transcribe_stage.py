"""Stage 2 — WhisperX transcription with word-level timestamps.

Device selection:
  CUDA (EC2 GPU)  → float16, batch_size 32   (fast)
  CPU (Apple M1)  → int8,    batch_size 8    (MPS not supported by faster-whisper)
"""

import torch

from .cache import Cache


def _whisper_device() -> tuple[str, str, int]:
    """Return (device, compute_type, batch_size) for this host."""
    if torch.cuda.is_available():
        return "cuda", "float16", 32
    return "cpu", "int8", 8


def transcribe(
    wav_path: str,
    language: str,
    cache: Cache,
    audio_hash: str,
    initial_prompt: str = "",  # kept for API compat, not passed to WhisperX
) -> dict:
    """Return transcript dict with word-level timestamps; result is cached."""
    language_label, whisper_language = _language_for_whisper(language)
    stage = f"transcript_{language_label}"
    if cache.exists(audio_hash, stage, "json"):
        data = cache.load_json(audio_hash, stage)
        print(f"  [cache hit] {len(data.get('segments', []))} segments")
        return data

    import whisperx  # deferred — slow import

    device, compute_type, batch_size = _whisper_device()
    print(f"  Loading WhisperX large-v3 ({device} / {compute_type}) …")

    model_kwargs = {
        "device": device,
        "compute_type": compute_type,
    }
    if whisper_language:
        model_kwargs["language"] = whisper_language

    model = whisperx.load_model("large-v3", **model_kwargs)

    audio  = whisperx.load_audio(wav_path)
    transcribe_kwargs = {"batch_size": batch_size}
    if whisper_language:
        transcribe_kwargs["language"] = whisper_language
    result = model.transcribe(audio, **transcribe_kwargs)

    print("  Aligning word timestamps …")
    detected_language = result.get("language") or whisper_language
    try:
        if not detected_language:
            raise RuntimeError("WhisperX did not return a detected language")
        model_a, meta = whisperx.load_align_model(
            language_code=detected_language, device=device
        )
        aligned = whisperx.align(
            result["segments"],
            model_a,
            meta,
            audio,
            device=device,
            return_char_alignments=False,
        )
    except Exception as exc:
        print(f"  WARNING: alignment failed ({exc}); using unaligned segments.")
        aligned = {"segments": result["segments"], "word_segments": []}

    output = {
        "language": detected_language or language_label,
        "requested_language": language_label,
        "segments": aligned["segments"],
        "word_segments": aligned.get("word_segments", []),
    }
    cache.save_json(audio_hash, stage, output)
    print(f"  Done — {len(output['segments'])} segments")
    return output


def _language_for_whisper(language: str) -> tuple[str, str | None]:
    label = str(language or "auto").strip().lower()
    if label in {"", "auto", "detect", "multilingual", "mixed"}:
        return "auto", None
    if any(separator in label for separator in [",", "/", "+"]):
        return "auto", None
    return label, label
