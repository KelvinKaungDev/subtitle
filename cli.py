"""Run pipeline steps from the terminal.   .venv/bin/python cli.py --help"""
import argparse
import json

from app import jobs, pipeline


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("english", help="download a video and get English segments")
    s.add_argument("url")
    s.add_argument("--lang", choices=["my", "en"], default="my", help="my=Burmese, en=English subtitles")
    s = sub.add_parser("show", help="print segments of a job")
    s.add_argument("job_id")
    sub.add_parser("list", help="list jobs")
    s = sub.add_parser("translate", help="translate with OpenAI (or --file answer.json from Claude)")
    s.add_argument("job_id")
    s.add_argument("--file", help="JSON answer pasted from Claude (manual mode)")
    s = sub.add_parser("prompt", help="print the prompt to paste into Claude")
    s.add_argument("job_id")
    s = sub.add_parser("burn", help="render final_burned.mp4 (subtitles drawn on the video)")
    s.add_argument("job_id")
    s = sub.add_parser("export", help="write burmese.srt + final_soft.mp4")
    s.add_argument("job_id")
    a = p.parse_args()

    if a.cmd == "english":
        from app.download import check_youtube_url
        job_id = jobs.new_job(check_youtube_url(a.url), a.lang)
        print("job:", job_id)
        pipeline.step_get_english(job_id)
        print(json.dumps(jobs.get_status(job_id), indent=2))
    elif a.cmd == "show":
        for s in jobs.load_segments(a.job_id):
            print(f"{s['id']:>3} {s['start']:7.2f}-{s['end']:7.2f} ({s['end']-s['start']:.1f}s) {s['en']}")
            if s.get("my"):
                print(f"{'':>25}{s['my']}")
    elif a.cmd == "translate":
        mode, text = ("manual", open(a.file).read()) if a.file else ("openai", "")
        print("warnings:", pipeline.step_translate(a.job_id, mode, text))
    elif a.cmd == "prompt":
        from app import translate
        print(translate.build_manual_prompt(jobs.load_segments(a.job_id),
                                            jobs.get_status(a.job_id).get("title", "")))
    elif a.cmd == "burn":
        print("subtitles burned in:", pipeline.step_render_burned(a.job_id))
    elif a.cmd == "export":
        print("subtitles written:", pipeline.step_export_soft(a.job_id))
    elif a.cmd == "list":
        for j in jobs.list_jobs():
            print(j["id"], j["state"], j.get("title", ""))


if __name__ == "__main__":
    main()
