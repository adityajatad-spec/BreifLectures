"""Choosing and fetching captions, against a stand-in for YouTube."""

from types import SimpleNamespace

import pytest
from youtube_transcript_api import IpBlocked, NoTranscriptFound, TranscriptsDisabled, YouTubeRequestFailed

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
    assert youtube.fetch_transcript("vid", ["en"])[0].text == "English text"


def test_other_language_is_translated_to_english(monkeypatch):
    hindi = FakeTranscript("hi", "Hindi", generated=True, translations=["fr", "en"])
    use(monkeypatch, [hindi])
    assert youtube.fetch_transcript("vid", ["en", "en-US"])[0].text == "English (from Hindi) text"
    assert hindi.translated_to == "en"


def test_falls_back_to_original_when_translation_fails(monkeypatch):
    use(monkeypatch, [FakeTranscript("hi", "Hindi", translations=["en"], translate_fails=True)])
    assert youtube.fetch_transcript("vid", ["en"])[0].text == "Hindi text"


def test_human_captions_beat_auto_generated(monkeypatch):
    use(monkeypatch, [FakeTranscript("de", "German auto", generated=True), FakeTranscript("de", "German")])
    assert youtube.fetch_transcript("vid", ["en"])[0].text == "German text"


@pytest.mark.parametrize(
    "error, message",
    [
        (TranscriptsDisabled("vid"), "no captions"),
        (IpBlocked("vid"), "temporarily blocking"),
        (ConnectionError("offline"), "Try again"),
    ],
)
def test_errors_are_explained_in_plain_words(monkeypatch, error, message):
    use(monkeypatch, error)
    with pytest.raises(youtube.YouTubeError, match=message) as info:
        youtube.fetch_transcript("vid", ["en"])
    assert "TranscriptsDisabled" not in str(info.value)


def test_video_without_any_captions(monkeypatch):
    use(monkeypatch, [])
    with pytest.raises(youtube.YouTubeError, match="no captions"):
        youtube.fetch_transcript("vid", ["en"])
