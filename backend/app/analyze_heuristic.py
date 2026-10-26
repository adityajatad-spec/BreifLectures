"""Offline analyzer: no API key, no network. Rough, but makes the whole app usable for development."""

import re

from .models import Label, Segment
from .segmenter import approx_tokens

# Speech density in model tokens per second works in every script; English lectures run
# around 3-4. Well below 1 means mostly pauses.
SPARSE_TOKENS_PER_SEC = 0.8

FILLER_WORDS = re.compile(r"\b(um+|uh+|er+|hmm+|you know|i mean|like|sort of|kind of|basically|actually)\b", re.I)

PATTERNS: list[tuple[Label, re.Pattern[str]]] = [
    (
        Label.promo,
        re.compile(
            r"(subscribe|like (this|the) video|smash (that|the)|notification bell|sponsor|patreon|"
            r"link in the description|use (my )?code)",
            re.I,
        ),
    ),
    (
        Label.admin,
        re.compile(
            r"(can (you|everyone) (hear|see) me|share my screen|is (this|the mic) (on|working)|"
            r"office hours|homework|problem set|due (on|next)|midterm|attendance|"
            r"let me (just )?(find|open|pull up)|give (me|it) a (second|sec|moment))",
            re.I,
        ),
    ),
    (
        Label.recap,
        re.compile(
            r"(to (sum|recap|summarize)|in summary|last (time|lecture|class) we|"
            r"as i (said|mentioned)|let'?s review|quick recap)",
            re.I,
        ),
    ),
]


def _density(seg: Segment) -> float:
    return approx_tokens(seg.text) / max(seg.end - seg.start, 1.0)


def analyze(segments: list[Segment]) -> tuple[list[Segment], str]:
    for seg in segments:
        if seg.label == Label.silence:
            seg.importance = 0.0
            continue
        words = seg.text.split()
        for label, pattern in PATTERNS:
            if pattern.search(seg.text):
                seg.label = label
                break
        else:
            filler_ratio = len(FILLER_WORDS.findall(seg.text)) / max(len(words), 1)
            if filler_ratio > 0.15 or _density(seg) < SPARSE_TOKENS_PER_SEC:
                seg.label = Label.filler

        seg.importance = {
            Label.core: 0.6,
            Label.example: 0.6,
            Label.recap: 0.35,
            Label.repeat: 0.2,
            Label.tangent: 0.2,
            Label.admin: 0.1,
            Label.promo: 0.0,
            Label.filler: 0.05,
        }.get(seg.label, 0.5)
        # Denser speech tends to carry more content.
        if seg.label == Label.core:
            seg.importance = min(1.0, 0.4 + 0.075 * _density(seg))

    return segments, "Offline estimate."
