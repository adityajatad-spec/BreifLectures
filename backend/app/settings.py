"""Settings the user can change from the app, persisted next to the cache. Env vars give the defaults."""

import json
import logging

from pydantic import BaseModel

from . import config

log = logging.getLogger(__name__)


class Settings(BaseModel):
    model: str
    think: bool
    # Defaults keep settings files saved by older versions loading.
    whisper_model: str = "small"
    output_language: str = "English"


def current() -> Settings:
    return Settings(
        model=config.OLLAMA_MODEL,
        think=config.OLLAMA_THINK,
        whisper_model=config.WHISPER_MODEL,
        output_language=config.OUTPUT_LANGUAGE,
    )


def _apply(s: Settings) -> None:
    config.OLLAMA_MODEL, config.OLLAMA_THINK = s.model.strip(), s.think
    config.WHISPER_MODEL = s.whisper_model.strip() or "small"
    config.OUTPUT_LANGUAGE = s.output_language.strip() or "English"


def load() -> None:
    try:
        saved = Settings.model_validate_json(config.SETTINGS_FILE.read_text())
    except FileNotFoundError:
        return
    except ValueError:
        log.warning("Ignoring unreadable %s", config.SETTINGS_FILE)
        return
    _apply(saved)


def save(new: Settings) -> Settings:
    _apply(new)
    config.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.SETTINGS_FILE.write_text(json.dumps(current().model_dump(), indent=2))
    return current()
