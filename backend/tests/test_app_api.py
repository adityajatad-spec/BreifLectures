import time

import pytest
from fastapi.testclient import TestClient

from app import config, main, ollama_setup
from app.models import Analysis, Segment

from .fake_ollama import FakeOllama


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(main.cache, "CACHE_DB", tmp_path / "cache.sqlite3")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "OLLAMA_MODEL", "qwen3.5:4b")
    monkeypatch.setattr(config, "OLLAMA_THINK", False)
    return TestClient(main.app, base_url="http://127.0.0.1")


def analysis(video_id: str, engine: str, title: str = "T") -> Analysis:
    return Analysis(
        video_id=video_id,
        title=title,
        duration=60,
        engine=engine,
        segments=[Segment(id=0, start=0, end=60, text="hello")],
    )


def test_settings_round_trip(client):
    assert client.get("/api/settings").json() == {"model": "qwen3.5:4b", "think": False}
    saved = client.put("/api/settings", json={"model": " qwen3:4b ", "think": True}).json()
    assert saved == {"model": "qwen3:4b", "think": True}
    assert config.OLLAMA_MODEL == "qwen3:4b"
    assert '"qwen3:4b"' in config.SETTINGS_FILE.read_text()
    assert client.put("/api/settings", json={"model": "  ", "think": False}).status_code == 400


def test_saved_settings_load_on_startup(client):
    config.SETTINGS_FILE.write_text('{"model": "llama3.2:3b", "think": true}')
    with client:  # entering runs the lifespan
        assert client.get("/api/settings").json() == {"model": "llama3.2:3b", "think": True}


def test_library_lists_and_forgets(client):
    main.cache.put(analysis("aaaaaaaaaaa", "heuristic", "First"))
    main.cache.put(analysis("bbbbbbbbbbb", "heuristic", "Second"))
    main.cache.put(analysis("aaaaaaaaaaa", "ollama", "First"))
    items = client.get("/api/library").json()
    assert [i["video_id"] for i in items] == ["aaaaaaaaaaa", "bbbbbbbbbbb"]
    assert items[0]["engine"] == "ollama"

    client.delete("/api/library/aaaaaaaaaaa")
    assert [i["video_id"] for i in client.get("/api/library").json()] == ["bbbbbbbbbbb"]


def test_cached_ai_analysis_wins_when_ollama_is_off(client, monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_HOST", "http://127.0.0.1:9")
    main.cache.put(analysis("ccccccccccc", "ollama"))
    job = client.post("/api/analyze", json={"url": "ccccccccccc"}).json()
    assert job["status"] == "done" and job["result"]["engine"] == "ollama"


def test_setup_reports_each_stage(client, monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_HOST", "http://127.0.0.1:9")
    monkeypatch.setattr(ollama_setup, "_MAC_APP", ollama_setup.Path("/nonexistent/Ollama.app"))
    monkeypatch.setattr(ollama_setup.shutil, "which", lambda name: None)
    status = client.get("/api/setup").json()
    assert status["ollama"] == "missing" and not status["model_ready"]
    assert status["recommended"][0]["name"] == "qwen3.5:4b"

    with FakeOllama(models=["llama3.2:3b"]) as server:
        monkeypatch.setattr(config, "OLLAMA_HOST", server.url)
        status = client.get("/api/setup").json()
        assert status["ollama"] == "running"
        assert status["pulled"] == ["llama3.2:3b"]
        assert not status["model_ready"]

        pull = client.post("/api/setup/pull", json={"model": "qwen3.5:4b"}).json()
        assert pull["status"] == "running"
        deadline = time.time() + 5
        while (pull := client.get("/api/setup").json()["pull"])["status"] == "running":
            assert time.time() < deadline
            time.sleep(0.02)
        assert pull["status"] == "done"
        assert (pull["completed"], pull["total"]) == (3_010, 3_010)  # both blobs, not just the last one
        assert client.get("/api/setup").json()["model_ready"]

        client.post("/api/setup/pull", json={"model": "missing:1b"})
        deadline = time.time() + 5
        while (pull := client.get("/api/setup").json()["pull"])["status"] == "running":
            assert time.time() < deadline
            time.sleep(0.02)
        assert pull["status"] == "error" and "does not exist" in pull["error"]


def test_rejects_foreign_host_headers(client):
    # DNS rebinding: evil.example resolving to 127.0.0.1 must not reach the API.
    assert client.get("/api/library", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/library", headers={"Host": "localhost:5173"}).status_code == 200
