"""Speech-to-text for lectures that have no captions, in any language or mix of languages.

Runs as its own process (the `brief-transcribe` binary in the app, `python -m app.transcribe`
in development) so its libraries never load into the engine, and all the memory Whisper used
goes back to the user the moment it exits. app/speech.py starts it and reads its output.

Protocol: one JSON object per line on stdout.
    {"event": "progress", "stage": "audio" | "model" | "transcribe", "fraction": 0.42}
    {"event": "result", "snippets": [...], "languages": ["hi", "en"]}
    {"event": "error", "message": "..."}
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from collections import Counter
from pathlib import Path

# Approximate download sizes, for the progress bar while a model downloads (first use only).
MODEL_SIZES_MB = {"tiny": 75, "base": 145, "small": 484, "medium": 1530, "large-v3-turbo": 1620}
SAMPLE_RATE = 16000
LANGUAGE_SAMPLES = 8  # points across the lecture where we check which language is spoken


def emit(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def progress(stage: str, fraction: float) -> None:
    emit("progress", stage=stage, fraction=round(max(0.0, min(1.0, fraction)), 3))


class TranscribeError(Exception):
    pass


# --- Audio -------------------------------------------------------------------------------


def deno_path() -> str | None:
    """yt-dlp needs a JavaScript runtime for YouTube. The app bundles Deno next to this code."""
    bundled = Path(getattr(sys, "_MEIPASS", "")) / "bin" / "deno"
    if getattr(sys, "_MEIPASS", None) and bundled.exists():
        return str(bundled)
    try:
        import deno

        return deno.find_deno_bin()
    except (ImportError, FileNotFoundError):
        return shutil.which("deno")


def download_audio(video_id: str, workdir: Path) -> Path:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    def hook(d: dict) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                progress("audio", d.get("downloaded_bytes", 0) / total)

    opts = {
        # Audio only: a fraction of the video's size, and PyAV decodes it without ffmpeg.
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(workdir / "audio.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
    }
    if deno := deno_path():
        opts["js_runtimes"] = {"deno": {"path": deno}}
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            path = Path(ydl.prepare_filename(info))
    except DownloadError as exc:
        raise TranscribeError(f"Couldn't download the lecture's audio: {_readable(str(exc))}") from exc
    if not path.exists():  # some formats get renamed after download
        candidates = sorted(workdir.glob("audio.*"))
        if not candidates:
            raise TranscribeError("Couldn't download the lecture's audio.")
        path = candidates[0]
    progress("audio", 1.0)
    return path


def _readable(message: str) -> str:
    """yt-dlp's message without its bug-report boilerplate and exception internals."""
    text = message.replace("ERROR: ", "").splitlines()[0]
    text = re.split(r";\s*please report this issue", text)[0]
    text = re.sub(r"\s*\(caused by .*$", "", text)
    return text.strip()


# --- Model -------------------------------------------------------------------------------


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def ensure_model(name: str, models_dir: Path) -> Path:
    """Downloads the model on first use, reporting progress by watching the folder grow."""
    target = models_dir / name
    if (target / "model.bin").exists():
        return target
    from faster_whisper.utils import download_model

    expected = MODEL_SIZES_MB.get(name, 500) * 1_000_000
    done = threading.Event()

    def watch() -> None:
        while not done.wait(1.0):
            if target.exists():
                progress("model", min(0.99, _dir_size(target) / expected))

    threading.Thread(target=watch, daemon=True).start()
    try:
        download_model(name, output_dir=str(target))
    except Exception as exc:
        raise TranscribeError(f"Couldn't download the speech model '{name}': {exc}") from exc
    finally:
        done.set()
    progress("model", 1.0)
    return target


# --- Transcription -----------------------------------------------------------------------


def _languages(model, audio, speech_spans: list[tuple[float, float]]) -> list[str]:
    """Which languages the lecture uses, most-spoken first, sampled across its speech."""
    if not speech_spans:
        return []
    window = 30 * SAMPLE_RATE
    total = sum(end - start for start, end in speech_spans)
    counts: Counter[str] = Counter()
    for i in range(LANGUAGE_SAMPLES):
        # Walk to the i-th evenly spaced point in the speech, skipping the silences.
        at = total * (i + 0.5) / LANGUAGE_SAMPLES
        pos = int(speech_spans[-1][0] * SAMPLE_RATE)
        for start, end in speech_spans:
            if at <= end - start:
                pos = int((start + at) * SAMPLE_RATE)
                break
            at -= end - start
        chunk = audio[pos : pos + window]
        if len(chunk) < SAMPLE_RATE:
            continue
        language, probability, _ = model.detect_language(chunk)
        if probability >= 0.5:
            counts[language] += 1
    return [lang for lang, _ in counts.most_common()]


