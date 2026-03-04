"""Chrome-related utilities: executable lookup and PDF download preferences."""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def find_chrome_executable() -> str:
    """Return path to Chrome executable. Raises FileNotFoundError if not found."""
    if platform.system() == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
    elif platform.system() == "Linux":
        for name in (
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
        ):
            path = shutil.which(name)
            if path:
                return path
    elif platform.system() == "Windows":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
    raise FileNotFoundError("Chrome executable not found")


def write_pdf_download_prefs(user_data_dir: str, download_dir: str) -> None:
    """Write Chrome Preferences to enable PDF auto-download (always_open_pdf_externally)."""
    default_dir = Path(user_data_dir) / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)
    prefs_path = default_dir / "Preferences"

    prefs: dict = {}
    if prefs_path.exists():
        try:
            prefs = json.loads(prefs_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    prefs.setdefault("plugins", {})["always_open_pdf_externally"] = True
    prefs.setdefault("download", {}).update(
        {
            "prompt_for_download": False,
            "default_directory": os.path.abspath(download_dir),
            "directory_upgrade": True,
        }
    )

    prefs_path.write_text(json.dumps(prefs, indent=2))
    logger.info("Wrote PDF auto-download prefs to %s", prefs_path)
