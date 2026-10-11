"""A job = one video, stored in jobs/<job_id>/. Status and segments are plain JSON files."""
import json
import re
import time
import uuid
from pathlib import Path

from .config import JOBS_DIR

STATES = ["downloading", "transcribing", "translating", "waiting_review",
          "rendering", "done", "error"]


# Each job makes ONE kind of subtitles: "my" = Burmese (translated), "en" = English (as heard).
LANGS = {
    "my": {"key": "my", "srt": "burmese.srt", "tag": "mya", "title": "Burmese"},
    "en": {"key": "en", "srt": "english.srt", "tag": "eng", "title": "English"},
}


def get_lang(job_id: str) -> dict:
    return LANGS[get_status(job_id).get("subtitle_lang", "my")]


def new_job(url: str, lang: str = "my") -> str:
    if lang not in LANGS:
        raise ValueError("lang must be 'my' or 'en'")
    job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    job_dir(job_id).mkdir(parents=True)
    set_status(job_id, "downloading", progress=0, message="Starting", url=url, subtitle_lang=lang)
    return job_id


def job_dir(job_id: str) -> Path:
    if not re.fullmatch(r"[\w-]+", job_id):
        raise ValueError("bad job id")
    return JOBS_DIR / job_id


def get_status(job_id: str) -> dict:
    return json.loads((job_dir(job_id) / "status.json").read_text())


def set_status(job_id: str, state: str, progress: float | None = None,
               message: str = "", **extra) -> dict:
    path = job_dir(job_id) / "status.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    old.update(state=state, message=message, updated=time.time(), **extra)
    if progress is not None:
        old["progress"] = progress
    path.write_text(json.dumps(old, indent=2, ensure_ascii=False))
    return old


def list_jobs() -> list[dict]:
    out = []
    for d in sorted(JOBS_DIR.glob("*/status.json"), reverse=True):
        out.append({"id": d.parent.name, **json.loads(d.read_text())})
    return out


def load_segments(job_id: str) -> list[dict]:
    return json.loads((job_dir(job_id) / "segments.json").read_text())


def save_segments(job_id: str, segments: list[dict]) -> None:
    (job_dir(job_id) / "segments.json").write_text(
        json.dumps(segments, indent=2, ensure_ascii=False))
