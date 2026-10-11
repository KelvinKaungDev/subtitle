"""Turn raw captions / Whisper output into clean sentence-level segments.

A segment is {"id": int, "start": sec, "end": sec, "en": str, "my": str}.
"""
import json
import re
from pathlib import Path

from .config import load_settings

SENTENCE_END = re.compile(r"(?<!\.\.)[.!?][\"')\]]*$")
ABBREVIATION = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|St|Jr|Sr|vs|Prof)\.$")


def _clean(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text)   # [Music], (laughs)
    text = re.sub(r">>+|&gt;&gt;", " ", text)            # speaker-change marks
    text = text.replace("​", "").replace("\n", " ")
    text = re.sub(r"\b(?:uh|um|uhm|erm)\b[,.]?", " ", text, flags=re.I)   # filler words
    return re.sub(r"\s+", " ", text).strip()


def parse_json3(path: Path) -> list[dict]:
    """Read YouTube json3 captions into rough cues [{start,end,text}]."""
    events = json.loads(path.read_text()).get("events", [])
    cues = []
    for ev in events:
        if "segs" not in ev:
            continue
        text = _clean("".join(s.get("utf8", "") for s in ev["segs"]))
        if not text:
            continue
        start = ev["tStartMs"] / 1000
        cues.append({"start": start, "end": start + ev.get("dDurationMs", 0) / 1000,
                     "text": text})
    # Auto-captions repeat text across overlapping cues; drop exact repeats
    # and trim the end of each cue so cues never overlap.
    cues.sort(key=lambda c: c["start"])
    out = []
    for c in cues:
        if out and c["text"] == out[-1]["text"]:
            out[-1]["end"] = max(out[-1]["end"], c["end"])
            continue
        if out and out[-1]["end"] > c["start"]:
            out[-1]["end"] = c["start"]
        out.append(c)
    return out


def _dedupe_rolling(cues: list[dict]) -> list[dict]:
    """If a cue starts with the previous cue's text (rolling captions), keep only the new part."""
    out = []
    prev = ""
    for c in cues:
        text = c["text"]
        if prev and text.startswith(prev):
            text = text[len(prev):].strip()
        prev = c["text"]
        if text:
            out.append({**c, "text": text})
    return out


def merge_sentences(cues: list[dict]) -> list[dict]:
    """Join cues into sentences; also break on long pauses or when too long."""
    cfg = load_settings()
    max_sec, max_chars = cfg["max_segment_seconds"], cfg["max_segment_chars"] * 2
    segs, cur = [], None
    for c in cues:
        if cur and c["start"] - cur["end"] > 1.0:       # long pause = new segment
            segs.append(cur)
            cur = None
        if cur is None:
            cur = dict(c)
        else:
            cur["text"] += " " + c["text"]
            cur["end"] = c["end"]
        too_long = (cur["end"] - cur["start"] > max_sec * 1.5) or len(cur["text"]) > max_chars
        if (SENTENCE_END.search(cur["text"]) and not ABBREVIATION.search(cur["text"])) or too_long:
            segs.append(cur)
            cur = None
    if cur:
        segs.append(cur)
    return segs


def split_long(segs: list[dict]) -> list[dict]:
    """Split segments longer than max_segment_seconds / max_segment_chars at sentence/comma/word
    boundaries, sharing the time in proportion to text length."""
    cfg = load_settings()
    max_sec, max_chars = cfg["max_segment_seconds"], cfg["max_segment_chars"]
    out = []
    for s in segs:
        pieces = [s["text"]]
        while True:
            long = [p for p in pieces if len(p) > max_chars]
            if not long and (s["end"] - s["start"]) / max(len(pieces), 1) <= max_sec:
                break
            idx = max(range(len(pieces)), key=lambda i: len(pieces[i]))
            p = pieces[idx]
            if len(p) < 30:
                break
            cut = _best_cut(p)
            if cut is None:
                break
            pieces[idx:idx + 1] = [p[:cut].strip(), p[cut:].strip()]
        total = sum(len(p) for p in pieces) or 1
        t = s["start"]
        for p in pieces:
            dur = (s["end"] - s["start"]) * len(p) / total
            out.append({"start": t, "end": t + dur, "text": p})
            t += dur
    return out


def _best_cut(text: str) -> int | None:
    """Pick the split point nearest the middle, preferring . ? ! then , ; then spaces."""
    mid = len(text) / 2
    for pattern in (r"[.!?…]\s", r"[,;:—-]\s", r"\s"):
        cands = [m.end() for m in re.finditer(pattern, text) if 10 < m.end() < len(text) - 10]
        if cands:
            return min(cands, key=lambda i: abs(i - mid))
    return None


def finalize(segs: list[dict]) -> list[dict]:
    return [{"id": i, "start": round(s["start"], 2), "end": round(s["end"], 2),
             "en": s["text"], "my": ""} for i, s in enumerate(segs, 1)]


def from_captions(path: Path) -> list[dict]:
    cues = _dedupe_rolling(parse_json3(path))
    return finalize(split_long(merge_sentences(cues)))


def from_whisper(whisper_segments: list[dict]) -> list[dict]:
    cues = [{"start": s["start"], "end": s["end"], "text": _clean(s["text"])}
            for s in whisper_segments if _clean(s["text"])]
    return finalize(split_long(merge_sentences(cues)))
