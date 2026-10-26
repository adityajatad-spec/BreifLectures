"""Runs the speech-to-text worker (app/transcribe.py) for lectures without captions."""

import json
import logging
import subprocess
import sys
from collections.abc import Callable

from . import config
from .models import Snippet

log = logging.getLogger(__name__)

# Shown in Settings. Every model handles ~99 languages and mixed-language speech; bigger ones
# are more accurate, especially for less common languages, and slower.
MODELS = [
    {"name": "small", "download_mb": 484, "ram_gb": 1.0, "note": "Recommended: good for most languages"},
    {"name": "medium", "download_mb": 1530, "ram_gb": 2.0, "note": "More accurate for less common languages; about 3× slower"},
    {"name": "large-v3-turbo", "download_mb": 1620, "ram_gb": 2.5, "note": "Most accurate, best with mixed languages; slowest"},
]


class SpeechError(Exception):
    pass


def _command() -> list[str]:
    if config.TRANSCRIBER:
        return [config.TRANSCRIBER]
    if getattr(sys, "frozen", False):
        raise SpeechError("Speech-to-text isn't included in this build.")
    return [sys.executable, "-m", "app.transcribe"]


def transcribe_video(
    video_id: str, on_progress: Callable[[str, float], None]
) -> tuple[list[Snippet], list[str]]:
    cmd = _command() + [
        "--video-id", video_id,
        "--model", config.WHISPER_MODEL,
        "--models-dir", str(config.WHISPER_DIR),
    ]  # fmt: skip
    log.info("Transcribing %s with Whisper %s", video_id, config.WHISPER_MODEL)
    result: dict | None = None
    error: str | None = None
    # stderr is inherited, so library warnings land in the engine's log.
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8") as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                log.info("transcriber: %s", line.rstrip())
                continue
            if event.get("event") == "progress":
                on_progress(event["stage"], event["fraction"])
            elif event.get("event") == "result":
                result = event
            elif event.get("event") == "error":
                error = event.get("message")
    if result is None:
        raise SpeechError(error or f"Speech-to-text stopped unexpectedly (exit code {proc.returncode}).")
    snippets = [Snippet(**s) for s in result["snippets"]]
    return snippets, result.get("languages", [])
