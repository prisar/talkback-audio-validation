from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class FieldType(str, Enum):
    PERCENTAGE = "percentage"
    SIGNED_LEVEL = "signed_level"
    NAME_WITH_STATE = "name_with_state"
    ENUM_STATE = "enum_state"


class ParseStatus(str, Enum):
    OK = "ok"
    NO_VALUE = "no_value"
    AMBIGUOUS = "ambiguous"
    OUT_OF_RANGE = "out_of_range"


@dataclass
class SpokenValue:
    status: ParseStatus
    value: object | None = None
    state: str | None = None
    utterance: str = ""
    candidates: list = field(default_factory=list)
    note: str = ""


UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

PERCENT_WORDS = r"(?:%|percent|per\s?cent)"
NEGATIVE_WORDS = ("minus", "negative")
INAUDIBLE = "[inaudible]"


def normalize(text: str) -> str:
    t = text.lower().strip()
    t = t.replace("–", "-").replace("—", "-")
    t = re.sub(r"[,;!?]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _words_to_int(phrase: str) -> int | None:
    parts = re.split(r"[\s-]+", phrase.strip())
    parts = [p for p in parts if p and p != "and"]
    if not parts:
        return None
    total = 0
    matched = False
    for part in parts:
        if part in TENS:
            total += TENS[part]
            matched = True
        elif part in UNITS:
            total += UNITS[part]
            matched = True
        elif part == "hundred":
            total = (total or 1) * 100
            matched = True
        else:
            return None
    return total if matched else None


def _number_tokens(text: str) -> list[tuple[int, int, int]]:
    """Return (value, start, end) for every digit or word number in text."""
    found: list[tuple[int, int, int]] = []
    for m in re.finditer(r"-?\d+", text):
        found.append((int(m.group()), m.start(), m.end()))
    word_re = (
        r"\b(?:"
        + "|".join(sorted(list(UNITS) + list(TENS) + ["hundred"], key=len, reverse=True))
        + r")(?:[\s-]+(?:"
        + "|".join(sorted(list(UNITS) + ["hundred"], key=len, reverse=True))
        + r"))*\b"
    )
    for m in re.finditer(word_re, text):
        value = _words_to_int(m.group())
        if value is not None:
            overlaps = any(m.start() < e and s < m.end() for _, s, e in found)
            if not overlaps:
                found.append((value, m.start(), m.end()))
    found.sort(key=lambda item: item[1])
    return found


def parse_percentage(transcript: str) -> SpokenValue:
    text = normalize(transcript)
    if not text or INAUDIBLE in text and not re.search(r"\d", text):
        return SpokenValue(ParseStatus.NO_VALUE, utterance=transcript)

    candidates: list[int] = []
    for value, _start, end in _number_tokens(text):
        tail = text[end:end + 12]
        if re.match(r"\s*" + PERCENT_WORDS, tail):
            candidates.append(value)

    if not candidates:
        return SpokenValue(ParseStatus.NO_VALUE, utterance=transcript,
                           note="no number carried percentage semantics")

    distinct = sorted(set(candidates))
    if len(distinct) > 1:
        return SpokenValue(ParseStatus.AMBIGUOUS, utterance=transcript,
                           candidates=distinct,
                           note="multiple distinct percentages announced")

    value = distinct[0]
    if not 0 <= value <= 100:
        return SpokenValue(ParseStatus.OUT_OF_RANGE, value=value, utterance=transcript,
                           candidates=distinct)
    return SpokenValue(ParseStatus.OK, value=value, utterance=transcript,
                       candidates=distinct)


def parse_signed_level(transcript: str, low: int = -6, high: int = 6) -> SpokenValue:
    text = normalize(transcript)
    if not text:
        return SpokenValue(ParseStatus.NO_VALUE, utterance=transcript)

    candidates: list[int] = []
    for value, start, _end in _number_tokens(text):
        prefix = text[max(0, start - 14):start]
        negative = any(w in prefix for w in NEGATIVE_WORDS) or text[start:start + 1] == "-"
        signed = -abs(value) if negative else value
        candidates.append(signed)

    if not candidates:
        return SpokenValue(ParseStatus.NO_VALUE, utterance=transcript)

    distinct = sorted(set(candidates))
    if len(distinct) > 1:
        return SpokenValue(ParseStatus.AMBIGUOUS, utterance=transcript,
                           candidates=distinct,
                           note="multiple distinct levels announced")

    value = distinct[0]
    if not low <= value <= high:
        return SpokenValue(ParseStatus.OUT_OF_RANGE, value=value, utterance=transcript,
                           candidates=distinct)
    return SpokenValue(ParseStatus.OK, value=value, utterance=transcript,
                       candidates=distinct)


def parse_name_with_state(transcript: str, vocabulary: list[str]) -> SpokenValue:
    text = normalize(transcript)
    if not text:
        return SpokenValue(ParseStatus.NO_VALUE, utterance=transcript)

    hits = [name for name in vocabulary if normalize(name) in text]
    if not hits:
        return SpokenValue(ParseStatus.NO_VALUE, utterance=transcript,
                           note="no known program name present")
    if len(hits) > 1:
        longest = max(hits, key=len)
        shorter = [h for h in hits if h != longest and normalize(h) not in normalize(longest)]
        if shorter:
            return SpokenValue(ParseStatus.AMBIGUOUS, utterance=transcript,
                               candidates=sorted(hits))
        hits = [longest]

    state = "selected" if "selected" in text else None
    return SpokenValue(ParseStatus.OK, value=hits[0], state=state, utterance=transcript,
                       candidates=hits)


def parse_enum_state(transcript: str, vocabulary: list[str]) -> SpokenValue:
    text = normalize(transcript)
    if not text:
        return SpokenValue(ParseStatus.NO_VALUE, utterance=transcript)
    hits = [word for word in vocabulary if re.search(rf"\b{re.escape(word)}\b", text)]
    if not hits:
        return SpokenValue(ParseStatus.NO_VALUE, utterance=transcript)
    if len(set(hits)) > 1:
        return SpokenValue(ParseStatus.AMBIGUOUS, utterance=transcript,
                           candidates=sorted(set(hits)))
    return SpokenValue(ParseStatus.OK, value=hits[0], utterance=transcript, candidates=hits)


def parse(transcript: str, field_type: FieldType, **kwargs) -> SpokenValue:
    if field_type == FieldType.PERCENTAGE:
        return parse_percentage(transcript)
    if field_type == FieldType.SIGNED_LEVEL:
        return parse_signed_level(transcript, **kwargs)
    if field_type == FieldType.NAME_WITH_STATE:
        return parse_name_with_state(transcript, **kwargs)
    if field_type == FieldType.ENUM_STATE:
        return parse_enum_state(transcript, **kwargs)
    raise ValueError(f"unsupported field type: {field_type}")
