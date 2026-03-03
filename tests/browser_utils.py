"""Shared run/attach infrastructure for integration flow tests."""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
DEFAULT_URL = "https://staging.squadhealth.ai/interview"
DEFAULT_PORT = 9222
DEFAULT_DOWNLOAD_DIR = str(REPO_ROOT / "outputs" / "flow_tests")
DEFAULT_USER_DATA_DIR = str(REPO_ROOT / ".chrome-debug-profile")

logger = logging.getLogger(__name__)


def _extract_result(cdp_response: dict) -> dict | list | str | None:
    try:
        inner = cdp_response.get("result", {})
        if "result" in inner:
            inner = inner["result"]
        if "value" in inner:
            return inner["value"]
        return inner
    except Exception:
        return None


class _CdpAdapter:
    """CDP adapter for raw WebDriver (attach mode)."""

    def __init__(self, driver: webdriver.Chrome) -> None:
        self._driver = driver

    def evaluate(self, expression: str) -> dict | list | str | None:
        resp = self._driver.execute_cdp_cmd(
            "Runtime.evaluate",
            {"expression": expression.strip(), "returnByValue": True},
        )
        return _extract_result(resp)

    def get_title(self) -> str:
        return self._driver.title or ""

    def save_screenshot(self, path: str) -> None:
        self._driver.save_screenshot(path)
        logger.info("Screenshot saved: %s", path)

    def wait_for_element(self, selector: str, timeout: int = 5) -> None:
        by, value = _selector_to_by(selector)
        WebDriverWait(self._driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )

    def click(self, selector: str) -> None:
        by, value = _selector_to_by(selector)
        el = WebDriverWait(self._driver, 10).until(
            EC.element_to_be_clickable((by, value))
        )
        el.click()


def _selector_to_by(selector: str) -> tuple[By, str]:
    """Convert SeleniumBase-style selector to (By, value)."""
    if ":contains(" in selector:
        # button:contains("Submit") -> XPath
        import re
        m = re.match(r"(\w+):contains\(\"([^\"]+)\"\)", selector)
        if m:
            tag, text = m.groups()
            return By.XPATH, f"//{tag}[contains(text(),'{text}')]"
    # CSS
    return By.CSS_SELECTOR, selector


class SbAdapter:
    """Minimal SB-like adapter for browser functions when attaching to Chrome."""

    def __init__(self, driver: webdriver.Chrome) -> None:
        self.driver = driver
        self.cdp = _CdpAdapter(driver)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def activate_cdp_mode(self, url: str) -> None:
        """Navigate to url (attach mode: we already have CDP via debugger)."""
        logger.info("Navigating to %s", url)
        self.driver.get(url)
        self.sleep(3)


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
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
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
    logger.info("Wrote PDF auto-download prefs to %s", prefs_path)


def launch_chrome(
    port: int = DEFAULT_PORT,
    download_dir: str | None = None,
    user_data_dir: str | None = None,
    chrome_path: str | None = None,
) -> None:
    """Launch Chrome with remote debugging and PDF auto-download prefs."""
    dir_path = download_dir or DEFAULT_DOWNLOAD_DIR
    dir_path = os.path.abspath(dir_path)
    os.makedirs(dir_path, exist_ok=True)

    ud = os.path.abspath(user_data_dir or DEFAULT_USER_DATA_DIR)
    _write_pdf_download_prefs(ud, dir_path)

    chrome = chrome_path or _find_chrome_executable()
    cmd = [
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={ud}",
        "--no-first-run",
    ]
    logger.info("Launching Chrome: %s", " ".join(cmd))
    logger.info("Download dir: %s | User data dir: %s", dir_path, ud)
    print("\n*** QUIT ALL Chrome windows first ***\n")
    subprocess.Popen(cmd, start_new_session=True)  # noqa: S603
    print(f"\nChrome launched. Download dir: {dir_path}\n")


def connect(port: int = DEFAULT_PORT) -> tuple[webdriver.Chrome, SbAdapter]:
    """Connect to existing Chrome via debuggerAddress. Raises on failure."""
    opts = Options()
    opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")

    logger.info("Connecting to Chrome on port %d...", port)
    driver = webdriver.Chrome(options=opts)
    sb = SbAdapter(driver)
    return driver, sb
