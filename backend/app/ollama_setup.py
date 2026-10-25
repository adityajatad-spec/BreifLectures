"""Helping the user get a local model running: detect Ollama, start it, download a model."""

import logging
import platform
import shutil
import subprocess
import threading
from pathlib import Path

import ollama
from pydantic import BaseModel

from . import analyze_ollama, config

log = logging.getLogger(__name__)

# Sizes are approximate (Ollama's default Q4 builds); RAM includes an 8k context.
RECOMMENDED = [
    {"name": "qwen3.5:4b", "download_gb": 3.4, "ram_gb": 4.5, "note": "Recommended for 16 GB Macs"},
    {"name": "qwen3:4b", "download_gb": 2.5, "ram_gb": 4.0, "note": "Lighter, very widely supported"},
    {"name": "llama3.2:3b", "download_gb": 2.0, "ram_gb": 3.0, "note": "For 8 GB Macs; rougher labels"},
    {"name": "qwen3:8b", "download_gb": 5.2, "ram_gb": 6.5, "note": "Better labels; 24 GB+ Macs only"},
]

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"
_MAC_APP = Path("/Applications/Ollama.app")


class PullState(BaseModel):
    model: str = ""
    status: str = "idle"  # idle | running | done | error
    detail: str = ""
    completed: int = 0
    total: int = 0
    error: str | None = None


_pull = PullState()
_pull_lock = threading.Lock()


def pulled_models() -> list[str] | None:
    """Model names Ollama has locally, or None if Ollama isn't reachable."""
    try:
        return sorted(m.model for m in analyze_ollama.client().list().models if m.model)
    except (ConnectionError, ollama.ResponseError):
        return None


def ollama_state(models: list[str] | None) -> str:
    if models is not None:
        return "running"
    if _MAC_APP.exists() or shutil.which("ollama"):
        return "stopped"
    return "missing"


def start_ollama() -> None:
    if platform.system() == "Darwin" and _MAC_APP.exists():
        subprocess.Popen(["open", "-a", "Ollama"])
    elif exe := shutil.which("ollama"):
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    else:
        raise RuntimeError("Ollama is not installed.")


def pull_state() -> PullState:
    return _pull.model_copy()


def start_pull(model: str) -> PullState:
    global _pull
    with _pull_lock:
        if _pull.status == "running":
            return _pull.model_copy()
        _pull = PullState(model=model, status="running", detail="Starting download")
    threading.Thread(target=_run_pull, args=(_pull,), daemon=True).start()
    return _pull.model_copy()


def _run_pull(state: PullState) -> None:
    # A model arrives as several blobs (weights, projector, template, ...), each reporting its
    # own progress; the overall figure is the sum over every blob seen so far.
    blobs: dict[str, tuple[int, int]] = {}
    try:
        for progress in analyze_ollama.client().pull(state.model, stream=True):
            state.detail = progress.status or ""
            if progress.digest and progress.total:
                blobs[progress.digest] = (progress.completed or 0, progress.total)
                state.completed = sum(done for done, _ in blobs.values())
                state.total = sum(total for _, total in blobs.values())
        state.status, state.detail = "done", "Downloaded"
    except ConnectionError:
        state.status, state.error = "error", f"Ollama isn't running at {config.OLLAMA_HOST}."
    except ollama.ResponseError as exc:
        state.status, state.error = "error", exc.error
    except Exception as exc:  # network drops mid-download, disk full, ...
        log.exception("Model pull failed")
        state.status, state.error = "error", str(exc)
