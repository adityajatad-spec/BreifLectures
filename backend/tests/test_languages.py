"""Lectures in any language, mixed languages, and lectures without captions."""

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import analyze_heuristic, analyze_ollama, config, main, speech, transcribe, youtube
from app.models import Label, Segment, Snippet, Transcript
from app.segmenter import approx_tokens, build_segments

HINDI = "आज हम न्यूटन के गति के नियमों को समझेंगे और देखेंगे कि बल कैसे काम करता है।"
CHINESE = "今天我们学习牛顿运动定律，看看力是如何改变物体运动状态的。这是物理学的基础。"
HINGLISH = "So guys आज का topic है derivatives, matlab rate of change, समझ गए?"


def snippets(lines: list[str], every: float = 6.0) -> list[Snippet]:
    return [Snippet(start=i * every, duration=every, text=t) for i, t in enumerate(lines)]


# --- Text handling in any script ----------------------------------------------------------


@pytest.mark.parametrize(
    "part, end",
    [("आज हम न्यूटन के नियम समझेंगे", "।"), ("今天我们学习牛顿运动定律", "。"), ("هذه هي المشتقة", "؟")],
)
def test_sentence_ends_in_other_scripts_close_segments(part, end):
    # 8 s caption lines; every third ends a sentence in its own script. Segments should close
    # there (24 s) instead of running on to the 40 s cap, which is what an English-only rule did.
    lines = [part, part, part + end] * 4
    segs = build_segments(snippets(lines, every=8.0))
    assert [round(s.end - s.start) for s in segs] == [24, 24, 24, 24]


def test_caption_markers_in_any_language_count_as_silence():
    segs = build_segments(snippets(["[संगीत]", "[Música]", "[音楽]", "♪♪", "(applause)"], every=8.0))
    assert {s.label for s in segs} == {Label.silence}


def test_token_estimate_is_fair_across_scripts():
    # Same sentence meaning; estimates should be the same order of magnitude, not 1 vs 40.
    english = approx_tokens("Today we will understand Newton's laws of motion and how force works.")
    for other in (HINDI, CHINESE):
        assert english / 3 < approx_tokens(other) < english * 4


def test_windows_cap_text_without_spaces():
    segs = [Segment(id=i, start=i * 20.0, end=(i + 1) * 20.0, text=CHINESE * 4) for i in range(120)]
    parts = analyze_ollama.windows(segs)
    assert len(parts) > 3  # word counting would have seen 1 "word" per segment
    for window in parts:
        assert sum(approx_tokens(s.text) for s in window) <= analyze_ollama.WINDOW_TOKENS


@pytest.mark.parametrize("text", [CHINESE * 2, HINDI * 2, HINGLISH * 2])
def test_offline_estimate_does_not_call_dense_speech_filler(text):
    segs, _ = analyze_heuristic.analyze([Segment(id=0, start=0, end=20, text=text)])
    assert segs[0].label == Label.core


# --- The AI prompt -----------------------------------------------------------------------


def test_prompt_handles_any_language_and_asks_for_the_output_language(monkeypatch):
    assert "switch languages" in analyze_ollama.SYSTEM
    window = [Segment(id=0, start=0, end=20, text=HINGLISH)]

    monkeypatch.setattr(config, "OUTPUT_LANGUAGE", "Hindi")
    assert analyze_ollama._render("Calculus", window, []).endswith("title in Hindi.")

    monkeypatch.setattr(config, "OUTPUT_LANGUAGE", "auto")
    assert "the lecture's main language" in analyze_ollama._render("Calculus", window, [])


# --- No captions: speech-to-text -----------------------------------------------------------


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    monkeypatch.setattr(main.cache, "CACHE_DB", tmp_path / "cache.sqlite3")
    monkeypatch.setattr(config, "ANALYZER", "heuristic")
    monkeypatch.setattr(youtube, "fetch_title", lambda vid: "Lecture")
    return TestClient(main.app, base_url="http://127.0.0.1")


def run_job(client, video_id="dQw4w9WgXcQ"):
    job = client.post("/api/analyze", json={"url": video_id}).json()
    deadline = time.time() + 10
    seen = set()
    while job["status"] in ("queued", "running"):
        assert time.time() < deadline, job
        seen.add(job["step"].split(" · ")[0])
        time.sleep(0.01)
        job = client.get(f"/api/jobs/{job['id']}").json()
    return job, seen


