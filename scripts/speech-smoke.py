#!/usr/bin/env python3
"""End-to-end check of the packaged speech-to-text worker, run on the macOS release build.

macOS's `say` speaks a short lecture-style passage in several languages (and one mixed
Hindi/English passage). The packaged brief-transcribe binary must turn each into text and
recognize the language. Spanish must pass; other languages depend on which voices the
machine has, so a mismatch there is reported as a warning rather than failing the build.

Usage: speech-smoke.py <path-to-brief-transcribe> [model]
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PASSAGES = [
    # locale prefix, expected language, required?, text
    ("es_", "es", True, "Hoy vamos a estudiar las derivadas. Una derivada mide la tasa de cambio de una función."),
    ("fr_", "fr", False, "Aujourd'hui nous allons étudier les dérivées. Une dérivée mesure le taux de variation."),
    ("de_", "de", False, "Heute lernen wir Ableitungen. Eine Ableitung misst die Änderungsrate einer Funktion."),
    ("hi_", "hi", False, "आज हम अवकलज के बारे में पढ़ेंगे। अवकलज किसी फलन के परिवर्तन की दर को मापता है।"),
    ("ja_", "ja", False, "今日は微分について勉強します。微分は関数の変化の割合を表します。"),
    ("zh_", "zh", False, "今天我们学习导数。导数表示函数的变化率。"),
    # Mixed: a Hindi voice reading Hinglish. Either language is a correct answer.
    ("hi_", "hi|en", False, "Toh aaj ka topic hai derivatives. Derivative matlab rate of change, samjhe?"),
]


# Some languages must also come out in the right script (Whisper can write Hindi in Urdu
# script, or Mandarin in Traditional characters).
SCRIPTS = {
    "hi": ("Devanagari", lambda t: any("\u0900" <= ch <= "\u097f" for ch in t)),
    "zh": ("Simplified Chinese", lambda t: sum(ch in "们学习导数表示变" for ch in t) > sum(ch in "們學習導數錶示變" for ch in t)),
}


def voices() -> dict[str, str]:
    """First installed voice for each locale, e.g. {"es_ES": "Mónica"}."""
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True).stdout
    found: dict[str, str] = {}
    for line in out.splitlines():
        m = re.match(r"^(.+?)\s+([a-z]{2}_[A-Z]{2})\s+#", line)
        if m:
            found.setdefault(m.group(2), m.group(1).strip())
    return found


def transcribe(binary: str, audio: Path, model: str, models_dir: str) -> dict:
    proc = subprocess.run(
        [binary, "--audio", str(audio), "--model", model, "--models-dir", models_dir],
        capture_output=True, text=True, timeout=900,
    )  # fmt: skip
    events = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    for event in events:
        if event["event"] == "result":
            return event
        if event["event"] == "error":
            raise RuntimeError(event["message"])
    raise RuntimeError(f"no result (exit {proc.returncode}): {proc.stderr[-2000:]}")


def main() -> int:
    binary = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "small"
    available = voices()
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for prefix, expected, required, text in PASSAGES:
            voice = next((v for loc, v in available.items() if loc.startswith(prefix)), None)
            if not voice:
                print(f"::notice::No {prefix}* voice installed; skipping {expected}")
                failures += required
                continue
            audio = Path(tmp) / f"{prefix}{len(expected)}.aiff"
            subprocess.run(["say", "-v", voice, "-o", str(audio), text], check=True)
            try:
                result = transcribe(binary, audio, model, str(Path(tmp) / "models"))
            except Exception as exc:  # report every language, then decide
                print(f"::error::{expected} ({voice}): {exc}")
                failures += 1
                continue
            heard = " ".join(s["text"] for s in result["snippets"])
            ok = bool(heard.strip()) and result["languages"][:1] and re.fullmatch(expected, result["languages"][0])
            script = SCRIPTS.get(expected.split("|")[0])
            if script and not script[1](heard):
                ok = False
                heard = f"[not {script[0]}] {heard}"
            line = f"{expected:5} {voice:12} detected={result['languages']} text={heard[:80]!r}"
            if ok:
                print(f"PASS  {line}")
            elif required:
                print(f"::error::FAIL {line}")
                failures += 1
            else:
                print(f"::warning::MISMATCH {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
