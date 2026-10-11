# Myanmar Dub — Burmese subtitle web app

Personal web app (Mac) that takes a YouTube link of an English video (movie recaps etc.) and outputs the SAME video (original video and audio untouched) with Burmese (Myanmar) subtitles.

The user is not an expert: explain things simply. Ask before installing anything new with brew.

## Environment (already set up)
- MacBook Air, Apple Silicon (arm64)
- Project folder: ~/myanmar-dub, Python 3.12 venv at .venv (always use it)
- Installed: fastapi, uvicorn[standard], yt-dlp, mlx-whisper, openai, python-dotenv, pillow
- FFmpeg 9 from Homebrew. IMPORTANT: it has NO libass, so the `subtitles`/`ass` filters do not exist. Do not use them.
- Pillow has raqm support (checked: True), so it can shape Burmese text correctly.
- OpenAI API key goes in .env as OPENAI_API_KEY, never hardcoded.

## Pipeline
1. Download: yt-dlp downloads the video as mp4.
2. English text with timestamps:
   - First try YouTube's English captions via yt-dlp (prefer manual captions, fall back to auto-generated). Clean up auto-caption duplicates/rolling text and merge into sentence-level segments.
   - If no captions exist, extract audio and transcribe with mlx-whisper (large-v3-turbo).
3. Translate: OpenAI GPT model (model name in a settings file) translates all segments in one request for context, returning strict JSON (one Burmese line per segment id). Natural, casual Burmese, Unicode only (never Zawgyi), consistent character names, short enough to read comfortably. Split segments that are too long to read (max ~2 lines, ~6 seconds).
   - Also add a "manual Claude mode": show a copyable prompt with the segments, and a box where the user pastes the JSON answer (they use Claude Pro in the browser).
4. Review: web screen with timestamp, English and editable Burmese for each segment, plus a video preview that jumps to the segment when clicked. Save edits.
5. Output both:
   a) burmese.srt (UTF-8) and an mp4 with soft subtitles (mov_text), original streams copied without re-encoding.
   b) A burned-in mp4: render each subtitle as a transparent PNG with Pillow (Noto Sans Myanmar font downloaded into fonts/, white text, black outline, bottom-center, max 2 lines, size relative to video height). Burmese has no spaces between words, so wrap at spaces or syllable boundaries, never mid-syllable. Overlay with FFmpeg overlay + enable='between(t,start,end)', batching if there are many segments. Copy the original audio unchanged. Use VideoToolbox (h264_videotoolbox) if available.

## App structure
- FastAPI backend, simple single-page HTML/JS frontend served by FastAPI (no React, no build step).
- Each video is a job in jobs/<job_id>/ with original.mp4, segments.json, burmese.srt, subs/, final_soft.mp4, final_burned.mp4, status.json (downloading, transcribing, translating, waiting_review, rendering, done, error).
- Background processing with progress shown on the page. Job list on the home page, download buttons, clear error messages.
- A command-line way to run each step for debugging.
- ./run.sh activates .venv and starts uvicorn at http://localhost:8000

## Phases (stop and show results after each)
1. Download + get English segments for a test link.
2. Translate + review screen, export .srt.
3. Burned-in subtitles render.
4. Polish the web UI.

## Design note
Design the code so a Burmese voiceover mode (edge-tts) can be added later without rewriting it (keep pipeline steps as independent functions operating on segments.json).
