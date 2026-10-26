"""Choosing and fetching captions, against a stand-in for YouTube."""

from types import SimpleNamespace

import pytest
from youtube_transcript_api import (
    AgeRestricted,
    IpBlocked,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeRequestFailed,
)

from app import youtube


class FakeTranscript:
    def __init__(self, code, language, generated=False, translations=(), text=None, translate_fails=False):
        self.language_code, self.language, self.is_generated = code, language, generated
        self.translation_languages = [SimpleNamespace(language_code=c) for c in translations]
        self.is_translatable = bool(translations)
        self.text = text or f"{language} text"
        self.translate_fails = translate_fails
        self.translated_to = None

    def translate(self, code):
        self.translated_to = code
        if self.translate_fails:
            raise YouTubeRequestFailed("vid", Exception("429 Too Many Requests"))
        return FakeTranscript(code, f"English (from {self.language})")

    def fetch(self):
        return [SimpleNamespace(start=0.0, duration=2.0, text=self.text)]


class FakeList(list):
    def find_transcript(self, codes):
        for code in codes:
            for t in self:
                if t.language_code == code:
                    return t
        raise NoTranscriptFound("vid", codes, self)


def use(monkeypatch, listing):
    class FakeApi:
        def list(self, video_id):
            if isinstance(listing, Exception):
                raise listing
            return FakeList(listing)

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", FakeApi)


def test_prefers_requested_english(monkeypatch):
    use(monkeypatch, [FakeTranscript("hi", "Hindi"), FakeTranscript("en", "English")])
    result = youtube.fetch_transcript("vid", ["en"])
    assert result.snippets[0].text == "English text"
    assert result.languages == ["en"]


def test_any_language_is_used_as_spoken(monkeypatch):
    # Kept in the original language: translating would garble lectures that mix languages.
    hindi = FakeTranscript("hi", "Hindi", generated=True, translations=["en"])
    use(monkeypatch, [hindi])
    result = youtube.fetch_transcript("vid", ["en", "en-US"])
    assert result.snippets[0].text == "Hindi text"
    assert hindi.translated_to is None
    assert result.source == "YouTube captions · Hindi (auto-generated)"
    assert result.languages == ["hi"]


def test_human_captions_beat_auto_generated(monkeypatch):
    use(monkeypatch, [FakeTranscript("de", "German auto", generated=True), FakeTranscript("de", "German")])
    result = youtube.fetch_transcript("vid", ["en"])
    assert result.snippets[0].text == "German text"
    assert result.source == "YouTube captions · German"


@pytest.mark.parametrize(
    "error, message, speech_can_help",
    [
        (TranscriptsDisabled("vid"), "no captions", True),
        (IpBlocked("vid"), "temporarily blocking", True),
        (VideoUnavailable("vid"), "unavailable", False),
        (AgeRestricted("vid"), "age-restricted", False),
        (ConnectionError("offline"), "Try again", True),
    ],
)
def test_errors_are_explained_in_plain_words(monkeypatch, error, message, speech_can_help):
    use(monkeypatch, error)
    with pytest.raises(youtube.YouTubeError, match=message) as info:
        youtube.fetch_transcript("vid", ["en"])
    assert "TranscriptsDisabled" not in str(info.value)
    assert isinstance(info.value, youtube.NoCaptions) == speech_can_help


def test_video_without_any_captions(monkeypatch):
    use(monkeypatch, [])
    with pytest.raises(youtube.NoCaptions, match="no captions"):
        youtube.fetch_transcript("vid", ["en"])