def no_captions(vid, langs):
    raise youtube.NoCaptions("This video has no captions, so it can't be analyzed yet.")


def test_lecture_without_captions_is_transcribed(app_client, monkeypatch):
    def fake_speech(video_id, on_progress):
        for stage in ("audio", "model", "transcribe"):
            on_progress(stage, 0.5)
            time.sleep(0.05)
        return snippets([HINGLISH] * 10), ["hi", "en"]

    monkeypatch.setattr(youtube, "fetch_transcript", no_captions)
    monkeypatch.setattr(speech, "transcribe_video", fake_speech)
    job, steps = run_job(app_client)
    assert job["status"] == "done", job
    assert job["result"]["transcript_source"] == "Transcribed on this computer"
    assert job["result"]["languages"] == ["hi", "en"]
    assert "Turning speech into text" in steps


def test_when_speech_to_text_fails_too_the_user_hears_both_reasons(app_client, monkeypatch):
    def broken(video_id, on_progress):
        raise speech.SpeechError("Couldn't download the lecture's audio: Sign in to confirm your age")

    monkeypatch.setattr(youtube, "fetch_transcript", no_captions)
    monkeypatch.setattr(speech, "transcribe_video", broken)
    job, _ = run_job(app_client)
    assert job["status"] == "error"
    assert "no captions" in job["error"] and "Sign in to confirm your age" in job["error"]


def test_captions_are_used_without_touching_speech_to_text(app_client, monkeypatch):
    monkeypatch.setattr(
        youtube,
        "fetch_transcript",
        lambda vid, langs: Transcript(snippets=snippets([CHINESE] * 10), source="YouTube captions · Chinese", languages=["zh"]),
    )
    monkeypatch.setattr(speech, "transcribe_video", lambda *a: pytest.fail("should not transcribe"))
    job, _ = run_job(app_client)
    assert job["result"]["transcript_source"] == "YouTube captions · Chinese"


# --- The worker process protocol -----------------------------------------------------------


def fake_worker(tmp_path: Path, body: str) -> str:
    script = tmp_path / "worker.py"
    script.write_text(f"#!{sys.executable}\nimport json, sys\n" + body)
    script.chmod(0o755)
    return str(script)


def test_speech_reads_progress_and_result_from_the_worker(monkeypatch, tmp_path):
    worker = fake_worker(
        tmp_path,
        """
assert "--video-id" in sys.argv and "--model" in sys.argv
print("some library chatter")
for stage, f in [("audio", 0.5), ("model", 1.0), ("transcribe", 0.25)]:
    print(json.dumps({"event": "progress", "stage": stage, "fraction": f}), flush=True)
print(json.dumps({"event": "result", "languages": ["ta", "en"],
                  "snippets": [{"start": 0, "duration": 2, "text": "வணக்கம் everyone"}]}, ensure_ascii=False))
""",
    )
    monkeypatch.setattr(config, "TRANSCRIBER", worker)
    seen = []
    result, languages = speech.transcribe_video("vid", lambda stage, f: seen.append((stage, f)))
    assert seen == [("audio", 0.5), ("model", 1.0), ("transcribe", 0.25)]
    assert result[0].text == "வணக்கம் everyone" and languages == ["ta", "en"]


def test_speech_reports_the_workers_error(monkeypatch, tmp_path):
    worker = fake_worker(tmp_path, 'print(json.dumps({"event": "error", "message": "No speech was found"}))\nsys.exit(1)\n')
    monkeypatch.setattr(config, "TRANSCRIBER", worker)
    with pytest.raises(speech.SpeechError, match="No speech was found"):
        speech.transcribe_video("vid", lambda *a: None)


def test_speech_reports_a_crashed_worker(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "TRANSCRIBER", fake_worker(tmp_path, "sys.exit(9)\n"))
    with pytest.raises(speech.SpeechError, match="exit code 9"):
        speech.transcribe_video("vid", lambda *a: None)


# --- Inside the worker ------------------------------------------------------------------------


