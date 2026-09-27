# config.py - one place for version, settings and log setup
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Single source of truth: /health, the git tag and the image tag all use this.
VERSION = "1.1.0"

APP_ENV = os.getenv("APP_ENV", "development")
TRIAGE_BACKEND = os.getenv("TRIAGE_BACKEND", "openai")   # openai | stub
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LOG_DIR = Path(os.getenv("LOG_DIR", Path(__file__).parent / "logs"))

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def get_logger(name: str, filename: str) -> logging.Logger:
    """A logger that writes to logs/<filename> and to stderr (never stdout:
    the MCP server's stdout is the protocol channel)."""
    log = logging.getLogger(name)
    if log.handlers:
        return log
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT)
    for handler in (logging.FileHandler(LOG_DIR / filename, encoding="utf-8"),
                    logging.StreamHandler()):
        handler.setFormatter(formatter)
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
    return log
