import pytest

from app import analyze_ollama, config
from app.models import Label, Segment
from app.segmenter import approx_tokens

from .fake_ollama import FakeOllama


def make_lecture(n=60, words_per_segment=80):
    segs = []
    for i in range(n):
        if i == 50:
            text = "let me explain gradient descent again, " + "same idea " * 30
        elif i == 55:
            text = "please subscribe to the channel, " + "thanks " * 30
        else:
            text = f"topic {i}, " + "word " * words_per_segment
        segs.append(Segment(id=i, start=i * 20.0, end=(i + 1) * 20.0, text=text))
    segs.insert(10, Segment(id=999, start=0, end=0, text="", label=Label.silence))
    return segs


@pytest.fixture
def fake(monkeypatch):
    with FakeOllama() as server:
        monkeypatch.setattr(config, "OLLAMA_HOST", server.url)
        monkeypatch.setattr(config, "OLLAMA_MODEL", "qwen3.5:4b")
        yield server


def test_windows_respect_budget_and_skip_silence():
    parts = analyze_ollama.windows(make_lecture())
    assert len(parts) > 1
    for window in parts:
        assert sum(approx_tokens(s.text) for s in window) <= analyze_ollama.WINDOW_TOKENS
        assert len(window) <= analyze_ollama.WINDOW_MAX_SEGMENTS
        assert all(s.label != Label.silence for s in window)


def test_status(fake, monkeypatch):
    assert analyze_ollama.status()[0] is True
    monkeypatch.setattr(config, "OLLAMA_MODEL", "llama3.2:3b")
    ready, why = analyze_ollama.status()
    assert not ready and "ollama pull llama3.2:3b" in why
    monkeypatch.setattr(config, "OLLAMA_HOST", "http://127.0.0.1:9")
    ready, why = analyze_ollama.status()
    assert not ready and "isn't running" in why


def test_analyze_labels_every_window(fake):
    progress = []
    segs, chapters, summary = analyze_ollama.analyze("Gradients", make_lecture(), lambda d, t: progress.append((d, t)))

    by_id = {s.id: s for s in segs}
    assert by_id[50].label == Label.repeat
    assert by_id[55].label == Label.promo and by_id[55].importance == 0.0
    assert by_id[3].label == Label.core and by_id[3].importance == 0.8
    assert by_id[999].label == Label.silence  # never sent to the model
    assert summary.startswith("A lecture about gradients")
    assert len(chapters) >= 2 and chapters == sorted(chapters, key=lambda c: c.start)
    assert progress[-1][0] == progress[-1][1]

    label_calls = [r for r in fake.requests if r.get("format")]
    first, second = label_calls[0], label_calls[1]
    assert first["options"]["num_ctx"] == config.OLLAMA_CTX
    assert first["options"]["temperature"] == 0
    assert first["think"] is False
    ids = first["format"]["properties"]["segments"]["items"]["properties"]["id"]["enum"]
    assert 999 not in ids
    # Later windows see what earlier ones covered, so repeats can be recognized.
    assert "nothing yet" in first["messages"][-1]["content"]
    assert "- topic 0" in second["messages"][-1]["content"]


def test_garbage_output_falls_back_to_heuristic(monkeypatch):
    with FakeOllama(broken_windows=2) as server:
        monkeypatch.setattr(config, "OLLAMA_HOST", server.url)
        segs, _, _ = analyze_ollama.analyze("Gradients", make_lecture())
    # First window failed twice (call + retry): it keeps heuristic labels instead of crashing.
    assert segs[0].topic == ""
    assert any(s.topic for s in segs)


def test_missing_model_is_a_clear_error(fake, monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_MODEL", "nope:1b")
    with pytest.raises(analyze_ollama.LocalModelError, match="ollama pull nope:1b"):
        analyze_ollama.analyze("x", make_lecture(5))
