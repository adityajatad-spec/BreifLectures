"""Shared data shapes. These are also the JSON contract with the web client (web/src/lib/types.ts)."""

from enum import Enum

from pydantic import BaseModel


class Label(str, Enum):
    core = "core"  # new, essential material
    example = "example"  # worked example / demo of core material
    recap = "recap"  # summary of what was just covered (useful, but skippable)
    repeat = "repeat"  # restates earlier content with nothing new
    tangent = "tangent"  # off-topic story or digression
    admin = "admin"  # logistics: homework, mic checks, "can you see my screen"
    promo = "promo"  # sponsor reads, "like and subscribe"
    filler = "filler"  # ums, stalling, dead air with talking
    silence = "silence"  # no speech at all


class Snippet(BaseModel):
    """One caption line as YouTube returns it."""

    start: float
    duration: float
    text: str


class Segment(BaseModel):
    id: int
    start: float
    end: float
    text: str
    label: Label = Label.core
    importance: float = 0.5  # 0..1, how much a learner loses by skipping it
    topic: str = ""


class Chapter(BaseModel):
    start: float
    title: str


class Analysis(BaseModel):
    video_id: str
    title: str
    duration: float
    engine: str  # "ollama" or "heuristic"
    summary: str = ""
    segments: list[Segment]
    chapters: list[Chapter] = []
    # Where the words came from, e.g. "YouTube captions · Hindi (auto-generated)", and the
    # languages spoken (ISO codes, most-spoken first).
    transcript_source: str = ""
    languages: list[str] = []


class Transcript(BaseModel):
    snippets: list[Snippet]
    source: str
    languages: list[str] = []


class AnalyzeRequest(BaseModel):
    url: str
    force: bool = False  # bypass the cache


class Job(BaseModel):
    """Analysis runs in the background (a local model takes minutes); the client polls this."""

    id: str
    video_id: str
    status: str  # queued | running | done | error
    step: str = ""
    done: int = 0
    total: int = 0
    error: str | None = None
    result: Analysis | None = None


class LibraryItem(BaseModel):
    video_id: str
    title: str
    duration: float
    engine: str
    analyzed_at: str
