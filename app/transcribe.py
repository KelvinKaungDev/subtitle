"""Fallback when a video has no captions: transcribe the audio with mlx-whisper."""
import subprocess
from pathlib import Path

from .config import load_settings


def extract_audio(video: Path, wav: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
                    "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)


def transcribe(video: Path, work_dir: Path) -> list[dict]:
    import mlx_whisper  # imported late: it is slow to load
    wav = work_dir / "audio.wav"
    extract_audio(video, wav)
    result = mlx_whisper.transcribe(str(wav), language="en",
                                    path_or_hf_repo=load_settings()["whisper_model"])
    return result["segments"]
