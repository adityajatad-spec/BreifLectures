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
    TranscriptList,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeTranscriptApi,
)
from youtube_transcript_api import Transcript as CaptionTrack

from .models import Snippet, Transcript

log = logging.getLogger(__name__)

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeError(Exception):
    pass


class NoCaptions(YouTubeError):
    """YouTube has no usable captions for this video; speech-to-text can still work."""


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


def _choose(transcripts: TranscriptList, languages: list[str]) -> CaptionTrack:
    """The preferred language if there is one, else any captions, human-made before auto-generated."""
    try:
        return transcripts.find_transcript(languages)
    except NoTranscriptFound:
        available = sorted(transcripts, key=lambda t: t.is_generated)
        if not available:
            raise
        return available[0]


def fetch_transcript(video_id: str, languages: list[str]) -> Transcript:
    # Captions stay in their original language. Machine-translating them would garble
    # lectures that mix languages, and the model reads the original as it was spoken.
    try:
        chosen = _choose(YouTubeTranscriptApi().list(video_id), languages)
        fetched = chosen.fetch()
    except (VideoUnavailable, VideoUnplayable, AgeRestricted, InvalidVideoId) as exc:
        raise YouTubeError(_explain(exc)) from exc  # the audio won't be reachable either
    except Exception as exc:
        # No captions, blocked or failed caption requests: the audio may still be reachable,
        # so speech-to-text gets a try.
        if not isinstance(exc, CouldNotRetrieveTranscript):
            log.exception("Fetching captions for %s failed", video_id)
        raise NoCaptions(_explain(exc)) from exc

    language = chosen.language
    if chosen.is_generated and "auto" not in language.lower():
        language += " (auto-generated)"
    log.info("Using %s captions for %s", language, video_id)
    return Transcript(
        snippets=[Snippet(start=s.start, duration=s.duration, text=s.text) for s in fetched],
        source=f"YouTube captions · {language}",
        languages=[chosen.language_code],
    )
