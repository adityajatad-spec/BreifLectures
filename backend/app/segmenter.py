"""Turns caption snippets (2-5s each) into segments big enough to judge (~20s each).

Segments are the unit everything else works on: the analyzer labels them and the
player skips them. Gaps with no captions become their own `silence` segments.
"""

import html
import re

from .models import Label, Segment, Snippet

TARGET_SECONDS = 20.0
MAX_SECONDS = 40.0
SILENCE_GAP = 3.0

_SENTENCE_END = re.compile(r"[.!?][\"')\]]*$")
_BRACKETED = re.compile(r"\[(music|applause|laughter|silence|inaudible)\]", re.I)


def clean(text: str) -> str:
    return " ".join(html.unescape(text).replace("\n", " ").split())


def build_segments(snippets: list[Snippet]) -> list[Segment]:
    segments: list[Segment] = []
    buf: list[Snippet] = []

    def flush() -> None:
        if not buf:
            return
        text = clean(" ".join(s.text for s in buf))
        start, end = buf[0].start, buf[-1].start + buf[-1].duration
        label = Label.silence if not _BRACKETED.sub("", text).strip() else Label.core
        segments.append(Segment(id=len(segments), start=start, end=end, text=text, label=label))
        buf.clear()

    prev_end = 0.0
    for snip in sorted(snippets, key=lambda s: s.start):
        if not clean(snip.text):
            continue
        if snip.start - prev_end >= SILENCE_GAP:
            flush()
            segments.append(
                Segment(id=len(segments), start=prev_end, end=snip.start, text="", label=Label.silence, importance=0.0)
            )
        buf.append(snip)
        # Caption durations overlap the next line, so the true end is the next start.
        prev_end = max(prev_end, snip.start + min(snip.duration, 10.0))

        length = snip.start + snip.duration - buf[0].start
        if length >= MAX_SECONDS or (length >= TARGET_SECONDS and _SENTENCE_END.search(snip.text.strip())):
            flush()
    flush()

    # Make segments contiguous so the timeline has no holes and skips land cleanly.
    for a, b in zip(segments, segments[1:]):
        a.end = b.start
    return segments
