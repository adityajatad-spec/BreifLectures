import pytest

from app.youtube import YouTubeError, parse_video_id


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s&list=PL123",
        "youtube.com/watch?v=dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?t=10",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ?feature=share",
        "dQw4w9WgXcQ",
    ],
)
def test_parse_video_id(url):
    assert parse_video_id(url) == "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url", ["https://vimeo.com/123456", "https://www.youtube.com/watch?v=short", "", "https://youtube.com/@channel"]
)
def test_parse_video_id_rejects(url):
    with pytest.raises(YouTubeError):
        parse_video_id(url)
