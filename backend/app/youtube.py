"""Everything that talks to YouTube: URL parsing, metadata, captions."""

import re
from urllib.parse import parse_qs, urlparse

import httpx
from youtube_transcript_api import YouTubeTranscriptApi

from .models import Snippet

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


def fetch_transcript(video_id: str, languages: list[str]) -> list[Snippet]:
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=languages)
    except Exception as exc:  # the library raises a dozen distinct types; all mean "no captions for us"
        raise YouTubeError(f"Could not get captions for {video_id}: {type(exc).__name__}") from exc
    return [Snippet(start=s.start, duration=s.duration, text=s.text) for s in fetched]
