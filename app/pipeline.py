"""Pipeline steps. Each step reads/writes files in the job folder, so a step can be run alone
(CLI) or in the background (web), and later steps (e.g. a voiceover step) can be added."""
import traceback

from . import export, jobs, render, segments as seg, translate
from .download import download
from .transcribe import transcribe


def step_get_english(job_id: str) -> None:
    """Download the video, then get English segments from captions or Whisper."""
    d = jobs.job_dir(job_id)
    url = jobs.get_status(job_id)["url"]
    try:
        jobs.set_status(job_id, "downloading", 0, "Downloading video")
        info = download(url, d, lambda f: jobs.set_status(
            job_id, "downloading", round(f * 100), "Downloading video"))
        jobs.set_status(job_id, "transcribing", 0, "Getting English text",
                        title=info["title"], duration=info["duration"])
        if info["caption_file"]:
            segments = seg.from_captions(d / info["caption_file"])
            source = f"youtube-{info['caption_kind']}"
        else:
            why = ("YouTube blocked the captions download (too many requests)"
                   if info.get("caption_error") else "No captions found")
            jobs.set_status(job_id, "transcribing", 10,
                            f"{why} - transcribing with Whisper (may take a while)")
            segments = seg.from_whisper(transcribe(d / "original.mp4", d))
            source = "whisper"
        jobs.save_segments(job_id, segments)
        if jobs.get_lang(job_id)["key"] == "en":     # English subtitles: nothing to translate
            jobs.set_status(job_id, "waiting_review", 100,
                            f"{len(segments)} English subtitles ready - please review",
                            english_source=source)
        else:
            jobs.set_status(job_id, "translating", 100,
                            f"{len(segments)} segments ready ({source})", english_source=source)
    except Exception as e:
        jobs.set_status(job_id, "error", message=f"{type(e).__name__}: {e}",
                        traceback=traceback.format_exc())
        raise


def step_translate(job_id: str, mode: str = "openai", answer_text: str = "") -> list[str]:
    """mode 'openai' = ask GPT; mode 'manual' = use JSON pasted from Claude (answer_text).
    Returns warnings. On success the job moves to waiting_review."""
    try:
        segments = jobs.load_segments(job_id)
        title = jobs.get_status(job_id).get("title", "")
        if mode == "openai":
            jobs.set_status(job_id, "translating", 20, "Asking OpenAI to translate")
            answer = translate.translate_openai(segments, title)
        else:
            answer = translate.parse_json_answer(answer_text)
        warnings = translate.apply_translations(segments, answer)
        jobs.save_segments(job_id, segments)
        jobs.set_status(job_id, "waiting_review", 100, "Translated - please review",
                        warnings=warnings)
        return warnings
    except Exception as e:
        jobs.set_status(job_id, "error" if mode == "openai" else "translating",
                        message=f"Translation failed: {e}", traceback=traceback.format_exc())
        raise


def step_export_soft(job_id: str) -> int:
    """Write burmese.srt and final_soft.mp4 from the current segments."""
    d = jobs.job_dir(job_id)
    try:
        jobs.set_status(job_id, "rendering", 50, "Writing subtitles")
        lang = jobs.get_lang(job_id)
        n = export.write_srt(jobs.load_segments(job_id), d / lang["srt"], lang["key"])
        if n == 0:
            raise RuntimeError(f"There is no {lang['title']} text to export yet")
        export.make_soft_mp4(d / "original.mp4", d / lang["srt"], d / "final_soft.mp4",
                             lang["tag"], lang["title"])
        jobs.set_status(job_id, "done", 100, f"Exported {n} subtitles")
        return n
    except Exception as e:
        jobs.set_status(job_id, "error", message=f"Export failed: {e}",
                        traceback=traceback.format_exc())
        raise


def step_render_burned(job_id: str) -> int:
    """Draw the subtitles onto the video -> final_burned.mp4 (also refreshes the .srt)."""
    d = jobs.job_dir(job_id)
    try:
        jobs.set_status(job_id, "rendering", 0, "Rendering burned-in subtitles")
        segments = jobs.load_segments(job_id)
        lang = jobs.get_lang(job_id)
        export.write_srt(segments, d / lang["srt"], lang["key"])
        n = render.burn(d / "original.mp4", segments, d, d / "final_burned.mp4",
                        lambda f: jobs.set_status(job_id, "rendering", round(f * 100),
                                                  "Rendering burned-in subtitles"),
                        key=lang["key"])
        jobs.set_status(job_id, "done", 100, f"Burned in {n} subtitles")
        return n
    except Exception as e:
        jobs.set_status(job_id, "error", message=f"Render failed: {e}",
                        traceback=traceback.format_exc())
        raise
