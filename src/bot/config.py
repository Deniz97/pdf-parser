"""Shared constants for bot, tests, and scripts."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

NUM_STEPS = 3
DEFAULT_PORT = 9222
DEFAULT_URL = "https://staging.squadhealth.ai/interview"
DEFAULT_DOWNLOAD_DIR = str(REPO_ROOT / "outputs" / "downloads")
DEFAULT_USER_DATA_DIR = str(REPO_ROOT / ".chrome-debug-profile")
