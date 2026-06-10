# meeting-scribe

A local-first meeting transcriber that turns audio or video recordings into speaker-diarized transcripts and technical meeting notes.

![meeting-scribe demo](assets/demo.gif)

## What It Produces

For each meeting, the tool writes:

| File | Description |
|---|---|
| `{meeting}.txt` | Plain transcript |
| `{meeting}_timestamped.txt` | Timestamped transcript |
| `{meeting}.json` | Structured transcript with speaker turns |
| `{meeting}_summary.md` | Technical meeting notes |

Summaries are structured for software-development meetings: TL;DR, goals and context, business and product context, decisions, technical discussion, requirements and scope, implementation plan, action items, risks and blockers, open questions, technical references, and follow-up agenda.

## Why This Tool Is Different

Most transcribers give you a flat transcript and a generic summary. This one is local-first (runs on your own machine, keys stay in your `.env`) and makes three deliberate choices:

1. **You steer the summary, per meeting.** Each meeting in `config/meetings.yaml` carries a `summary_focus` list — exactly what must not be missed (decisions, risks, named customers, owners, technical debt). The summarizer is told to prioritize those points, so an onboarding call and a go-live call produce differently-shaped notes. You can also override the focus at summarize time.

2. **Real speaker identification, not just "Speaker 1".** A two-stage pipeline: pyannote diarizes (separates who spoke when), then SpeechBrain matches each speaker to a real person using short reference voice clips in `voice_samples/`. Provide a 20–30s clip per participant and the transcript reads "Alice" / "Bob" instead of `SPEAKER_00`. No samples? Fall back to a manual `speaker_map`. It will not guess names it cannot verify.

3. **Bilingual by design.** `language` (what was spoken) and `summary_language` (what the notes are written in) are separate. A German meeting can produce English notes, or both at once as two files. `language: auto` lets WhisperX detect mixed-language calls.

It also exports branded PDF summaries (`export_summary_pdf.py` + `config/partners.yaml`), processes meetings in batch from a manifest, and can cut voice reference clips straight from a recording with the `sample` command.

## Third-Party Dependencies

| Component | Role | What you need |
|---|---|---|
| **WhisperX** (large-v3) | Transcription + word-level timestamp alignment | nothing (model auto-downloads) |
| **pyannote.audio** | Speaker diarization (who spoke when) | HuggingFace token (`HF_TOKEN`) + accept the gated model terms |
| **SpeechBrain** | Match diarized speakers to named people via voice samples | optional voice clips in `voice_samples/` |
| **OpenAI API** | Generates the structured summary | `OPENAI_API_KEY` |
| **ffmpeg** | Decode/convert audio & video to 16 kHz WAV | system install (`brew install ffmpeg`) |

> **Commercial use note:** the pyannote models are HuggingFace-gated and carry their own usage conditions. Anyone using this commercially must satisfy *those* terms — this project's license cannot grant them.

## Setup

**1. Python environment**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. System dependency** — you also need `ffmpeg`:

```bash
brew install ffmpeg
```

**3. API keys** — copy the template and fill in real values:

```bash
cp .env.example .env
# OPENAI_API_KEY=sk-...   used for summaries
# HF_TOKEN=hf_...         used by pyannote for diarization
```

`HF_TOKEN` also requires accepting the gated pyannote model terms on HuggingFace.

**4. Config** — copy the example configs and edit them:

```bash
cp config/config.example.yaml   config/config.yaml    # local defaults
cp config/meetings.example.yaml config/meetings.yaml  # your meeting manifest
cp config/partners.example.yaml config/partners.yaml  # PDF branding (optional)
```

`.env`, `config/meetings.yaml`, `config/config.yaml`, `config/partners.yaml`, and your recordings are gitignored — only the `*.example` templates are tracked.

## Single Meeting

Put recordings in `meetings/`, then run:

```bash
python meeting.py run meetings/team-sync.m4a \
  --title "Team Sync" \
  --participants "Sam,Alice,Bob" \
  --participant-samples "Sam=voice_samples/sam.m4a,Alice=voice_samples/alice.m4a,Bob=voice_samples/bob.m4a" \
  --speakers 3
```

