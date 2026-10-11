"""FastAPI web app. Run with ./run.sh  ->  http://localhost:8000"""
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import json

from . import jobs, pipeline, translate
from .config import ROOT, load_settings
from .download import check_youtube_url

app = FastAPI(title="Myanmar Dub")

DOWNLOADS = {   # URL name -> (file in job folder, download name); "srt" depends on the job's language
    "srt": (None, None),
    "soft": ("final_soft.mp4", "video_soft_subs.mp4"),
    "burned": ("final_burned.mp4", "video_burned_subs.mp4"),
    "original": ("original.mp4", "original.mp4"),
}


def _job(job_id: str) -> dict:
    try:
        return {"id": job_id, **jobs.get_status(job_id)}
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Job not found")


class NewJob(BaseModel):
    url: str
    lang: str = "my"              # "my" = Burmese subtitles, "en" = English subtitles


class TranslateReq(BaseModel):
    mode: str = "openai"          # "openai" or "manual"
    answer: str = ""


class SegmentEdit(BaseModel):
    my: str


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.post("/api/jobs")
def create_job(body: NewJob, bg: BackgroundTasks):
    try:
        url = check_youtube_url(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if body.lang not in jobs.LANGS:
        raise HTTPException(400, "lang must be 'my' or 'en'")
    job_id = jobs.new_job(url, body.lang)
    bg.add_task(_safe, pipeline.step_get_english, job_id)
    return {"id": job_id}


def _safe(fn, *args):
    """Background tasks must not crash the server; errors are already saved in status.json."""
    try:
        fn(*args)
    except Exception:
        pass


@app.get("/api/jobs")
def list_jobs():
    return jobs.list_jobs()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = _job(job_id)
    d = jobs.job_dir(job_id)
    lang = jobs.get_lang(job_id)
    job["subtitle_lang"] = lang["key"]
    job["files"] = {k: ((d / (lang["srt"] if k == "srt" else f)).exists())
                    for k, (f, _) in DOWNLOADS.items()}
    return job


@app.get("/api/jobs/{job_id}/segments")
def get_segments(job_id: str):
    _job(job_id)
    try:
        return jobs.load_segments(job_id)
    except FileNotFoundError:
        return []


class AllEdits(BaseModel):
    texts: dict[str, str]          # {"1": "text", "2": "text", ...}


@app.put("/api/jobs/{job_id}/segments")
def edit_all_segments(job_id: str, body: AllEdits):
    _job(job_id)
    key = jobs.get_lang(job_id)["key"]
    segs = jobs.load_segments(job_id)
    for s in segs:
        if str(s["id"]) in body.texts:
            s[key] = body.texts[str(s["id"])]
    jobs.save_segments(job_id, segs)
    return {"ok": True, "saved": len(body.texts)}


@app.put("/api/jobs/{job_id}/segments/{seg_id}")
def edit_segment(job_id: str, seg_id: int, body: SegmentEdit):
    _job(job_id)
    segs = jobs.load_segments(job_id)
    for s in segs:
        if s["id"] == seg_id:
            s[jobs.get_lang(job_id)["key"]] = body.my     # edits go to the job's subtitle language
            jobs.save_segments(job_id, segs)
            return {"ok": True}
    raise HTTPException(404, "Segment not found")


@app.get("/api/jobs/{job_id}/prompt")
def manual_prompt(job_id: str):
    job = _job(job_id)
    return {"prompt": translate.build_manual_prompt(jobs.load_segments(job_id),
                                                    job.get("title", ""))}


@app.post("/api/jobs/{job_id}/translate")
def start_translate(job_id: str, body: TranslateReq, bg: BackgroundTasks):
    _job(job_id)
    if body.mode == "manual":      # quick, and we want errors shown right away
        try:
            warnings = pipeline.step_translate(job_id, "manual", body.answer)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"warnings": warnings}
    bg.add_task(_safe, pipeline.step_translate, job_id, "openai")
    return {"started": True}


@app.post("/api/jobs/{job_id}/export")
def export_job(job_id: str, bg: BackgroundTasks):
    _job(job_id)
    bg.add_task(_safe, pipeline.step_export_soft, job_id)
    return {"started": True}


@app.post("/api/jobs/{job_id}/render")
def render_job(job_id: str, bg: BackgroundTasks):
    _job(job_id)
    bg.add_task(_safe, pipeline.step_render_burned, job_id)
    return {"started": True}


class BurnSettings(BaseModel):
    burn_bottom_margin: float | None = None      # 0.02 - 0.40 of video height
    burn_background: str | None = None           # "none" or "box"


@app.get("/api/settings")
def get_settings():
    s = load_settings()
    return {"burn_bottom_margin": s["burn_bottom_margin"], "burn_background": s["burn_background"]}


@app.put("/api/settings")
def put_settings(body: BurnSettings):
    path = ROOT / "settings.json"
    s = json.loads(path.read_text())
    if body.burn_bottom_margin is not None:
        s["burn_bottom_margin"] = min(0.4, max(0.02, body.burn_bottom_margin))
    if body.burn_background in ("none", "box"):
        s["burn_background"] = body.burn_background
    path.write_text(json.dumps(s, indent=2))
    return get_settings()


@app.get("/api/jobs/{job_id}/video")
def video(job_id: str):
    path = jobs.job_dir(job_id) / "original.mp4"
    if not path.exists():
        raise HTTPException(404, "Video not downloaded yet")
    return FileResponse(path, media_type="video/mp4")   # supports seeking (Range)


@app.get("/api/jobs/{job_id}/download/{kind}")
def download(job_id: str, kind: str):
    if kind not in DOWNLOADS:
        raise HTTPException(404)
    name, pretty = DOWNLOADS[kind]
    if kind == "srt":
        name = pretty = jobs.get_lang(job_id)["srt"]
    path = jobs.job_dir(job_id) / name
    if not path.exists():
        raise HTTPException(404, "File not created yet")
    return FileResponse(path, filename=pretty)
