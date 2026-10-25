"""Settings the user can change from the app, persisted next to the cache. Env vars give the defaults."""

import json
import logging

from pydantic import BaseModel

from . import config

log = logging.getLogger(__name__)


class Settings(BaseModel):
    model: str
    think: bool


def current() -> Settings:
    return Settings(model=config.OLLAMA_MODEL, think=config.OLLAMA_THINK)


def load() -> None:
    try:
        saved = Settings.model_validate_json(config.SETTINGS_FILE.read_text())
    except FileNotFoundError:
        return
    except ValueError:
        log.warning("Ignoring unreadable %s", config.SETTINGS_FILE)
        return
    config.OLLAMA_MODEL, config.OLLAMA_THINK = saved.model, saved.think


def save(new: Settings) -> Settings:
    config.OLLAMA_MODEL, config.OLLAMA_THINK = new.model.strip(), new.think
    config.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.SETTINGS_FILE.write_text(json.dumps(current().model_dump(), indent=2))
    return current()