def test_audio_download_uses_bundled_deno_and_reports_progress(monkeypatch, tmp_path, capsys):
    captured = {}

    class FakeYDL:
        def __init__(self, opts):
            captured.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download):
            captured["url"] = url
            for hook in captured["progress_hooks"]:
                hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
            (tmp_path / "audio.m4a").write_bytes(b"x")
            return {"ext": "m4a"}

        def prepare_filename(self, info):
            return str(tmp_path / "audio.m4a")

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)
    monkeypatch.setattr(transcribe, "deno_path", lambda: "/opt/deno")
    path = transcribe.download_audio("abcdefghijk", tmp_path)

    assert path.name == "audio.m4a"
    assert captured["url"].endswith("v=abcdefghijk")
    assert captured["js_runtimes"] == {"deno": {"path": "/opt/deno"}}
    assert "bestaudio" in captured["format"]
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert {"event": "progress", "stage": "audio", "fraction": 0.5} in events


def test_audio_download_errors_are_readable(monkeypatch, tmp_path):
    from yt_dlp.utils import DownloadError

    class FailingYDL:
        def __init__(self, opts): ...
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download):
            raise DownloadError("ERROR: [youtube] abc: Private video. Sign in if you've been granted access")

    monkeypatch.setattr("yt_dlp.YoutubeDL", FailingYDL)
    with pytest.raises(transcribe.TranscribeError, match="^Couldn't download the lecture's audio: \\[youtube\\] abc: Private video"):
        transcribe.download_audio("abc", tmp_path)


def test_language_sampling_finds_every_language_spoken():
    # Speech alternates: 0-60 s Hindi, 60-120 s English, with a long silence in the middle.
    class FakeModel:
        def detect_language(self, chunk):
            first = chunk[0]
            return ("hi" if first < 1 else "en"), 0.9, []

    sr = transcribe.SAMPLE_RATE
    import numpy as np

    audio = np.concatenate([np.zeros(60 * sr), np.full(300 * sr, 5.0), np.full(60 * sr, 2.0)])
    spans = [(0.0, 60.0), (360.0, 420.0)]  # the 300 s in between is silence, never sampled
    assert transcribe._languages(FakeModel(), audio, spans) == ["hi", "en"] or transcribe._languages(
        FakeModel(), audio, spans
    ) == ["en", "hi"]
    assert transcribe._languages(FakeModel(), audio, []) == []


def test_worker_cli_emits_result(monkeypatch, capsys, tmp_path):
    audio = tmp_path / "talk.m4a"
    audio.write_bytes(b"x")
    monkeypatch.setattr(
        transcribe, "transcribe", lambda path, model, models_dir, threads: ([{"start": 0, "duration": 1, "text": "hola"}], ["es"])
    )
    transcribe.main(["--audio", str(audio), "--model", "tiny"])
    out = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert out == {"event": "result", "snippets": [{"start": 0, "duration": 1, "text": "hola"}], "languages": ["es"]}


def test_worker_cli_reports_errors(monkeypatch, capsys):
    def fail(video_id, workdir):
        raise transcribe.TranscribeError("Couldn't download the lecture's audio: blocked")

    monkeypatch.setattr(transcribe, "download_audio", fail)
    with pytest.raises(SystemExit):
        transcribe.main(["--video-id", "abc"])
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["message"].endswith("blocked")


def test_audio_error_messages_drop_yt_dlp_boilerplate():
    raw = (
        "ERROR: [youtube] abc: Unable to download API page: ('Unable to connect to proxy', OSError('403')) "
        '(caused by ProxyError("...")); please report this issue on  https://github.com/yt-dlp/yt-dlp/issues'
    )
    assert transcribe._readable(raw) == "[youtube] abc: Unable to download API page: ('Unable to connect to proxy', OSError('403'))"


@pytest.mark.parametrize(
    "languages, script",
    [
        (["hi"], "\u0900"),  # Devanagari block
        (["en", "hi"], "\u0900"),  # Hinglish where English dominates still gets Devanagari
        (["zh"], "简"),
        (["ur", "hi"], None),  # Urdu speakers keep Urdu script
        (["es", "fr"], None),
        ([], None),
    ],
)
def test_script_hint_steers_whisper_to_the_expected_script(languages, script):
    hint = transcribe.script_hint(languages)
    if script is None:
        assert hint is None
    elif script == "\u0900":
        assert any("\u0900" <= ch <= "\u097f" for ch in hint)
    else:
        assert script in hint
