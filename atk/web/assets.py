"""Load local web assets bundled with the desktop application."""
from __future__ import annotations

from pathlib import Path


STATIC_DIR = Path(__file__).with_name("static")


def load_asset(name: str) -> str:
    """Return a UTF-8 static asset by name from the packaged web directory."""
    return (STATIC_DIR / name).read_text(encoding="utf-8")
