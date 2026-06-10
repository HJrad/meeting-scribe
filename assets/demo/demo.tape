# vhs tape for the meeting-scribe demo GIF.
# Render from repo root: vhs assets/demo/demo.tape  (writes assets/demo.gif)
#
# Narration uses `echo` (prints cleanly, no "command not found").
# The `run` command is only printed, never executed (it needs real audio).

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

Type "echo 'meeting-scribe: recordings -> speaker-labeled transcripts + notes'"
Enter
Sleep 1400ms

Type "python meeting.py --help"
Enter
Sleep 3000ms

Type "echo '# transcribe + summarize one meeting, with named speakers:'"
Enter
Sleep 900ms
Type "echo 'python meeting.py run meetings/team-sync.m4a --participants Sam,Alice,Bob --speakers 3'"
Enter
Sleep 2000ms

Type "echo '# pipeline: ffmpeg | WhisperX | pyannote diarize | SpeechBrain | summary'"
Enter
Sleep 1800ms

Type "echo '# the generated, focus-steered notes:'"
Enter
Sleep 900ms
Type "cat assets/demo/sample_summary.md"
Enter
Sleep 4500ms
