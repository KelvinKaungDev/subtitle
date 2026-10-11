"""Step 5a: the .srt and the soft-subtitle mp4 (streams copied, not re-encoded)."""
import subprocess
from pathlib import Path


def _ts(sec: float) -> str:
    ms = round(sec * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def write_srt(segments: list[dict], path: Path, key: str = "my") -> int:
    """Write UTF-8 SRT. Segments with empty Burmese are skipped. Returns how many were written."""
    blocks, n = [], 0
    for s in segments:
        text = (s.get(key) or "").strip()
        if not text:
            continue
        n += 1
        blocks.append(f"{n}\n{_ts(s['start'])} --> {_ts(s['end'])}\n{text}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")
    return n


def make_soft_mp4(video: Path, srt: Path, out: Path, tag: str = "mya", title: str = "Burmese") -> None:
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(srt),
           "-map", "0", "-map", "1", "-c", "copy", "-c:s", "mov_text",
           f"-metadata:s:s:0", f"language={tag}", "-metadata:s:s:0", f"title={title}",
           str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"FFmpeg failed: {r.stderr.strip()[-500:]}")
