"""Technical meeting-notes generation from transcript JSON."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path


DEFAULT_MODEL = "gpt-4o-mini"


def load_transcript(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def transcript_to_text(doc: dict, max_chars: int = 120_000) -> str:
    """Render timestamped turns compactly enough for an LLM prompt."""
    lines = []
    for turn in doc.get("turns", []):
        start = _format_ts(turn.get("start", 0))
        speaker = turn.get("speaker_name") or turn.get("speaker_label") or "Speaker"
        text = str(turn.get("text", "")).strip()
        if text:
            lines.append(f"[{start}] {speaker}: {text}")

    rendered = "\n".join(lines)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[:max_chars] + "\n\n[Transcript truncated because it exceeded the prompt budget.]"


def generate_summary(
    transcript_path: str | Path,
    output_path: str | Path | None = None,
    model: str = DEFAULT_MODEL,
    summary_focus: str | None = None,
    summary_language=None,
) -> list[Path]:
    """Generate one or more technical meeting summary markdown files."""
    transcript_path = Path(transcript_path)
    doc = load_transcript(transcript_path)
    transcript = transcript_to_text(doc)

    languages = _summary_languages(doc, summary_language)
    output_paths = []
    for language_code in languages:
        markdown = summarize_with_openai(
            doc,
            transcript,
            model=model,
            summary_focus=summary_focus,
            summary_language=language_code,
        )
        path = _summary_output_path(transcript_path, output_path, language_code, len(languages) > 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
        output_paths.append(path)
    return output_paths


def summarize_with_openai(
    doc: dict,
    transcript: str,
    model: str = DEFAULT_MODEL,
    summary_focus: str | None = None,
    summary_language=None,
) -> str:
    """Call OpenAI to produce technical meeting notes."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; add it to .env or your shell environment.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is not installed. Run: pip install openai") from exc

    client = OpenAI(api_key=api_key)
    output_language = _summary_language_name(summary_language or "en")
    metadata = _summary_metadata(doc, summary_focus=summary_focus, summary_language=output_language)

    system = (
        "You are a senior technical meeting scribe for software engineering teams. "
        "Produce accurate, useful engineering notes from the transcript. Capture "
        "technical decisions, tradeoffs, architecture context, implementation details, "
        "bugs, blockers, owners, due dates, systems, repositories, APIs, tickets, "
        "environments, data models, business context, customer impact, product "
        "requirements, commercial constraints, strategic priorities, and follow-up "
        "work. Do not let technical implementation details crowd out business "
        "importance. Distinguish clearly between decided, proposed, and unresolved "
        "items. Do not invent facts. If something is not specified, write 'Not "
        "specified'. Preserve technical and business names exactly when possible."
    )
    user = f"""Meeting metadata:
{metadata}

Transcript:
{transcript}

The transcript language is the original meeting language. Do not translate or rewrite the transcript itself.
Write the summary in {output_language}. Use the markdown section headings below, translated naturally into {output_language}.

Write the output in markdown with these sections:
# Technical Meeting Notes
## Meeting Details
Include title, date, participants, project, and topic when available.
## TL;DR
3-6 bullets with the most important outcomes.
## Goals and Context
Summarize why the meeting happened, what problem the team was trying to solve, and the business/product reason it matters.
## Business and Product Context
Capture business model, customers/users, value proposition, sales or delivery constraints, priorities, stakeholder concerns, deadlines, budget/cost implications, and product requirements when mentioned.
## Decisions
Use bullets. Label each decision as Decided, Proposed, or Revisited. Include timestamp references when useful.
## Technical Discussion
Group by topic. Capture architecture, APIs, code paths, infrastructure, data, testing, deployment, security, performance, and product constraints when mentioned.
## Requirements and Scope
Separate confirmed requirements from nice-to-have ideas and out-of-scope items.
## Implementation Plan
Describe the intended sequence of work. Include dependencies and sequencing constraints.
## Action Items
Use a markdown table with columns: Action, Owner, Due Date, Deliverable, Dependencies, Status.
## Risks and Blockers
Separate confirmed blockers from potential risks. Include business risks as well as technical risks.
## Open Questions
## Technical References
List mentioned repositories, files, branches, PRs, tickets, services, APIs, environments, tools, libraries, commands, dashboards, or documents. Use 'Not specified' if none are mentioned.
## Follow-up Agenda
Suggest the agenda for the next engineering sync based only on unresolved items.
"""

    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    content = response.choices[0].message.content
    return content or "# Meeting Summary\n\nNo summary was returned by the model."


def _summary_metadata(
    doc: dict,
    summary_focus: str | None = None,
    summary_language: str = "English",
) -> str:
    meta = doc.get("metadata", {})
    focus = summary_focus or meta.get("summary_focus") or "Software development, technical decisions, product/business context, implementation work, risks, blockers, and action items."
    participants = meta.get("participants", [])
    participant_lines = []
    for participant in participants:
        name = participant.get("name", "")
        role = participant.get("role", "")
        if name and role:
            participant_lines.append(f"- {name} ({role})")
        elif name:
            participant_lines.append(f"- {name}")

    return "\n".join([
        f"Title: {meta.get('title') or Path(doc.get('audio_file', 'meeting')).stem}",
        f"Date: {meta.get('date') or date.today().isoformat()}",
        f"Language: {doc.get('language', meta.get('language', 'en'))}",
        f"Summary language: {summary_language}",
        f"Project: {meta.get('project') or 'Not specified'}",
        f"Topic: {meta.get('topic') or 'Not specified'}",
        f"Summary focus: {_format_focus(focus)}",
        "Participants:",
        *(participant_lines or ["- Not specified"]),
    ])


def _summary_languages(doc: dict, override=None) -> list[str]:
    raw = override if override else doc.get("metadata", {}).get("summary_language") or "en"
    if isinstance(raw, list):
        values = raw
    else:
        values = str(raw).split(",")

    languages = []
    for value in values:
        code = _summary_language_code(value)
        if code not in languages:
            languages.append(code)
    return languages or ["en"]


def _summary_language_code(raw) -> str:
    value = str(raw).strip().lower()
    if value in {"de", "deutsch", "german"}:
        return "de"
    if value in {"en", "english"}:
        return "en"
    return value or "en"


def _summary_language_name(raw) -> str:
    code = _summary_language_code(raw)
    if code == "de":
        return "German"
    if code == "en":
        return "English"
    return str(raw).strip() or "English"


def _summary_output_path(
    transcript_path: Path,
    output_path: str | Path | None,
    language_code: str,
    multiple_languages: bool,
) -> Path:
    if output_path is not None:
        path = Path(output_path)
        if multiple_languages:
            return path.with_name(f"{path.stem}_{language_code}{path.suffix or '.md'}")
        return path

    suffix = f"_summary_{language_code}.md" if multiple_languages else "_summary.md"
    return transcript_path.with_name(transcript_path.stem + suffix)


def _format_focus(value) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if str(item).strip()) or "Not specified"
    return str(value).strip() or "Not specified"


def _format_ts(seconds: float) -> str:
    seconds = float(seconds or 0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
