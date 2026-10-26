import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("BRIEF_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
CACHE_DB = DATA_DIR / "cache.sqlite3"
SETTINGS_FILE = DATA_DIR / "settings.json"

# The desktop app points this at the bundled web build, so UI and API share one origin.
STATIC_DIR = os.environ.get("BRIEF_STATIC_DIR") or None

# "auto" uses the local model when Ollama is running and the model is pulled, otherwise the heuristic.
ANALYZER = os.environ.get("BRIEF_ANALYZER", "auto")  # auto | ollama | heuristic

# Sized for a 16 GB machine: ~3.4 GB of weights plus ~1 GB of context stays inside a 5-6 GB budget.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("BRIEF_OLLAMA_MODEL", "qwen3.5:4b")
OLLAMA_CTX = int(os.environ.get("BRIEF_OLLAMA_CTX", "8192"))
OLLAMA_THINK = os.environ.get("BRIEF_OLLAMA_THINK", "0") == "1"  # better labels, several times slower
# Unload the model soon after a job so the RAM goes back to the user.
OLLAMA_KEEP_ALIVE = os.environ.get("BRIEF_OLLAMA_KEEP_ALIVE", "2m")

# Lectures without captions are transcribed locally with Whisper (any language, or a mix).
# The desktop app points TRANSCRIBER at its bundled brief-transcribe binary.
TRANSCRIBER = os.environ.get("BRIEF_TRANSCRIBER") or None
WHISPER_MODEL = os.environ.get("BRIEF_WHISPER_MODEL", "small")
WHISPER_DIR = DATA_DIR / "whisper"

# Language for topics, chapter titles and summaries: a language name, or "auto" to use the
# lecture's own (main) language.
OUTPUT_LANGUAGE = os.environ.get("BRIEF_OUTPUT_LANGUAGE", "English")

# Captions in these languages are preferred when a video has several; otherwise any are used.
TRANSCRIPT_LANGUAGES = [
    lang.strip() for lang in os.environ.get("BRIEF_LANGUAGES", "en,en-US,en-GB").split(",") if lang.strip()
]

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "BRIEF_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]
