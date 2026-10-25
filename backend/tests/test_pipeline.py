from fastapi.testclient import TestClient

from app import analyze_heuristic, config, main, youtube
from app.models import Label, Snippet
from app.segmenter import build_segments


def lecture() -> list[Snippet]:
    lines = [
        (0.0, "can everyone hear me? let me share my screen."),
        (4.0, "okay give me a second."),
        # 10 seconds of nothing: should become a silence segment
        (18.0, "Today we cover gradient descent, the workhorse of machine learning."),
        (22.0, "We start with a loss function that measures how wrong the model is."),
        (26.0, "The gradient points uphill, so we step in the opposite direction."),
        (30.0, "The step size is called the learning rate and it matters a lot."),
        (34.0, "Too large and we overshoot, too small and training crawls."),
        (40.0, "Before we go on, don't forget to like and subscribe and hit the notification bell."),
        (46.0, "To recap: follow the negative gradient, scaled by the learning rate."),
    ]
    return [Snippet(start=s, duration=4.0, text=t) for s, t in lines]


def test_segments_are_contiguous_and_capture_silence():
    segs = build_segments(lecture())
    assert segs[0].start == 0.0
    for a, b in zip(segs, segs[1:]):
        assert a.end == b.start
    assert any(s.label == Label.silence and s.end - s.start >= 3 for s in segs)
    assert [s.id for s in segs] == list(range(len(segs)))


def test_heuristic_labels():
    segs, _ = analyze_heuristic.analyze(build_segments(lecture()))
    by_text = {s.text[:20]: s for s in segs if s.text}
    labels = {s.label for s in segs}
    assert Label.admin in labels
    assert Label.silence in labels
    assert any(s.label == Label.core and "gradient descent" in s.text for s in segs), by_text


def test_analyze_endpoint_offline(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ANALYZER", "heuristic")
    monkeypatch.setattr(main.cache, "CACHE_DB", tmp_path / "cache.sqlite3")
    monkeypatch.setattr(youtube, "fetch_transcript", lambda vid, langs: lecture())
    monkeypatch.setattr(youtube, "fetch_title", lambda vid: "Gradient Descent")

    client = TestClient(main.app)
    resp = client.post("/api/analyze", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["video_id"] == "dQw4w9WgXcQ"
    assert body["engine"] == "heuristic"
    assert body["duration"] > 45

    # Second call is served from the cache even if YouTube is now unreachable.
    monkeypatch.setattr(youtube, "fetch_transcript", lambda vid, langs: (_ for _ in ()).throw(AssertionError))
    assert client.post("/api/analyze", json={"url": "dQw4w9WgXcQ"}).json() == body

    assert client.post("/api/analyze", json={"url": "https://vimeo.com/1"}).status_code == 400
