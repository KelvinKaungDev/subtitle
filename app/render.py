"""Step 5b: burned-in subtitles.

1. Each subtitle -> transparent PNG (Pillow + Noto Sans Myanmar, white text, black outline).
2. FFmpeg overlays the PNGs at the right times (overlay + enable='between(t,start,end)').
   Many subtitles are handled in chunks of the video so one FFmpeg command never gets huge.
   Video chunks are joined without re-encoding, and the ORIGINAL audio is copied unchanged.
"""
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .burmese_text import to_units
from .config import FONTS_DIR, load_settings

FONT_FILE = FONTS_DIR / "NotoSansMyanmar.ttf"     # Burmese
LATIN_FONT_FILE = FONTS_DIR / "NotoSans.ttf"        # English
CHUNK = 40                    # subtitles per FFmpeg run
MAX_TEXT_WIDTH = 0.88         # fraction of video width


# ---------------------------------------------------------------- probing
def probe(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate,duration,bit_rate:format=duration",
         "-of", "json", str(video)], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    st = j["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return {"w": st["width"], "h": st["height"], "fps": float(num) / float(den),
            "duration": float(st.get("duration") or j["format"]["duration"]),
            "bitrate": int(st["bit_rate"]) if st.get("bit_rate", "").isdigit() else 0}


def font_size_for(w: int, h: int) -> int:
    """Relative to video height, but capped by width so vertical videos (Shorts) don't overflow."""
    return max(18, round(min(h * 0.045, w * 0.052)))


# ---------------------------------------------------------------- PNG rendering
def _font(size: int, latin: bool = False) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(LATIN_FONT_FILE if latin else FONT_FILE), size,
                           layout_engine=ImageFont.Layout.RAQM)
    f.set_variation_by_axes([600, 100])        # [weight, width]: SemiBold, normal width
    return f


def wrap_words(text: str, font: ImageFont.FreeTypeFont, max_w: float) -> list[str]:
    """English: break at spaces into the fewest lines (up to 3) that fit, as evenly as possible."""
    words = text.split()
    if not words:
        return []
    join = lambda a, b: " ".join(words[a:b])
    n = len(words)
    if font.getlength(join(0, n)) <= max_w:
        return [join(0, n)]
    best = None
    for k in range(1, n):                                   # two lines
        l = [join(0, k), join(k, n)]
        score = max(font.getlength(x) for x in l)
        if best is None or score < best[0]:
            best = (score, l)
    if best and best[0] <= max_w:
        return best[1]
    best3 = None
    for i in range(1, n - 1):                               # three lines
        for j in range(i + 1, n):
            l = [join(0, i), join(i, j), join(j, n)]
            score = max(font.getlength(x) for x in l)
            if best3 is None or score < best3[0]:
                best3 = (score, l)
    return best3[1] if best3 else best[1]


def wrap(text: str, font: ImageFont.FreeTypeFont, max_w: float, max_lines: int = 2) -> list[str]:
    """Break into at most max_lines lines. Prefer real spaces; otherwise syllable boundaries."""
    units = to_units(text)
    if not units:
        return []

    def join(a, b):
        return "".join((" " if sp and i > a else "") + u for i, (u, sp) in enumerate(units[a:b], a))

    def width(s):
        return font.getlength(s)

    full = join(0, len(units))
    if width(full) <= max_w or max_lines == 1:
        return [full]
    # try all single split points; score = widest line (+ penalty for breaking inside a word)
    best = None
    for k in range(1, len(units)):
        l1, l2 = join(0, k), join(k, len(units))
        score = max(width(l1), width(l2))
        if not units[k][1]:
            score *= 1.12                     # splitting between syllables of one word: allowed, less nice
        if best is None or score < best[0]:
            best = (score, [l1, l2])
    lines = best[1]
    if max(width(l) for l in lines) <= max_w or max_lines <= 2:
        return lines
    return lines


