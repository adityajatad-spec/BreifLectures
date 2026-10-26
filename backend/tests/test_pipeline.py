import time

import pytest
from fastapi.testclient import TestClient

from app import analyze_heuristic, config, main, youtube
from app.models import Label, Snippet, Transcript
from app.segmenter import build_segments

from .fake_ollama import FakeOllama


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


def captions() -> Transcript:
    return Transcript(snippets=lecture(), source="YouTube captions · English", languages=["en"])


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


def wait_for(client, job):
    deadline = time.time() + 10
    while job["status"] in ("queued", "running"):
        assert time.time() < deadline, job
        time.sleep(0.05)
        job = client.get(f"/api/jobs/{job['id']}").json()
    return job


@pytest.fixture
def stubbed(monkeypatch, tmp_path):
    monkeypatch.setattr(main.cache, "CACHE_DB", tmp_path / "cache.sqlite3")
    monkeypatch.setattr(youtube, "fetch_transcript", lambda vid, langs: captions())
    monkeypatch.setattr(youtube, "fetch_title", lambda vid: "Gradient Descent")
    return TestClient(main.app, base_url="http://127.0.0.1")


def test_analyze_offline_falls_back_to_heuristic(stubbed, monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_HOST", "http://127.0.0.1:9")  # nothing listening
    job = wait_for(stubbed, stubbed.post("/api/analyze", json={"url": "https://youtu.be/dQw4w9WgXcQ"}).json())
    assert job["status"] == "done", job
    body = job["result"]
    assert body["video_id"] == "dQw4w9WgXcQ"
    assert body["engine"] == "heuristic"
    assert "isn't running" in body["summary"]
    assert body["duration"] > 45

    # Second call is served from the cache even if YouTube is now unreachable.
    monkeypatch.setattr(youtube, "fetch_transcript", lambda vid, langs: (_ for _ in ()).throw(AssertionError))
    again = stubbed.post("/api/analyze", json={"url": "dQw4w9WgXcQ"}).json()
    assert again["status"] == "done" and again["result"] == body

    assert stubbed.post("/api/analyze", json={"url": "https://vimeo.com/1"}).status_code == 400


def test_analyze_with_local_model(stubbed, monkeypatch):
    with FakeOllama() as server:
        monkeypatch.setattr(config, "OLLAMA_HOST", server.url)
        monkeypatch.setattr(config, "OLLAMA_MODEL", "qwen3.5:4b")
        assert stubbed.get("/api/health").json()["engine"] == "ollama"
        job = wait_for(stubbed, stubbed.post("/api/analyze", json={"url": "dQw4w9WgXcQ"}).json())
    assert job["status"] == "done", job
    assert job["result"]["engine"] == "ollama"
    assert job["result"]["chapters"]


def test_transcript_failure_becomes_job_error(stubbed, monkeypatch):
    def boom(vid, langs):
        raise youtube.YouTubeError("Could not get captions for dQw4w9WgXcQ: TranscriptsDisabled")

    monkeypatch.setattr(config, "ANALYZER", "heuristic")
    monkeypatch.setattr(youtube, "fetch_transcript", boom)
    job = wait_for(stubbed, stubbed.post("/api/analyze", json={"url": "dQw4w9WgXcQ"}).json())
    assert job["status"] == "error" and "TranscriptsDisabled" in job["error"]
