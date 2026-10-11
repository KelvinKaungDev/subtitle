"""Step 3: English segments -> Burmese lines.

Two ways to get the same result:
  * OpenAI (automatic)            -> translate_openai()
  * "manual Claude mode": build_manual_prompt() shows a prompt you paste into claude.ai,
    then apply_answer() takes the JSON you paste back.
Both end up calling apply_translations(), which validates and stores the Burmese.
"""
import json
import os
import re

from .config import load_settings

RULES = """You are a professional subtitle translator from English to Burmese (Myanmar language).

Rules:
- Natural, casual, spoken Burmese, the way people really talk in a movie. Not stiff or bookish.
- Use standard Unicode Burmese only. NEVER use Zawgyi.
- Write ALL character names, titles and place names in Burmese script (e.g. Mr. Wick -> မစ္စတာ ဝစ်ခ်, John -> ဂျွန်). Never leave English letters in a subtitle. Spell each name the same way every time.
- Make the lines sound like real dialogue between the characters (who is speaking to whom, their tone), not a literal word-by-word translation.
- Subtitles must be short and easy to read: at most 2 short lines (about 40 characters per line). Shorten if needed, keep the meaning.
- The segments are consecutive lines from one video, so use the context of the whole story. A sentence may be cut across two segments; translate each segment so the pair reads naturally.
- Fix obvious speech-recognition mistakes using context.
- Translate every segment. Do not merge, skip or reorder them.
- Use "\\n" inside a string only if you really need a line break.
"""

ANSWER_FORMAT = ('Reply with ONLY a JSON object (no explanation, no markdown fences) that maps each '
                 'segment id (as a string) to its Burmese subtitle, like:\n'
                 '{"1": "မင်္ဂလာပါ", "2": "..."}')


def _segment_lines(segments: list[dict]) -> str:
    return "\n".join(f'{s["id"]}: {s["en"]}' for s in segments)


def build_manual_prompt(segments: list[dict], title: str = "") -> str:
    head = f'Video title: "{title}"\n\n' if title else ""
    return (f"{RULES}\n{ANSWER_FORMAT}\n\n{head}Segments (id: English):\n"
            f"{_segment_lines(segments)}")


def parse_json_answer(text: str) -> dict[str, str]:
    """Accept raw JSON, or JSON wrapped in ``` fences / extra chatter."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError("Could not find a JSON object in the answer. "
                             "Make sure you copied the whole reply.")
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise ValueError(f"The JSON is not valid ({e}). Ask Claude to reply with valid JSON only.")
    if isinstance(data, list):                   # [{"id":1,"my":"..."}] style
        data = {str(d.get("id")): d.get("my") or d.get("text") or d.get("burmese", "") for d in data}
    if not isinstance(data, dict):
        raise ValueError("The answer must be a JSON object mapping ids to Burmese lines.")
    return {str(k): str(v).strip() for k, v in data.items()}


def apply_translations(segments: list[dict], answer: dict[str, str]) -> list[str]:
    """Store Burmese into segments. Returns a list of warnings (missing ids, etc.)."""
    warnings = []
    missing = [s["id"] for s in segments if not answer.get(str(s["id"]))]
    if missing:
        warnings.append(f"No translation for segment(s): {missing}")
    extra = sorted(set(answer) - {str(s["id"]) for s in segments}, key=str)
    if extra:
        warnings.append(f"Ignored unknown ids: {extra}")
    for s in segments:
        s["my"] = answer.get(str(s["id"]), s.get("my", ""))
        if re.search(r"[က-႟]", s["my"]) is None and s["my"]:
            warnings.append(f"Segment {s['id']} has no Burmese letters")
    return warnings


def translate_openai(segments: list[dict], title: str = "") -> dict[str, str]:
    from openai import OpenAI
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is missing. Put it in ~/myanmar-dub/.env")
    model = load_settings()["openai_model"]
    head = f'Video title: "{title}"\n\n' if title else ""
    user = (f"{ANSWER_FORMAT}\n\n{head}Segments (id: English):\n{_segment_lines(segments)}")
    r = OpenAI().chat.completions.create(
        model=model, temperature=0.3,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": RULES},
                  {"role": "user", "content": user}])
    return parse_json_answer(r.choices[0].message.content)
