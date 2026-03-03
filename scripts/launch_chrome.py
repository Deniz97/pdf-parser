#!/usr/bin/env python3
"""Launch Chrome with remote debugging and PDF auto-download prefs.

Use when you need Chrome with always_open_pdf_externally for manual testing
or with other scripts that attach to the debugger.

Usage:
  uv run python scripts/launch_chrome.py
  make launch-chrome

Quit all Chrome windows first, then run this. Chrome will start with PDF
auto-download enabled. Navigate to your target URL manually.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 9222
DEFAULT_DOWNLOAD_DIR = "outputs/pdf_download_tests"
DEFAULT_USER_DATA_DIR = ".chrome-debug-profile"


def _find_chrome_executable() -> str:
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
            os.path.expandvars(
                r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
            ),
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
    raise FileNotFoundError("Chrome executable not found.")


def _write_pdf_download_prefs(user_data_dir: str, download_dir: str) -> None:
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
    logging.getLogger(__name__).info("Wrote PDF auto-download prefs to %s", prefs_path)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger = logging.getLogger(__name__)

    dir_path = os.path.abspath(str(REPO_ROOT / DEFAULT_DOWNLOAD_DIR))
    os.makedirs(dir_path, exist_ok=True)

    ud = os.path.abspath(str(REPO_ROOT / DEFAULT_USER_DATA_DIR))
    _write_pdf_download_prefs(ud, dir_path)

    chrome = _find_chrome_executable()
    cmd = [
        chrome,
        f"--remote-debugging-port={DEFAULT_PORT}",
        f"--user-data-dir={ud}",
        "--no-first-run",
    ]
    logger.info("Launching Chrome: %s", " ".join(cmd))
    logger.info("Download dir: %s | User data dir: %s", dir_path, ud)
    print("\n*** QUIT ALL Chrome windows first ***\n")
    subprocess.Popen(cmd, start_new_session=True)  # noqa: S603
    print(
        f"\nChrome launched with PDF auto-download. Download dir: {dir_path}\n"
        "Navigate to your target URL manually.\n"
    )


if __name__ == "__main__":
    main()
