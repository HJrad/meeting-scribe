#!/usr/bin/env python3
"""Personal meeting transcriber CLI."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from personal_transcriber.summary import DEFAULT_MODEL, generate_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Transcribe meetings and generate professional summaries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python meeting.py run meetings/team-sync.m4a --title "Team Sync" --participants "Sam,Alice"
  python meeting.py sample meetings/team-sync.m4a --name Sam --start 00:12:30 --duration 30
  python meeting.py transcribe meetings/team-sync.m4a --participants "Sam,Alice,Bob" --participant-samples "Sam=voice_samples/sam.m4a,Alice=voice_samples/alice.m4a"
  python meeting.py summarize output/team-sync.json
  python meeting.py batch --manifest config/meetings.yaml
""",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Transcribe one meeting, then summarize it")
    _add_transcribe_args(run)
    _add_summary_args(run, allow_skip=True)

    transcribe = subparsers.add_parser("transcribe", help="Transcribe one meeting")
    _add_transcribe_args(transcribe)

    sample = subparsers.add_parser("sample", help="Extract a participant voice sample with ffmpeg")
    sample.add_argument("audio", help="Source meeting audio/video file")
    sample.add_argument("--name", required=True, help="Participant name, used for the output filename")
    sample.add_argument("--start", required=True, help="Start time, e.g. 75, 01:15, or 00:12:30")
    sample.add_argument("--duration", type=float, default=30, help="Clip length in seconds (default: 30)")
    sample.add_argument("--output", help="Output path (default: voice_samples/{name}.wav)")

    summarize = subparsers.add_parser("summarize", help="Summarize an existing transcript JSON")
    summarize.add_argument("transcript_json", help="Transcript JSON produced by this project")
    _add_summary_args(summarize)

    batch = subparsers.add_parser("batch", help="Run every meeting in a manifest")
    batch.add_argument("--manifest", "-m", default="config/meetings.yaml", help="Meeting manifest YAML")
    batch.add_argument("--meetings-dir", default="meetings", help="Directory containing meeting audio")
    batch.add_argument("--config", default="config/config.yaml", help="Transcription config YAML")
    batch.add_argument("--output-dir", default="output/meetings", help="Output directory")
    batch.add_argument("--cache-dir", default=".cache", help="Cache directory")
    batch.add_argument("--hf-token", help="HuggingFace token for diarization")
    batch.add_argument("--no-cache", action="store_true", help="Clear per-audio cache and reprocess")
    _add_summary_args(batch, allow_skip=True)

    return parser


def _add_transcribe_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("audio", help="Meeting audio/video file")
    parser.add_argument("--title", help="Meeting title")
    parser.add_argument("--date", help="Meeting date, e.g. 2026-05-20")
    parser.add_argument("--participants", help="Comma-separated participant names")
    parser.add_argument("--participant-samples", help="Comma-separated voice refs, e.g. Sam=voice_samples/sam.m4a,Alice=voice_samples/alice.m4a")
    parser.add_argument("--speaker-map", help="Comma-separated labels, e.g. SPEAKER_00=Sam,SPEAKER_01=Alice")
    parser.add_argument("--language", default="en", help="Recording language: en, de, or auto (default: en)")
    parser.add_argument("--speakers", type=int, help="Expected number of speakers")
    parser.add_argument("--topic", help="Meeting topic")
    parser.add_argument("--project", help="Project/client/context")
    parser.add_argument("--notes", help="Extra words/names to prime transcription")
    parser.add_argument("--config", default="config/config.yaml", help="Transcription config YAML")
    parser.add_argument("--output-dir", default="output/meetings", help="Output directory")
    parser.add_argument("--cache-dir", default=".cache", help="Cache directory")
    parser.add_argument("--hf-token", help="HuggingFace token for diarization")
    parser.add_argument("--skip-diarization", action="store_true", help="Treat the recording as single speaker")
    parser.add_argument("--no-cache", action="store_true", help="Clear per-audio cache and reprocess")


def _add_summary_args(parser: argparse.ArgumentParser, allow_skip: bool = False) -> None:
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI model for summaries (default: {DEFAULT_MODEL})")
    parser.add_argument("--summary-output", help="Markdown summary output path")
    parser.add_argument("--summary-focus", help="Extra summary focus, e.g. business model, customers, pricing, technical risks")
    parser.add_argument("--summary-language", help="Summary output language(s), independent from transcription language. Examples: en, de, en,de")
    if allow_skip:
        parser.add_argument("--skip-summary", action="store_true", help="Only transcribe, do not summarize")


def main() -> None:
    _load_dotenv()
    args = build_parser().parse_args()

    if args.command == "summarize":
        _summarize(args.transcript_json, args)
    elif args.command == "sample":
        _extract_voice_sample(args)
    elif args.command == "batch":
        _run_batch(args)
    else:
        outputs = _transcribe_one(args.audio, _meta_from_args(args), args)
        if args.command == "run" and not args.skip_summary:
            _summarize(outputs["json"], args)


def _transcribe_one(audio_path: str, meta: dict, args: argparse.Namespace) -> dict:
    from transcribe import resolve_config, run_one

    transcribe_args = argparse.Namespace(
        config=args.config,
        hf_token=getattr(args, "hf_token", None),
        output_dir=getattr(args, "output_dir", None),
        cache_dir=getattr(args, "cache_dir", ".cache"),
        no_cache=getattr(args, "no_cache", False),
    )
    cfg = resolve_config(transcribe_args)
    cfg["speaker_identification"] = False
    cfg["output_dir"] = getattr(args, "output_dir", None) or cfg.get("output_dir", "output/meetings")
    cfg["cache_dir"] = getattr(args, "cache_dir", None) or cfg.get("cache_dir", ".cache")

    outputs = run_one(audio_path, meta, cfg, transcribe_args)
    return outputs or {}


