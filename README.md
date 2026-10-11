# Myanmar Dub

Personal web app: paste a YouTube link of an English video and get the same video with
Burmese (or English) subtitles. The original video and audio are never changed.

- Burmese mode: English text (YouTube captions, or Whisper if none) -> translated with OpenAI GPT
  or by pasting Claude's answer ("manual Claude mode") -> review/edit -> export.
- English mode: the English words as spoken, reviewed and exported (no translation).
- Output: `.srt`, an mp4 with soft subtitles, and an mp4 with the subtitles burned in.

## Setup (macOS, Apple Silicon)
```
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg            # needs h264_videotoolbox; no libass needed
echo 'OPENAI_API_KEY=sk-...' > .env
./run.sh                       # http://localhost:8000
```
Command-line steps for debugging: `python cli.py --help`. Settings live in `settings.json`.
Fonts in `fonts/` are Noto Sans and Noto Sans Myanmar (SIL Open Font License).
