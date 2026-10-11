"""Burmese line breaking. Burmese has no spaces between words, so we may only break
at SYLLABLE boundaries (never in the middle of a syllable) or at real spaces."""
import re

# A new syllable starts at a consonant (U+1000-1021), an independent vowel (U+1023-1027, U+1029-102A),
# or U+103F (great sa) -- UNLESS that consonant is:
#   * stacked under a virama   (previous char is U+1039)
#   * a final consonant        (next char is asat U+103A, or virama U+1039 starts a stack)
_START = "က-အဣ-ဧဩဪဿ"
_BREAK = re.compile(rf"(?<!္)(?=[{_START}](?![်္]))")
# Kinzi: NGA + asat + virama + consonant ("င်္") keeps the consonant with it (lookbehind above)
# Also digits and Latin text are kept together as one unit.
_NON_BURMESE_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’.,:%/\-]*")


def syllables(word: str) -> list[str]:
    """Split a space-free string into syllable units. Latin words/numbers stay whole."""
    out: list[str] = []
    pos = 0
    for m in _NON_BURMESE_RUN.finditer(word):
        out += _split_burmese(word[pos:m.start()])
        out.append(m.group(0))
        pos = m.end()
    out += _split_burmese(word[pos:])
    return [u for u in out if u]


def _split_burmese(text: str) -> list[str]:
    if not text:
        return []
    parts = _BREAK.split(text)
    # never start a unit with punctuation/combining marks: glue leftovers to the previous unit
    units: list[str] = []
    for p in parts:
        if not p:
            continue
        if units and not re.match(rf"[{_START}]", p[0]):
            units[-1] += p
        else:
            units.append(p)
    return units


def to_units(text: str) -> list[tuple[str, bool]]:
    """Return [(unit_text, space_before)] for the whole subtitle. Newlines count as spaces."""
    units: list[tuple[str, bool]] = []
    for i, word in enumerate(text.split()):
        for j, syl in enumerate(syllables(word)):
            units.append((syl, i > 0 and j == 0))
    return units
