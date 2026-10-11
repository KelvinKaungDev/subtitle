"""Step 1: download the video (and English captions if YouTube has them)."""
import time
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

from .config import load_settings


def _pick_caption(info: dict, wanted: list[str]) -> tuple[str, str] | None:
    """Return (language_code, 'manual'|'auto'), preferring manual captions."""
    for kind, key in (("manual", "subtitles"), ("auto", "automatic_captions")):
        available = info.get(key) or {}
        for lang in wanted:
            if lang in available:
                return lang, kind
        for lang in available:          # any other English variant, e.g. en-CA
            if lang.startswith("en") and lang != "en-orig":
                return lang, kind
    return None


YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")


def check_youtube_url(url: str) -> str:
    """Return a cleaned YouTube link, or raise ValueError with a message a human can act on."""
    url = url.strip()
    host = (urlparse(url).hostname or "").lower()
    if not url.startswith(("http://", "https://")):
        raise ValueError("Please paste a full link starting with https://")
    if host in ("localhost", "127.0.0.1") or host.endswith(".local"):
        raise ValueError("That is the address of this website, not a video. "
                         "Copy the link from YouTube (the Share button) and paste that here.")
    if not any(host == h or host.endswith("." + h) for h in YOUTUBE_HOSTS):
        raise ValueError("This app only works with YouTube links (youtube.com or youtu.be).")
    return url


def _base_opts() -> dict:
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
            "js_runtimes": {"node": {}}}
    browser = load_settings().get("cookies_from_browser")      # e.g. "chrome" (optional)
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def _download_captions(url: str, job_dir: Path, lang: str, kind: str, tries: int = 3) -> str | None:
    """Fetch captions on their own. YouTube sometimes answers 'HTTP 429 Too Many Requests' for
    captions, so wait and retry. Returns None if it never works (caller then uses Whisper)."""
    opts = {**_base_opts(), "skip_download": True, "outtmpl": str(job_dir / "original.%(ext)s"),
            "writesubtitles": kind == "manual", "writeautomaticsub": kind == "auto",
            "subtitleslangs": [lang], "subtitlesformat": "json3", "sleep_interval_subtitles": 1}
    error = "unknown error"
    for attempt in range(tries):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            if next(job_dir.glob("original.*.json3"), None):
                return None
            error = "no caption file was saved"
        except Exception as e:                       # yt-dlp raises DownloadError for 429 etc.
            error = str(e).replace("ERROR: ", "")
        if attempt < tries - 1:
            time.sleep(5 * (attempt + 1) ** 2)       # 5s, then 20s
    return error


def download(url: str, job_dir: Path, on_progress=None) -> dict:
    """Download to job_dir/original.mp4 and, if possible, YouTube's English captions.
    Returns {title, duration, caption_file, caption_kind, caption_error}.
    A captions failure is NOT fatal: caption_file is None and the caller falls back to Whisper."""
    wanted = load_settings()["caption_languages"]
    with yt_dlp.YoutubeDL(_base_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
    caption = _pick_caption(info, wanted)

    def hook(d):
        if on_progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                on_progress(d["downloaded_bytes"] / total)

    opts = {
        **_base_opts(),
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(job_dir / "original.%(ext)s"),
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    if not (job_dir / "original.mp4").exists():
        raise RuntimeError("Download finished but original.mp4 is missing")

    caption_error = None
    if caption:
        caption_error = _download_captions(url, job_dir, *caption)
    caption_file = next(job_dir.glob("original.*.json3"), None)
    return {
        "title": info.get("title", ""),
        "duration": info.get("duration"),
        "caption_file": caption_file.name if caption_file else None,
        "caption_kind": caption[1] if caption and caption_file else None,
        "caption_error": caption_error,
    }
