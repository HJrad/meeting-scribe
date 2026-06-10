"""Stage 6 — write plain text, timestamped text, and full JSON outputs."""

import json
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _row(label: str, value) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return f"  {label:<18}{value}"


def _metadata_header(meta: dict) -> str:
    sep = "=" * 60
    lines = [sep, "MEETING TRANSCRIPT", sep]
    participants = meta.get("participants", [])
    participant_names = ", ".join(p.get("name", "") for p in participants if p.get("name"))
    rows = [
        _row("Meeting:",      meta.get("title")),
        _row("Date:",         meta.get("date")),
        _row("Type:",         meta.get("recording_type", "meeting")),
        _row("Language:",     meta.get("language")),
        _row("Detected:",     meta.get("detected_language")),
        _row("Topic:",        meta.get("topic")),
        _row("Project:",      meta.get("project")),
        _row("Participants:", participant_names),
    ]
    lines += [r for r in rows if r]

    if meta.get("notes"):
        lines += ["", f"  Notes: {meta['notes']}"]

    lines += [sep, ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_plain_text(
    turns: list,
    speaker_map: dict,
    meta: dict,
    output_path: str,
) -> None:
    lines = [_metadata_header(meta)]
    for turn in turns:
        name = speaker_map.get(turn["speaker"], turn["speaker"])
        lines += [f"[{name}]", turn["text"], ""]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Plain text      → {output_path}")


def write_timestamped_text(
    turns: list,
    speaker_map: dict,
    meta: dict,
    output_path: str,
) -> None:
    lines = [_metadata_header(meta)]
    for turn in turns:
        name = speaker_map.get(turn["speaker"], turn["speaker"])
        lines += [f"[{_ts(turn['start'])}] [{name}]", turn["text"], ""]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Timestamped txt → {output_path}")


def write_json(
    turns: list,
    speaker_map: dict,
    meta: dict,
    audio_hash: str,
    audio_path: str,
    output_path: str,
) -> None:
    participant_roles = {
        p.get("name"): p.get("role", "participant")
        for p in meta.get("participants", [])
        if p.get("name")
    }

    enriched_turns = []
    for turn in turns:
        name = speaker_map.get(turn["speaker"], turn["speaker"])
        role = participant_roles.get(name, "participant")

        enriched_turns.append({
            "speaker_label": turn["speaker"],
            "speaker_name":  name,
            "role":          role,
            "start":         round(turn["start"], 3),
            "end":           round(turn["end"], 3),
            "duration":      round(turn["end"] - turn["start"], 3),
            "text":          turn["text"],
            "words": [
                {"word": w["word"], "start": round(w["start"], 3), "end": round(w["end"], 3)}
                for w in turn.get("words", [])
            ],
        })

    # Build clean metadata block (strip internal _ keys)
    meta_out = {k: v for k, v in meta.items() if not k.startswith("_") and v not in ("", None)}

    doc = {
        "audio_file":        Path(audio_path).name,
        "audio_hash_sha256": audio_hash,
        "language":          meta.get("language", "en"),
        "recording_type":    meta.get("recording_type", "meeting"),
        "generated_at":      datetime.now(timezone.utc).isoformat(),
        "metadata":          meta_out,
        "speaker_map":       speaker_map,
        "turns":             enriched_turns,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"  JSON            → {output_path}")
