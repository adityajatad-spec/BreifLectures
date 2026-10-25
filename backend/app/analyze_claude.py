"""AI analyzer: one Claude call labels every segment of the lecture.

The whole transcript goes in a single request (a 3-hour lecture is ~40k tokens), so
Claude can spot content that repeats something said an hour earlier — which is
exactly the redundancy a per-chunk approach would miss.
"""

import json

import anthropic

from .config import CLAUDE_MODEL
from .models import Chapter, Label, Segment

SKIPPABLE_HELP = """\
Labels:
- core: new, essential material. The point of the lecture.
- example: a worked example, demo or illustration of core material.
- recap: a summary of material just covered or covered last time.
- repeat: restates earlier material in this lecture without adding anything.
- tangent: a digression, anecdote or off-topic discussion.
- admin: logistics — homework, exams, mic checks, screen sharing, waiting for people.
- promo: sponsor reads, self-promotion, "like and subscribe".
- filler: stalling, verbal filler, setting up equipment while talking.
- silence: no meaningful speech.

importance (0.0–1.0): how much a student who skips this segment loses.
1.0 = the single most important explanation in the lecture; 0.0 = nothing lost."""

SYSTEM = f"""You analyze recorded lectures so students can watch a shorter version.
You receive a transcript split into numbered segments with timestamps. Label every
segment, score its importance, give it a short topic (≤6 words), group the lecture
into chapters, and write a two-sentence summary of the lecture.

{SKIPPABLE_HELP}

Judge each segment in the context of the whole lecture: a clear first explanation is
core, the same idea explained again later with no new angle is repeat. Return every
segment id exactly once."""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "label": {"type": "string", "enum": [label.value for label in Label]},
                    "importance": {"type": "number"},
                    "topic": {"type": "string"},
                },
                "required": ["id", "label", "importance", "topic"],
                "additionalProperties": False,
            },
        },
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "segment_id": {"type": "integer"},
                    "title": {"type": "string"},
                },
                "required": ["segment_id", "title"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "segments", "chapters"],
    "additionalProperties": False,
}


class ClaudeAnalysisError(Exception):
    pass


def _timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _render(title: str, segments: list[Segment]) -> str:
    lines = [f"Lecture title: {title}", ""]
    for seg in segments:
        text = seg.text or "(no speech)"
        lines.append(f"[{seg.id}] {_timestamp(seg.start)}–{_timestamp(seg.end)} {text}")
    return "\n".join(lines)


def analyze(title: str, segments: list[Segment]) -> tuple[list[Segment], list[Chapter], str]:
    client = anthropic.Anthropic()
    try:
        with client.beta.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=64000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            system=SYSTEM,
            messages=[{"role": "user", "content": _render(title, segments)}],
        ) as stream:
            message = stream.get_final_message()
    except anthropic.AuthenticationError as exc:
        raise ClaudeAnalysisError("Anthropic credentials were rejected.") from exc
    except anthropic.RateLimitError as exc:
        raise ClaudeAnalysisError("Rate limited by the Anthropic API; try again shortly.") from exc
    except anthropic.APIStatusError as exc:
        raise ClaudeAnalysisError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise ClaudeAnalysisError("Could not reach the Anthropic API.") from exc

    if message.stop_reason == "refusal":
        raise ClaudeAnalysisError("Claude declined to analyze this transcript.")
    if message.stop_reason == "max_tokens":
        raise ClaudeAnalysisError("Lecture too long for a single analysis pass.")

    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClaudeAnalysisError("Claude returned malformed JSON.") from exc

    by_id = {seg.id: seg for seg in segments}
    for item in data["segments"]:
        seg = by_id.get(item["id"])
        if seg is None:
            continue
        seg.label = Label(item["label"])
        seg.importance = max(0.0, min(1.0, float(item["importance"])))
        seg.topic = item["topic"]

    chapters = [
        Chapter(start=by_id[c["segment_id"]].start, title=c["title"])
        for c in data["chapters"]
        if c["segment_id"] in by_id
    ]
    chapters.sort(key=lambda c: c.start)
    return segments, chapters, data["summary"]