def render_png(text: str, w: int, h: int, out: Path, latin: bool = False) -> tuple[int, int]:
    """Draw one subtitle. Returns the PNG size (width, height)."""
    size = font_size_for(w, h)
    max_w = w * MAX_TEXT_WIDTH
    for _ in range(8):                         # shrink the font a bit if 2 lines are still too wide
        font = _font(size, latin)
        lines = wrap_words(text, font, max_w) if latin else wrap(text, font, max_w)
        if max(font.getlength(l) for l in lines) <= max_w or size <= 18:
            break
        size = int(size * 0.92)
    ascent, descent = font.getmetrics()
    line_h = int(size * (1.25 if latin else 1.55))   # Burmese needs more room for stacked letters
    stroke = max(2, round(size / 14))
    pad = stroke + 4
    img_w = int(max(font.getlength(l) for l in lines)) + 2 * pad
    img_h = line_h * (len(lines) - 1) + ascent + descent + 2 * pad
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if load_settings().get("burn_background") == "box":
        d.rounded_rectangle((0, 0, img_w - 1, img_h - 1), radius=size // 3, fill=(0, 0, 0, 235))
    for i, line in enumerate(lines):
        x = (img_w - font.getlength(line)) / 2
        d.text((x, pad + i * line_h + ascent), line, font=font, anchor="ls",
               fill=(255, 255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    img.save(out)
    return img_w, img_h


# ---------------------------------------------------------------- FFmpeg
def _encoders() -> str:
    return subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True,
                          text=True).stdout


def video_encoder_args(info: dict) -> list[str]:
    enc = _encoders()
    if "h264_videotoolbox" in enc:
        bps = int(info["bitrate"] * 1.3) if info["bitrate"] else int(info["w"] * info["h"] * info["fps"] * 0.08)
        bps = max(3_000_000, min(bps, 25_000_000))
        return ["-c:v", "h264_videotoolbox", "-b:v", str(bps), "-allow_sw", "1"]
    return ["-c:v", "libx264", "-crf", "18", "-preset", "medium"]


def _run_ffmpeg(cmd: list[str], duration: float, on_progress=None) -> None:
    p = subprocess.Popen(cmd + ["-progress", "pipe:1", "-nostats"], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    for line in p.stdout:
        if on_progress and line.startswith("out_time_us="):
            try:
                on_progress(min(1.0, int(line.split("=")[1]) / 1e6 / max(duration, 0.1)))
            except ValueError:
                pass
    err = p.stderr.read()
    if p.wait():
        raise RuntimeError(f"FFmpeg failed: {err.strip()[-600:]}")


def _chunks(items: list[dict], info: dict) -> list[tuple[float, float, list[dict]]]:
    """Group subtitles in chunks of CHUNK. Chunk boundaries sit at a subtitle start (rounded to a
    frame), so no subtitle is cut in half. Returns [(t0, t1, [items])]."""
    fps = info["fps"]
    snap = lambda t: round(t * fps) / fps
    groups = [items[i:i + CHUNK] for i in range(0, len(items), CHUNK)]
    bounds = [0.0] + [snap(g[0]["start"]) for g in groups[1:]] + [info["duration"]]
    return [(bounds[i], bounds[i + 1], g) for i, g in enumerate(groups)]


def burn(video: Path, segments: list[dict], work_dir: Path, out: Path, on_progress=None,
         key: str = "my") -> int:
    """Create `out` (mp4) with subtitles drawn on (key "my" = Burmese, "en" = English). Returns the number of subtitles."""
    font_file = LATIN_FONT_FILE if key == "en" else FONT_FILE
    if not font_file.exists():
        raise RuntimeError(f"Font missing: {font_file}")
    info = probe(video)
    w, h = info["w"], info["h"]
    subs_dir = work_dir / "subs"
    subs_dir.mkdir(exist_ok=True)
    for old in subs_dir.glob("*.png"):
        old.unlink()

    # make sure subtitles never overlap and stay inside the video
    items = []
    segs = [s for s in segments if (s.get(key) or "").strip()]
    for i, s in enumerate(segs):
        end = min(s["end"], segs[i + 1]["start"] if i + 1 < len(segs) else info["duration"])
        if end - s["start"] < 0.05:
            continue
        png = subs_dir / f"{s['id']:04d}.png"
        pw, ph = render_png(s[key].strip(), w, h, png, latin=(key == "en"))
        items.append({"start": s["start"], "end": end, "png": png, "pw": pw, "ph": ph})
    if not items:
        raise RuntimeError("There is no subtitle text to burn in yet")

    chunks = _chunks(items, info)
    part_files = []
    enc = video_encoder_args(info)
    for ci, (t0, t1, group) in enumerate(chunks):
        part = work_dir / f"part_{ci:03d}.mp4"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t0:.4f}", "-t", f"{t1 - t0:.4f}",
               "-i", str(video)]
        for it in group:
            cmd += ["-i", str(it["png"])]
        chain, last = [], "[0:v]"
        for k, it in enumerate(group, 1):
            x = f"(W-w)/2"
            y = round(h - it["ph"] - h * load_settings()["burn_bottom_margin"])
            a, b = max(0, it["start"] - t0), it["end"] - t0
            label = f"[v{k}]"
            chain.append(f"{last}[{k}:v]overlay=x={x}:y={y}:enable='between(t,{a:.3f},{b:.3f})'{label}")
            last = label
        cmd += ["-filter_complex", ";".join(chain), "-map", last, "-an", "-pix_fmt", "yuv420p",
                *enc, str(part)]
        base = ci / len(chunks)
        _run_ffmpeg(cmd, t1 - t0, lambda f, base=base: on_progress and
                    on_progress((base + f / len(chunks)) * 0.95))
        part_files.append(part)

    # join the chunks (no re-encode), then add the ORIGINAL audio (copied, not re-encoded)
    listing = work_dir / "parts.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in part_files))
    joined = work_dir / "video_only.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(listing), "-c", "copy", str(joined)], check=True, cwd=work_dir)
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-i", str(video),
                        "-map", "0:v", "-map", "1:a?", "-c", "copy", "-movflags", "+faststart",
                        str(out)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"FFmpeg failed while adding audio: {r.stderr.strip()[-500:]}")
    for f in [*part_files, listing, joined]:
        f.unlink(missing_ok=True)
    if on_progress:
        on_progress(1.0)
    return len(items)


def preview_frame(video: Path, segment: dict, key: str, out: Path) -> None:
    """One JPEG: a real frame from the video with this subtitle drawn exactly as the render would."""
    info = probe(video)
    w, h = info["w"], info["h"]
    t = min(max((segment["start"] + segment["end"]) / 2, 0), max(info["duration"] - 0.1, 0))
    frame, sub = out.with_name("preview_frame.png"), out.with_name("preview_sub.png")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video),
                        "-frames:v", "1", str(frame)], capture_output=True, text=True)
    if r.returncode or not frame.exists():
        raise RuntimeError(f"Could not read a frame: {r.stderr.strip()[-300:]}")
    text = (segment.get(key) or "").strip() or "(empty subtitle)"
    pw, ph = render_png(text, w, h, sub, latin=(key == "en"))
    img = Image.open(frame).convert("RGBA")
    cfg = load_settings()
    img.alpha_composite(Image.open(sub), ((w - pw) // 2, round(h - ph - h * cfg["burn_bottom_margin"])))
    img = img.convert("RGB")
    img.thumbnail((900, 1100))
    img.save(out, quality=88)
    frame.unlink(missing_ok=True)
    sub.unlink(missing_ok=True)