Transcript-only:

```bash
python meeting.py transcribe meetings/team-sync.m4a \
  --title "Team Sync" \
  --participants "Sam,Alice,Bob" \
  --speakers 3
```

Summarize an existing transcript:

```bash
python meeting.py summarize output/meetings/team-sync.json
```

## Batch Meetings

Edit `config/meetings.yaml`, then run:

```bash
python meeting.py batch --manifest config/meetings.yaml
```

## Summary Focus

The summary is generated from the transcript JSON and the meeting metadata. The prompt is now balanced for technical and business context, but you can tell it what must not be missed.

`language` and `summary_language` are intentionally separate:

```yaml
language: de          # original meeting/transcription language: en, de, or auto
summary_language: en  # generated notes language(s): en, de, or a list
```

To generate both English and German notes from the same original transcript:

```yaml
summary_language:
  - en
  - de
```

That writes separate files, for example:

```text
INTERVIEW_001_team-sync_summary_en.md
INTERVIEW_001_team-sync_summary_de.md
```

For a mixed English/German recording, use:

```yaml
language: auto
```

WhisperX will detect the transcription language instead of forcing German or English. For meetings that are clearly one language, prefer the explicit code (`de` or `en`) because alignment is usually more stable.

In `config/meetings.yaml`:

```yaml
summary_focus:
  - Business context and important strategic points
  - Product requirements and customer/user impact
  - Technical decisions, architecture, risks, and implementation tasks
  - Action items with owners and follow-up questions
```

Or override it when regenerating a summary:

```bash
python meeting.py summarize output/meetings/TEAM_SYNC_001_team-sync.json \
  --summary-language en,de \
  --summary-focus "Focus on business model, customer value, pricing, delivery risks, technical decisions, and next actions"
```

## Speaker Names

Pyannote separates speakers, and SpeechBrain can identify them when you provide short reference clips for participants. You can provide samples for everyone, or just for the person you care most about identifying.

The easiest workflow is:

1. Generate a timestamped transcript once.
2. Find a clean 20-30 second section where one person speaks alone.
3. Extract that section with `meeting.py sample`.

```bash
python meeting.py sample meetings/team-sync.m4a \
  --name Sam \
  --start 00:12:30 \
  --duration 30
```

This writes `voice_samples/sam.wav`.

Then add the sample to `config/meetings.yaml`:

```yaml
participants:
  - name: Sam
    role: host
    voice_sample: voice_samples/sam.wav
  - name: Alice
    role: participant
    voice_sample: voice_samples/alice.wav
```

You can also pass samples for one-off runs:

```bash
python meeting.py run meetings/team-sync.m4a \
  --participants "Sam,Alice" \
  --participant-samples "Sam=voice_samples/sam.wav,Alice=voice_samples/alice.wav"
```

If only Sam has a reference sample, the tool will label the matching diarized speaker as `Sam` and keep the rest generic, such as `Speaker 1`. It will not guess names for people without reference samples.

If you do not have voice samples, inspect the generated transcript once and fill `speaker_map` in `config/meetings.yaml`:

```yaml
speaker_map:
  SPEAKER_00: Sam
  SPEAKER_01: Alice
  SPEAKER_02: Bob
```

Then rerun the meeting.

## Project Layout

```text
meeting-scribe/
├── meeting.py                  # Main CLI
├── transcribe.py               # Lower-level transcription pipeline
├── config/
│   ├── config.yaml             # Local defaults
│   └── meetings.yaml           # Meeting manifest
├── meetings/                   # Put recordings here
├── voice_samples/              # Participant voice reference clips
├── output/meetings/            # Generated transcripts and summaries
├── personal_transcriber/       # Summary generation
└── pipeline/                   # Audio, WhisperX, diarization, output helpers
```

## License

Licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for third-party attributions.

The bundled Apache-2.0 grant covers this project's own code only. Third-party
models — notably the gated pyannote diarization models on Hugging Face — carry
their own terms that you must satisfy independently, especially for commercial
use.
