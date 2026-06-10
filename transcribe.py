#!/usr/bin/env python3
"""
Personal Transcription Pipeline
===============================
Transcribes and diarizes meetings and single-speaker recordings.

Usage — single file:
    python transcribe.py meetings/team-sync.m4a --manifest config/meetings.yaml

Usage — by recording ID:
    python transcribe.py TEAM_SYNC_001 --manifest config/meetings.yaml

Usage — batch all recordings in manifest:
    python transcribe.py --manifest config/meetings.yaml --all
"""

import warnings
warnings.filterwarnings("ignore", message="torchcodec is not installed")
warnings.filterwarnings("ignore", message=".*torchcodec is not installed correctly.*")
warnings.filterwarnings("ignore", message="torchaudio._backend.list_audio_backends")
warnings.filterwarnings("ignore", message="Lightning automatically upgraded")
warnings.filterwarnings("ignore", message="In 2.9, this function's implementation will be changed")

import argparse
import os
import re
import sys
from pathlib import Path


def _build_initial_prompt(meta: dict) -> str:
    """
    Prime Whisper with meeting titles, participant names, and project terms.
    Limit: ~224 Whisper tokens, roughly 448 characters.
    """
    parts = []

    title = meta.get("title") or meta.get("topic")
    if title:
        parts.append(title)

    for participant in meta.get("participants", []):
        name = participant.get("name", "")
        role = participant.get("role", "")
        if name and role:
            parts.append(f"{name}, {role}")
        elif name:
            parts.append(name)

    org = meta.get("organization", "")
    if org:
        names = [n.strip() for n in re.split(r"[;,]", org) if n.strip()]
        parts.extend(names)

    project = meta.get("project", "")
    if project:
        parts.append(project)

    notes = meta.get("notes", "")
    if notes:
        parts.append(notes)

    prompt = ", ".join(parts)
    return prompt[:448]


def _participant_names(meta: dict) -> list[str]:
    names = [
        participant.get("name", "").strip()
        for participant in meta.get("participants", [])
        if participant.get("name", "").strip()
    ]
    if names:
        return names

    return ["Speaker 1"]


def _speaker_map_from_metadata(turns: list, meta: dict) -> dict:
    """Best-effort speaker labels from explicit metadata or participant order."""
    speakers = sorted({turn["speaker"] for turn in turns})
    explicit_map = meta.get("speaker_map") or {}
    if explicit_map:
        return {
            label: explicit_map.get(label, explicit_map.get(str(label), label))
            for label in speakers
        }

    names = _participant_names(meta)
    mapping = {}
    for index, label in enumerate(speakers):
        mapping[label] = names[index] if index < len(names) else f"Speaker {index + 1}"
    return mapping


def _has_voice_samples(meta: dict) -> bool:
    for participant in meta.get("participants", []):
        if participant.get("voice_sample") or participant.get("voice_samples"):
            return True
    return False


def _load_dotenv() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Transcribe + diarize audio recordings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "audio",
        nargs="?",
        help="Audio file path OR meeting ID (e.g. TEAM_SYNC_001). "
             "Omit with --all to process every entry in the manifest.",
    )
    p.add_argument(
        "--manifest", "-m",
        default="config/meetings.yaml",
        metavar="FILE",
        help="Meeting manifest YAML (default: config/meetings.yaml)",
    )
    p.add_argument(
        "--all", "-a",
        action="store_true",
        dest="process_all",
        help="Process every recording in the manifest (requires --manifest)",
    )
    p.add_argument("--config",      default="config/config.yaml",  metavar="FILE")
    p.add_argument("--hf-token",    metavar="TOKEN")
    p.add_argument("--output-dir",  metavar="DIR")
    p.add_argument("--cache-dir",   metavar="DIR")
    p.add_argument("--recordings-dir", default="meetings", metavar="DIR",
                   help="Directory containing manifest audio files (default: meetings/)")
    p.add_argument("--no-cache", action="store_true",
                   help="Clear per-audio cache and reprocess from scratch")
    return p


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

