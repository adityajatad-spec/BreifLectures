"""Local AI analyzer: a small model served by Ollama labels the lecture.

A 4B model at an 8k context can't read a whole lecture at once, so we go window by
window (~15 min of speech each). To still catch content that repeats something said
much earlier, each window gets the running outline of topics covered so far.

Every request uses a JSON schema, which Ollama turns into a grammar: the model can only
emit valid labels and segment ids, which keeps small models on the rails.
"""

import json
from collections.abc import Callable

import ollama

from . import analyze_heuristic, config
from .models import Chapter, Label, Segment

WINDOW_WORDS = 1800
WINDOW_MAX_SEGMENTS = 40
OUTLINE_MAX = 40
MIN_CHAPTER_GAP = 60.0

SYSTEM = """You label parts of a recorded lecture so students can skip what they don't need.
You get a slice of the transcript as numbered segments. For EVERY segment give:
- label, one of:
  core: new, essential material
  example: worked example or demo of the material
  recap: summary of what was already covered
  repeat: explains again something from the "already covered" list, adding nothing new
  tangent: off-topic story or digression
  admin: logistics such as homework, exams, mic checks, screen sharing, waiting
  promo: sponsors, "like and subscribe"
  filler: stalling, ums, setup chatter
- importance: 0-10, how much a student loses by skipping it (10 = essential)
- topic: at most 5 words
Also list where new sections start, with a short title (at most 6 words)."""

SUMMARY_SYSTEM = "Write a two-sentence summary of a lecture from its title and topic outline. Plain text, no preamble."

ProgressFn = Callable[[int, int], None]


class LocalModelError(Exception):
    pass


def client() -> ollama.Client:
    return ollama.Client(host=config.OLLAMA_HOST, timeout=600)


def _canonical(name: str) -> str:
    return name if ":" in name else f"{name}:latest"


def status() -> tuple[bool, str]:
    """(ready, explanation) for the configured model."""
    try:
        pulled = {_canonical(m.model) for m in client().list().models if m.model}
    except (ConnectionError, ollama.ResponseError):
        return False, f"Ollama isn't running at {config.OLLAMA_HOST}."
    if _canonical(config.OLLAMA_MODEL) not in pulled:
        return False, f"Model not downloaded yet. Run: ollama pull {config.OLLAMA_MODEL}"
    return True, f"Using {config.OLLAMA_MODEL} via Ollama."


def windows(segments: list[Segment]) -> list[list[Segment]]:
    """Group speech segments into windows that fit comfortably in the context budget."""
    out: list[list[Segment]] = []
    current: list[Segment] = []
    words = 0
    for seg in segments:
        if seg.label == Label.silence:
            continue
        n = len(seg.text.split())
        if current and (words + n > WINDOW_WORDS or len(current) >= WINDOW_MAX_SEGMENTS):
            out.append(current)
            current, words = [], 0
        current.append(seg)
        words += n
    if current:
        out.append(current)
    return out


def _schema(ids: list[int]) -> dict:
    labels = [label.value for label in Label if label != Label.silence]
    return {
        "type": "object",
        "properties": {
            "segments": {
                "type": "array",
                "minItems": len(ids),
                "maxItems": len(ids),
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "enum": ids},
                        "label": {"type": "string", "enum": labels},
                        "importance": {"type": "integer", "enum": list(range(11))},
                        "topic": {"type": "string"},
                    },
                    "required": ["id", "label", "importance", "topic"],
                },
            },
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "segment_id": {"type": "integer", "enum": ids},
                        "title": {"type": "string"},
                    },
                    "required": ["segment_id", "title"],
                },
            },
        },
        "required": ["segments", "sections"],
    }


def _timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _render(title: str, window: list[Segment], outline: list[str]) -> str:
    covered = "\n".join(f"- {t}" for t in outline) if outline else "(nothing yet: this is the start)"
    lines = [f"Lecture: {title}", "", "Already covered earlier in this lecture:", covered, "", "Segments:"]
    lines += [f"[{s.id}] {_timestamp(s.start)} {s.text}" for s in window]
    return "\n".join(lines)


def _chat(llm: ollama.Client, system: str, prompt: str, schema: dict | None) -> str:
    try:
        resp = llm.chat(
            model=config.OLLAMA_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            format=schema,
            think=config.OLLAMA_THINK,
            options={"num_ctx": config.OLLAMA_CTX, "temperature": 0},
            keep_alive=config.OLLAMA_KEEP_ALIVE,
        )
    except ConnectionError as exc:
        raise LocalModelError(f"Ollama isn't running at {config.OLLAMA_HOST}.") from exc
    except ollama.ResponseError as exc:
        if exc.status_code == 404:
            raise LocalModelError(f"Model not downloaded yet. Run: ollama pull {config.OLLAMA_MODEL}") from exc
        raise LocalModelError(f"Ollama error: {exc.error}") from exc
    return resp.message.content or ""


def _label_window(llm: ollama.Client, title: str, window: list[Segment], outline: list[str]) -> dict:
    prompt = _render(title, window, outline)
    schema = _schema([s.id for s in window])
    for _ in range(2):  # small models occasionally truncate; one retry is usually enough
        try:
            data = json.loads(_chat(llm, SYSTEM, prompt, schema))
            if isinstance(data.get("segments"), list):
                return data
        except json.JSONDecodeError:
            pass
    return {"segments": [], "sections": []}  # keep the heuristic labels for this window


def analyze(
    title: str, segments: list[Segment], progress: ProgressFn = lambda done, total: None
) -> tuple[list[Segment], list[Chapter], str]:
    # Start from the heuristic so a window the model fumbles still has sensible labels.
    segments, _ = analyze_heuristic.analyze(segments)
    by_id = {s.id: s for s in segments}
    llm = client()
    parts = windows(segments)
    total = len(parts) + 1  # +1 for the summary
    outline: list[str] = []
    chapters: list[Chapter] = []

    for i, window in enumerate(parts):
        progress(i, total)
        data = _label_window(llm, title, window, outline)
        allowed = {s.id for s in window}
        for item in data["segments"]:
            seg = by_id.get(item.get("id"))
            if seg is None or seg.id not in allowed:
                continue
            try:
                seg.label = Label(item["label"])
                seg.importance = max(0, min(10, int(item["importance"]))) / 10
            except (KeyError, ValueError, TypeError):
                continue
            seg.topic = str(item.get("topic", ""))[:60]
            if seg.label in (Label.core, Label.example) and seg.topic and seg.topic.lower() not in map(str.lower, outline):
                outline.append(seg.topic)
        outline = outline[-OUTLINE_MAX:]

        sections = [(by_id[sec["segment_id"]], str(sec.get("title", "")).strip())
                    for sec in data.get("sections", []) if sec.get("segment_id") in allowed]
        for seg, title_text in sorted(sections, key=lambda pair: pair[0].start):
            if not title_text:
                continue
            if chapters and (seg.start - chapters[-1].start < MIN_CHAPTER_GAP or title_text.lower() == chapters[-1].title.lower()):
                continue
            chapters.append(Chapter(start=seg.start, title=title_text[:80]))

    progress(len(parts), total)
    summary = ""
    if outline:
        summary = _chat(llm, SUMMARY_SYSTEM, f"Title: {title}\nTopics in order:\n" + "\n".join(outline), None).strip()
    progress(total, total)
    return segments, chapters, summary
