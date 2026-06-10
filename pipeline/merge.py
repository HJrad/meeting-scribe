"""Stage 4 — assign transcript words to speaker segments and form turns."""

from typing import Optional


# ---------------------------------------------------------------------------
# Word → speaker assignment
# ---------------------------------------------------------------------------

def _overlap(w_start: float, w_end: float, s_start: float, s_end: float) -> float:
    return max(0.0, min(w_end, s_end) - max(w_start, s_start))


def assign_words_to_speakers(transcript: dict, diarization: list) -> list:
    """Return flat list of word dicts with an added 'speaker' key."""
    # Collect all words with timestamps from WhisperX aligned segments
    words = []
    for seg in transcript.get("segments", []):
        seg_words = seg.get("words", [])
        if not seg_words:
            # Segment has no word-level timestamps — treat whole segment as one token
            if seg.get("start") is not None and seg.get("end") is not None:
                words.append({
                    "word": seg.get("text", "").strip(),
                    "start": seg["start"],
                    "end": seg["end"],
                })
            continue
        for w in seg_words:
            if w.get("start") is None or w.get("end") is None:
                continue
            words.append({
                "word": w.get("word", ""),
                "start": w["start"],
                "end": w["end"],
            })

    diar = sorted(diarization, key=lambda s: s["start"])

    for word in words:
        ws, we = word["start"], word["end"]
        # Choose speaker segment with maximum time-overlap with the word
        best_label: Optional[str] = None
        best_overlap = -1.0
        for seg in diar:
            ov = _overlap(ws, we, seg["start"], seg["end"])
            if ov > best_overlap:
                best_overlap = ov
                best_label = seg["speaker"]
        # Fallback: midpoint containment
        if best_label is None or best_overlap == 0:
            mid = (ws + we) / 2
            for seg in diar:
                if seg["start"] <= mid <= seg["end"]:
                    best_label = seg["speaker"]
                    break
        word["speaker"] = best_label or "UNKNOWN"

    return words


# ---------------------------------------------------------------------------
# Word list → speaker turns
# ---------------------------------------------------------------------------

def _make_turn(speaker: str, words: list) -> dict:
    text = " ".join(w["word"].strip() for w in words if w["word"].strip())
    return {
        "speaker": speaker,
        "start": words[0]["start"],
        "end": words[-1]["end"],
        "text": text,
        "words": words,
    }


def group_into_turns(words: list) -> list:
    """Merge consecutive same-speaker words into utterance turns."""
    if not words:
        return []

    turns = []
    current_speaker = words[0]["speaker"]
    current_words = [words[0]]

    for word in words[1:]:
        if word["speaker"] == current_speaker:
            current_words.append(word)
        else:
            turns.append(_make_turn(current_speaker, current_words))
            current_speaker = word["speaker"]
            current_words = [word]

    turns.append(_make_turn(current_speaker, current_words))
    return turns
