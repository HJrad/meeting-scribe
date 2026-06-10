# vhs tape for the meeting-scribe demo GIF.
# Render from repo root: vhs assets/demo/demo.tape  (writes assets/demo.gif)

Output assets/demo.gif

Set Shell zsh
Set FontSize 18
Set Width 1100
Set Height 720
Set Padding 22
Set Theme "Dracula"
Set TypingSpeed 35ms

Hide
Type "source .venv/bin/activate && clear"
Enter
Sleep 800ms
Show

Type "# meeting-scribe: recordings -> speaker-labeled transcripts + notes"
Enter
Sleep 1200ms

Type "python meeting.py --help"
Enter
Sleep 2800ms

Type "# 1) transcribe + summarize one meeting, with named speakers:"
Enter
Sleep 700ms
Type 'python meeting.py run meetings/team-sync.m4a --participants "Sam,Alice,Bob" --participant-samples "Sam=voice_samples/sam.wav,Alice=voice_samples/alice.wav" --speakers 3'
Sleep 1800ms
Ctrl+C
Sleep 400ms

Type "# pipeline: ffmpeg -> WhisperX -> pyannote diarize -> SpeechBrain -> summary"
Enter
Sleep 1600ms

Type "# 2) the generated, focus-steered notes:"
Enter
Sleep 700ms
Type "cat assets/demo/sample_summary.md"
Enter
Sleep 4200ms