def _run_batch(args: argparse.Namespace) -> None:
    from pipeline.metadata import _normalise_manifest_entry, load_manifest, manifest_entries

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        sys.exit(f"ERROR: Manifest not found: {manifest_path}")

    entries = manifest_entries(load_manifest(str(manifest_path)))
    if not entries:
        sys.exit(f"ERROR: No meetings found in {manifest_path}")

    failed = []
    for meeting_id, raw in entries.items():
        audio_path = Path(args.meetings_dir) / raw.get("source_audio", "")
        if not audio_path.exists():
            print(f"\n  SKIP {meeting_id}: file not found: {audio_path}")
            continue

        meta = _normalise_manifest_entry(meeting_id, raw)
        meta.setdefault("output_stem", meeting_id)
        try:
            outputs = _transcribe_one(str(audio_path), meta, args)
            if not args.skip_summary:
                _summarize(outputs["json"], args)
        except Exception as exc:
            print(f"\n  ERROR in {meeting_id}: {exc}")
            failed.append(meeting_id)

    if failed:
        print(f"\nCompleted with errors in: {', '.join(failed)}")
    else:
        print("\nAll available meetings processed successfully.")


def _summarize(transcript_json: str, args: argparse.Namespace) -> None:
    transcript_path = _resolve_transcript_path(transcript_json)
    output_paths = generate_summary(
        transcript_path,
        output_path=getattr(args, "summary_output", None),
        model=getattr(args, "model", DEFAULT_MODEL),
        summary_focus=getattr(args, "summary_focus", None),
        summary_language=getattr(args, "summary_language", None),
    )
    for output_path in output_paths:
        print(f"  Summary         -> {output_path}")


def _resolve_transcript_path(transcript_json: str) -> Path:
    path = Path(transcript_json)
    if path.exists():
        return path

    candidates = sorted(Path("output/meetings").glob("*.json"))
    message = [f"ERROR: Transcript JSON not found: {path}"]
    if candidates:
        message.append("")
        message.append("Available transcript JSON files:")
        message.extend(f"  - {candidate}" for candidate in candidates)
    sys.exit("\n".join(message))


def _extract_voice_sample(args: argparse.Namespace) -> None:
    audio_path = Path(args.audio)
    if not audio_path.exists():
        sys.exit(f"ERROR: Audio file not found: {audio_path}")

    output_path = Path(args.output) if args.output else Path("voice_samples") / f"{_safe_stem(args.name)}.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        _ffmpeg_bin(),
        "-y",
        "-ss", args.start,
        "-i", str(audio_path),
        "-t", str(args.duration),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        str(output_path),
    ]
    proc = subprocess.run(command, capture_output=True)
    if proc.returncode != 0:
        sys.exit(f"ERROR: ffmpeg failed:\n{proc.stderr.decode(errors='replace')}")

    print(f"  Voice sample    -> {output_path}")
    print(f"  Manifest entry  -> voice_sample: {output_path}")


def _meta_from_args(args: argparse.Namespace) -> dict:
    sample_map = _parse_participant_samples(args.participant_samples)
    participants = [
        {
            "name": name.strip(),
            "role": "participant",
            **({"voice_sample": sample_map[name.strip()]} if name.strip() in sample_map else {}),
        }
        for name in (args.participants or "").split(",")
        if name.strip()
    ]
    title = args.title or Path(args.audio).stem
    return {
        "recording_type": "meeting",
        "language": args.language,
        "num_speakers": args.speakers or len(participants) or 2,
        "skip_diarization": args.skip_diarization,
        "title": title,
        "date": args.date or "",
        "participants": participants,
        "speaker_map": _parse_speaker_map(args.speaker_map),
        "topic": args.topic or "",
        "project": args.project or "",
        "summary_focus": getattr(args, "summary_focus", None) or "",
        "summary_language": getattr(args, "summary_language", None) or "en",
        "notes": args.notes or "",
        "source_audio": Path(args.audio).name,
        "output_stem": _safe_stem(title),
    }


def _parse_speaker_map(raw: str | None) -> dict:
    mapping = {}
    for item in (raw or "").split(","):
        if "=" not in item:
            continue
        label, name = item.split("=", 1)
        if label.strip() and name.strip():
            mapping[label.strip()] = name.strip()
    return mapping


def _parse_participant_samples(raw: str | None) -> dict:
    mapping = {}
    for item in (raw or "").split(","):
        if "=" not in item:
            continue
        name, path = item.split("=", 1)
        if name.strip() and path.strip():
            mapping[name.strip()] = path.strip()
    return mapping


def _safe_stem(value: str) -> str:
    import re

    stem = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return stem or "meeting"


def _ffmpeg_bin() -> str:
    homebrew = Path("/opt/homebrew/opt/ffmpeg/bin/ffmpeg")
    if homebrew.exists():
        return str(homebrew)
    found = shutil.which("ffmpeg")
    if found:
        return found
    sys.exit("ERROR: ffmpeg not found. Install it with: brew install ffmpeg")


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


if __name__ == "__main__":
    main()
