import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("BRIEF_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
CACHE_DB = DATA_DIR / "cache.sqlite3"

# "auto" uses Claude when credentials are configured, otherwise the offline heuristic.
ANALYZER = os.environ.get("BRIEF_ANALYZER", "auto")  # auto | claude | heuristic
CLAUDE_MODEL = os.environ.get("BRIEF_CLAUDE_MODEL", "claude-opus-5-5")

TRANSCRIPT_LANGUAGES = [
    lang.strip() for lang in os.environ.get("BRIEF_LANGUAGES", "en,en-US,en-GB").split(",") if lang.strip()
]

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "BRIEF_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,tauri://localhost"
    ).split(",")
    if origin.strip()
]
