"""Everything that talks to YouTube: URL parsing, metadata, captions."""

import logging
import re
from urllib.parse import parse_qs, urlparse

import httpx
from youtube_transcript_api import (
    AgeRestricted,
    CouldNotRetrieveTranscript,
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    Transcript,
    TranscriptList,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeTranscriptApi,
)

from .models import Snippet

log = logging.getLogger(__name__)

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeError(Exception):
    pass


def parse_video_id(url: str) -> str:
    """Accepts watch, youtu.be, shorts, embed and live URLs, or a bare 11-character ID."""
    url = url.strip()
    if _ID.match(url):
        return url
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    parts = [p for p in parsed.path.split("/") if p]

    candidate = None
    if host == "youtu.be" and parts:
        candidate = parts[0]
    elif host in ("youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        if parts[:1] == ["watch"] or not parts:
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        elif len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v"):
            candidate = parts[1]

    if not candidate or not _ID.match(candidate):
        raise YouTubeError(f"Not a recognizable YouTube video link: {url}")
    return candidate


def fetch_title(video_id: str) -> str:
    """oEmbed needs no API key. Falls back to the ID if YouTube is unreachable."""
    try:
        resp = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("title") or video_id
    except (httpx.HTTPError, ValueError):
        return video_id


# What the user sees instead of the library's exception names.
_EXPLANATIONS: list[tuple[tuple[type[Exception], ...], str]] = [
    ((TranscriptsDisabled, NoTranscriptFound), "This video has no captions, so it can't be analyzed yet."),
    ((VideoUnavailable, VideoUnplayable), "This video is unavailable: it may be private, deleted or region-locked."),
    ((AgeRestricted,), "This video is age-restricted, so YouTube won't share its captions."),
    ((IpBlocked, RequestBlocked), "YouTube is temporarily blocking caption requests from your network. Try again later."),
    ((InvalidVideoId,), "That isn't a valid YouTube video link."),
]


def _explain(exc: Exception) -> str:
    for types, message in _EXPLANATIONS:
        if isinstance(exc, types):
            return message
    return f"Couldn't get captions from YouTube ({type(exc).__name__}). Try again in a moment."


def _choose(transcripts: TranscriptList, languages: list[str]) -> Transcript:
    """The preferred language if there is one, else any captions, human-made before auto-generated."""
    try:
        return transcripts.find_transcript(languages)
    except NoTranscriptFound:
        available = sorted(transcripts, key=lambda t: t.is_generated)
        if not available:
            raise
        return available[0]


def _is_english(code: str) -> bool:
    return code.split("-")[0].lower() == "en"


def fetch_transcript(video_id: str, languages: list[str]) -> list[Snippet]:
    try:
        chosen = _choose(YouTubeTranscriptApi().list(video_id), languages)
        fetched = None
        # The model labels English best, so ask YouTube to translate other languages.
        english = next((t.language_code for t in chosen.translation_languages if _is_english(t.language_code)), None)
        if not _is_english(chosen.language_code) and chosen.is_translatable and english:
            try:
                fetched = chosen.translate(english).fetch()
                log.info("Using %s captions for %s, translated to English", chosen.language, video_id)
            except Exception as exc:  # translation is a bonus: the original captions still work
                log.warning("Translating %s captions failed (%s); using the original", chosen.language, exc)
        if fetched is None:
            fetched = chosen.fetch()
            log.info("Using %s captions for %s", chosen.language, video_id)
    except CouldNotRetrieveTranscript as exc:
        raise YouTubeError(_explain(exc)) from exc
    except Exception as exc:  # network failures and anything else the library lets through
        log.exception("Fetching captions for %s failed", video_id)
        raise YouTubeError(_explain(exc)) from exc
    return [Snippet(start=s.start, duration=s.duration, text=s.text) for s in fetched]
