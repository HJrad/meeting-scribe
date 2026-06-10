"""Metadata loading: manifest YAML (multi-recording) or per-file sidecar YAML."""

from pathlib import Path
from typing import Optional
import re


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_manifest(manifest_path: str) -> dict:
    """Load a multi-recording manifest YAML."""
    import yaml
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def load_sidecar(audio_path: str) -> dict:
    """Load per-file sidecar YAML (legacy / fallback)."""
    base = Path(audio_path)
    for ext in (".yaml", ".yml"):
        p = base.with_suffix(ext)
        if p.exists():
            import yaml
            with open(p, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            print(f"  Loaded sidecar: {p.name}")
            return _normalise_sidecar(raw)

    print(f"  WARNING: No sidecar metadata found for {base.name}")
    return {}


def load_config(config_path: str) -> dict:
    import yaml
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Manifest lookup
# ---------------------------------------------------------------------------

def find_in_manifest(manifest: dict, audio_filename: str) -> tuple[Optional[str], dict]:
    """
    Return (recording_id, normalised_meta) for the entry whose source_audio
    matches audio_filename (basename, case-insensitive).
    Returns (None, {}) if not found.
    """
    needle = audio_filename.lower()
    for rid, raw in manifest_entries(manifest).items():
        if str(raw.get("source_audio", "")).lower() == needle:
            return rid, _normalise_manifest_entry(rid, raw)
    return None, {}


def manifest_entries(manifest: dict) -> dict:
    """Return the manifest's meeting entries."""
    if "meetings" in manifest:
        return manifest.get("meetings", {}) or {}
    return manifest.get("recordings", {}) or {}


# ---------------------------------------------------------------------------
# Normalisation — both formats produce the same internal dict
# ---------------------------------------------------------------------------

def _normalise_manifest_entry(meeting_id: str, raw: dict) -> dict:
    """Convert a meeting manifest entry to the internal metadata dict."""
    return _normalise_meeting_entry(meeting_id, raw)


def _normalise_meeting_entry(meeting_id: str, raw: dict) -> dict:
    """Convert a meeting manifest entry to the internal metadata dict."""
    participants = _normalise_participants(raw.get("participants", []))
    title = raw.get("title") or raw.get("meeting_title") or meeting_id
    source_audio = raw.get("source_audio", "")

    return {
        "meeting_id":       meeting_id,
        "recording_type":   "meeting",
        "num_speakers":     int(raw.get("num_speakers") or len(participants) or 2),
        "skip_diarization": bool(raw.get("skip_diarization", False)),
        "language":         _normalise_language(raw.get("language", "en")),
        "title":            title,
        "date":             str(raw.get("date") or ""),
        "participants":     participants,
        "speaker_map":      raw.get("speaker_map", {}),
        "topic":            raw.get("topic", ""),
        "organization":     raw.get("organization", ""),
        "project":          raw.get("project", ""),
        "summary_focus":    raw.get("summary_focus", ""),
        "summary_language": raw.get("summary_language", "en"),
        "notes":            raw.get("notes", ""),
        "source_audio":     source_audio,
        "output_stem":      raw.get("output_stem") or _meeting_output_stem(meeting_id, title, source_audio),
    }


def _normalise_participants(raw_participants) -> list[dict]:
    participants = []
    for item in raw_participants or []:
        if isinstance(item, str):
            participants.append({"name": item, "role": "participant"})
        elif isinstance(item, dict):
            name = item.get("name")
            if name:
                participants.append({
                    "name": name,
                    "role": item.get("role", "participant"),
                    **{k: v for k, v in item.items() if k not in {"name", "role"}},
                })
    return participants


def _meeting_output_stem(meeting_id: str, title: str, source_audio: str) -> str:
    if meeting_id:
        base = meeting_id
    elif source_audio:
        base = Path(source_audio).stem
    else:
        base = title or "meeting"

    title_slug = re.sub(r"[^A-Za-z0-9]+", "-", title or "").strip("-").lower()
    if title_slug and title_slug.lower() not in base.lower():
        return f"{base}_{title_slug[:40]}"
    return base


def _normalise_sidecar(raw: dict) -> dict:
    """Convert a legacy per-file sidecar YAML to the internal metadata dict."""
    meeting = raw.get("meeting", raw)
    participants = _normalise_participants(meeting.get("participants", []))
    return {
        "recording_type":   "meeting",
        "num_speakers":     int(meeting.get("num_speakers") or len(participants) or 2),
        "skip_diarization": bool(meeting.get("skip_diarization", False)),
        "language":         _normalise_language(meeting.get("language", "en")),
        "title":            meeting.get("title", ""),
        "date":             str(meeting.get("date") or ""),
        "participants":     participants,
        "speaker_map":      meeting.get("speaker_map", {}),
        "topic":            meeting.get("topic", ""),
        "project":          meeting.get("project", ""),
        "summary_focus":    meeting.get("summary_focus", ""),
        "summary_language": meeting.get("summary_language", "en"),
        "notes":            meeting.get("notes", ""),
        "source_audio":     "",
    }


def _normalise_language(raw) -> str:
    """Return one WhisperX transcription language, or auto for mixed/unknown audio."""
    if raw is None:
        return "auto"

    if isinstance(raw, list):
        values = [str(item).strip().lower() for item in raw if str(item).strip()]
        return values[0] if len(values) == 1 else "auto"

    value = str(raw).strip().lower()
    if value in {"", "auto", "detect", "multilingual", "mixed"}:
        return "auto"

    separators = [",", "/", "+"]
    if any(separator in value for separator in separators):
        return "auto"

    return value
