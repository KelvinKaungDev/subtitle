"""Paths and user settings. Everything else imports from here."""
import json
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT / "jobs"
FONTS_DIR = ROOT / "fonts"

load_dotenv(ROOT / ".env")   # so it works no matter where the app is started


def load_settings() -> dict:
    return json.loads((ROOT / "settings.json").read_text())