# Whisper sometimes writes a language in the wrong script: spoken Hindi and Urdu sound
# alike, so Hindi often comes out in Urdu script, and Mandarin in Traditional characters.
# A short phrase in the expected script, passed as "hotwords" (repeated for every 30 s
# window, unlike initial_prompt), steers it. The Hindi one mixes in English the way
# lectures do, so English words in Hinglish stay in Latin letters.
SCRIPT_HINTS = {
    "hi": "नमस्ते दोस्तों, आज का topic है derivatives। चलिए शुरू करते हैं।",
    "zh": "以下是普通话的句子，使用简体中文。",
}


def script_hint(languages: list[str]) -> str | None:
    """The hint for the most-spoken language that needs one. Urdu speech keeps its own script."""
    for lang in languages:
        if lang == "ur":
            return None
        if lang in SCRIPT_HINTS:
            return SCRIPT_HINTS[lang]
    return None


def transcribe(audio_path: Path, model_name: str, models_dir: Path, threads: int) -> tuple[list[dict], list[str]]:
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import get_speech_timestamps

    model_path = ensure_model(model_name, models_dir)
    model = WhisperModel(str(model_path), device="cpu", compute_type="int8", cpu_threads=threads)
    audio = decode_audio(str(audio_path), sampling_rate=SAMPLE_RATE)

    speech = [(s["start"] / SAMPLE_RATE, s["end"] / SAMPLE_RATE) for s in get_speech_timestamps(audio)]
    if not speech:
        raise TranscribeError("No speech was found in this lecture's audio.")
    # Languages first: they decide the script hint, and the UI shows them.
    languages = _languages(model, audio, speech)

    # multilingual: detect the language again for every 30 s of audio, so a lecture that
    # switches between, say, Hindi and English is transcribed in whichever is being spoken.
    segments, info = model.transcribe(
        audio,
        multilingual=True,
        vad_filter=True,
        beam_size=1,
        condition_on_previous_text=False,  # stops one misheard phrase from repeating for minutes
        hotwords=script_hint(languages),
    )
    snippets: list[dict] = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            snippets.append({"start": seg.start, "duration": max(0.0, seg.end - seg.start), "text": text})
        if info.duration:
            progress("transcribe", seg.end / info.duration)
    if not snippets:
        raise TranscribeError("No speech was found in this lecture's audio.")
    progress("transcribe", 1.0)
    return snippets, languages or [info.language]


# --- Self-test (run by the release build to check the packaged binary) ------------------


def _tone(path: Path, codec: str, container: str, rate: int) -> None:
    """Three seconds of tone, encoded the way YouTube serves audio."""
    import math

    import av
    import numpy as np

    with av.open(str(path), "w", format=container) as out:
        stream = out.add_stream(codec, rate=rate)
        stream.layout = "stereo"
        wave = (0.3 * np.sin(2 * math.pi * 440 * np.arange(rate * 3) / rate)).astype("float32")
        frame = av.AudioFrame.from_ndarray(np.stack([wave, wave]), format="fltp", layout="stereo")
        frame.sample_rate = rate
        for packet in [*stream.encode(frame), *stream.encode(None)]:
            out.mux(packet)


def self_test() -> None:
    """Checks the packaged binary: libraries, bundled Deno, audio codecs, voice detection."""
    import subprocess

    import ctranslate2  # noqa: F401  (Whisper's inference engine)
    import yt_dlp_ejs  # noqa: F401  (YouTube's JS challenge solver for yt-dlp)
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import get_speech_timestamps

    deno = deno_path()
    if not deno:
        raise TranscribeError("Deno is missing")
    version = subprocess.run([deno, "--version"], capture_output=True, text=True, check=True).stdout.split("\n")[0]

    decoded = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, codec, container, rate in [("m4a", "aac", "mp4", 44100), ("webm", "libopus", "webm", 48000)]:
            path = Path(tmp) / f"tone.{name}"
            _tone(path, codec, container, rate)
            audio = decode_audio(str(path), sampling_rate=SAMPLE_RATE)
            if not 2.5 * SAMPLE_RATE < len(audio) < 3.5 * SAMPLE_RATE:
                raise TranscribeError(f"Decoding {name} gave {len(audio)} samples")
            decoded[name] = len(audio)
        get_speech_timestamps(audio)  # loads and runs the bundled voice-activity model
    emit("self-test", ok=True, deno=version, decoded=decoded)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="brief-transcribe")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video-id")
    source.add_argument("--audio", help="transcribe a local audio file instead")
    source.add_argument("--self-test", action="store_true")
    parser.add_argument("--model", default="small")
    parser.add_argument("--models-dir", default=str(Path.home() / ".cache" / "brieflectures" / "whisper"))
    parser.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    args = parser.parse_args(argv)

    try:
        if args.self_test:
            self_test()
            return
        with tempfile.TemporaryDirectory(prefix="brieflectures-") as tmp:
            audio = Path(args.audio) if args.audio else download_audio(args.video_id, Path(tmp))
            snippets, languages = transcribe(audio, args.model, Path(args.models_dir), args.threads)
        emit("result", snippets=snippets, languages=languages)
    except TranscribeError as exc:
        emit("error", message=str(exc))
        sys.exit(1)
    except Exception as exc:  # report anything unexpected in a form the engine can show
        emit("error", message=f"Speech-to-text failed: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