def resolve_config(args: argparse.Namespace) -> dict:
    from pipeline.metadata import load_config

    cfg: dict = {}
    if Path(args.config).exists():
        cfg = load_config(args.config)
    elif args.config != "config/config.yaml":
        sys.exit(f"ERROR: Config file not found: {args.config}")

    if args.hf_token:        cfg["hf_token"]      = args.hf_token
    if args.output_dir:      cfg["output_dir"]     = args.output_dir
    if args.cache_dir:       cfg["cache_dir"]      = args.cache_dir

    cfg.setdefault("cache_dir",        ".cache")
    cfg.setdefault("output_dir",       "output/meetings")
    cfg.setdefault("default_language", "en")

    return cfg


# ---------------------------------------------------------------------------
# Single-recording pipeline
# ---------------------------------------------------------------------------

def run_one(audio_path: str, meta: dict, cfg: dict, args: argparse.Namespace) -> None:
    from pipeline.cache      import Cache
    from pipeline.audio      import convert_to_wav
    from pipeline.transcribe_stage import transcribe
    from pipeline.diarize    import diarize
    from pipeline.identify   import identify_participants
    from pipeline.merge      import assign_words_to_speakers, group_into_turns
    from pipeline.output     import write_plain_text, write_timestamped_text, write_json

    hf_token:  str = cfg.get("hf_token") or os.environ.get("HF_TOKEN", "")

    # Metadata fields
    language         = meta.get("language") or cfg.get("default_language", "en")
    participant_name = _participant_names(meta)[0]
    skip_diarization = meta.get("skip_diarization", False)
    num_speakers     = meta.get("num_speakers", 2)
    recording_type   = meta.get("recording_type", "meeting")

    label = meta.get("meeting_id") or Path(audio_path).name

    print()
    print("=" * 60)
    print(f"  {label}")
    print(f"  {Path(audio_path).name}  |  {language}  |  {recording_type}")
    print("=" * 60)

    if not hf_token and not skip_diarization:
        sys.exit("ERROR: HuggingFace token required. Set hf_token in config or HF_TOKEN env var.")

    # Cache
    cache = Cache(cfg["cache_dir"])
    audio_hash = cache.audio_hash(audio_path)

    if args.no_cache:
        print("  [--no-cache] Clearing cached stages …")
        cache.clear_audio(audio_hash)

    print(f"  SHA-256: {audio_hash}")

    # ── Stage 1: convert ─────────────────────────────────────────────────────
    print("\n[1] Converting to 16 kHz mono WAV …")
    wav_path = convert_to_wav(audio_path, cache, audio_hash)

    # ── Stage 2: transcribe ──────────────────────────────────────────────────
    print("\n[2] Transcribing with WhisperX large-v3 …")
    initial_prompt = _build_initial_prompt(meta)
    transcript = transcribe(wav_path, language, cache, audio_hash, initial_prompt)
    if transcript.get("requested_language") == "auto" and transcript.get("language"):
        meta["detected_language"] = transcript["language"]

    # ── Stage 3+4: diarize + merge  (skipped for voice messages) ─────────────
    if skip_diarization:
        print(f"\n[3] Diarization skipped ({recording_type}) — assigning all speech to {participant_name}")
        from pipeline.merge import group_into_turns
        # Flatten all words and assign them to the single speaker
        words = []
        for seg in transcript.get("segments", []):
            for w in seg.get("words", []):
                if w.get("start") is not None:
                    words.append({**w, "speaker": "SPEAKER_00"})
        turns = group_into_turns(words)
        speaker_map = meta.get("speaker_map") or {"SPEAKER_00": participant_name}
        print(f"  {len(words)} words → {len(turns)} turns (single speaker)")

    else:
        print("\n[3] Running pyannote speaker diarization …")
        diarization = diarize(wav_path, hf_token, cache, audio_hash,
                              num_speakers=num_speakers)

        print("\n[4] Merging transcript with speaker segments …")
        from pipeline.merge import assign_words_to_speakers
        words = assign_words_to_speakers(transcript, diarization)
        turns = group_into_turns(words)
        print(f"  {len(words)} words → {len(turns)} turns")

        # ── Stage 5: identify or label speakers ───────────────────────────────
        if meta.get("speaker_map"):
            print("\n[5] Labelling diarized speakers from explicit speaker_map ...")
            speaker_map = _speaker_map_from_metadata(turns, meta)
        elif _has_voice_samples(meta):
            print("\n[5] Identifying participants from voice samples ...")
            speaker_map = identify_participants(
                turns=turns,
                wav_path=wav_path,
                cache=cache,
                audio_hash=audio_hash,
                participants=meta.get("participants", []),
            )
        else:
            print("\n[5] Labelling diarized speakers from participant order ...")
            speaker_map = _speaker_map_from_metadata(turns, meta)
            print("  NOTE: Speaker names are assigned by diarization label order.")
            print("        Add voice_sample per participant or speaker_map in config/meetings.yaml for exact attribution.")

        print()
        for label_, name in speaker_map.items():
            print(f"  {label_} → {name}")

    # ── Stage 6: write outputs ────────────────────────────────────────────────
    print("\n[6] Writing outputs …")
    out_dir = Path(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = meta.get("output_stem") or meta.get("klarname") or Path(audio_path).stem
    base = out_dir / stem

    write_plain_text(turns, speaker_map, meta, str(base) + ".txt")
    write_timestamped_text(turns, speaker_map, meta, str(base) + "_timestamped.txt")
    write_json(turns, speaker_map, meta, audio_hash, audio_path, str(base) + ".json")

    print(f"\n  Done → output/{stem}.*")
    return {
        "plain_text": str(base) + ".txt",
        "timestamped_text": str(base) + "_timestamped.txt",
        "json": str(base) + ".json",
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    _load_dotenv()
    parser = build_parser()
    args   = parser.parse_args()
    cfg    = resolve_config(args)

    from pipeline.metadata import load_manifest, find_in_manifest, load_sidecar, manifest_entries

    recordings_dir = Path(args.recordings_dir)

    # ── Batch mode ────────────────────────────────────────────────────────────
    if args.process_all:
        manifest_path = args.manifest
        if not Path(manifest_path).exists():
            sys.exit(f"ERROR: Manifest not found: {manifest_path}")

        manifest = load_manifest(manifest_path)
        entries  = manifest_entries(manifest)
        if not entries:
            sys.exit("ERROR: No recordings found in manifest.")

        print(f"==> Batch mode: {len(entries)} recordings in {manifest_path}")
        failed = []
        for iid, raw in entries.items():
            audio_file = raw.get("source_audio", "")
            audio_path = recordings_dir / audio_file
            if not audio_path.exists():
                print(f"\n  SKIP {iid}: file not found: {audio_path}")
                continue
            from pipeline.metadata import _normalise_manifest_entry
            meta = _normalise_manifest_entry(iid, raw)
            try:
                run_one(str(audio_path), meta, cfg, args)
            except Exception as exc:
                print(f"\n  ERROR in {iid}: {exc}")
                failed.append(iid)

        if failed:
            print(f"\nCompleted with errors in: {failed}")
        else:
            print("\nAll recordings processed successfully.")
        return

    # ── Single file mode ──────────────────────────────────────────────────────
    if not args.audio:
        parser.print_help()
        sys.exit(1)

    audio_arg = args.audio
    manifest  = {}
    meta      = {}

    # Try to load manifest if it exists (even for single-file mode)
    if Path(args.manifest).exists():
        manifest = load_manifest(args.manifest)

    # audio_arg is a meeting ID from the manifest
    if manifest and audio_arg in manifest_entries(manifest):
        raw = manifest_entries(manifest).get(audio_arg)
        if not raw:
            sys.exit(f"ERROR: Meeting ID '{audio_arg}' not found in manifest.")
        from pipeline.metadata import _normalise_manifest_entry
        meta       = _normalise_manifest_entry(audio_arg, raw)
        audio_path = recordings_dir / raw["source_audio"]

    # audio_arg is a file path
    else:
        audio_path = Path(audio_arg)
        if not audio_path.exists():
            sys.exit(f"ERROR: Audio file not found: {audio_path}")

        # Look up in manifest by filename
        if manifest:
            _, meta = find_in_manifest(manifest, audio_path.name)

        # Fall back to sidecar if not in manifest
        if not meta:
            meta = load_sidecar(str(audio_path))

    if not audio_path.exists():
        sys.exit(f"ERROR: Audio file not found: {audio_path}")

    run_one(str(audio_path), meta, cfg, args)


if __name__ == "__main__":
    main()
