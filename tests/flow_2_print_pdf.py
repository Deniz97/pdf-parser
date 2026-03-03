#!/usr/bin/env python3
"""Flow 2: Print PDF via iframe button.

Run:  Launch Chrome, open URL, pass Cloudflare, click Print PDF, wait for PDF.
Attach: Connect to existing Chrome (already past Cloudflare), click Print PDF, wait for PDF.

Usage:
  make flow-2              # Run with fresh Chrome
  make flow-2-attach       # Attach (Chrome must be running, already on form page)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo_root / "src"))
sys.path.insert(0, str(_repo_root))

from seleniumbase import SB

from bot import browser
from tests.browser_utils import (
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_PORT,
    DEFAULT_URL,
    REPO_ROOT,
    connect,
    _write_pdf_download_prefs,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT = 30
IFRAME_TIMEOUT = 10


def run_with_sb(url: str, download_dir: str) -> int:
    """Run with SeleniumBase (fresh Chrome, full flow from start)."""
    user_data_dir = str(REPO_ROOT / "user_data")
    _write_pdf_download_prefs(user_data_dir, download_dir)

    with SB(
        uc=True,
        headed=True,
        external_pdf=True,
        user_data_dir=user_data_dir,
    ) as sb:
        logger.info("Opening %s", url)
        browser.activate(sb, url)
        browser.configure_download_dir(sb, download_dir)

        logger.info("Skipping Cloudflare")
        if browser.is_cloudflare_present(sb):
            browser.skip_cloudflare(sb)
            sb.sleep(2)
        else:
            logger.info("No Cloudflare challenge detected")

        logger.info("Clicking Print PDF (iframe traversal)")
        found, reason = browser.find_print_pdf_via_iframes(sb, timeout=IFRAME_TIMEOUT)
        if not found:
            logger.error("FAILED: %s", reason)
            return 1

        logger.info("Waiting for PDF in %s...", download_dir)
        try:
            pdf_path = browser.wait_for_download(download_dir, timeout=DOWNLOAD_TIMEOUT)
            logger.info("SUCCESS: PDF downloaded to %s", pdf_path)
            return 0
        except TimeoutError as e:
            logger.error("%s", e)
            return 1


def run_attach(port: int, download_dir: str) -> int:
    """Attach and run Print PDF flow (assume already past Cloudflare)."""
    try:
        driver, sb = connect(port=port)
    except Exception as e:
        logger.error(
            "Failed to connect. Is Chrome running with --remote-debugging-port=%d? %s",
            port,
            e,
        )
        return 1

    try:
        browser.configure_download_dir_for_driver(driver, download_dir)
        logger.info("Clicking Print PDF (iframe traversal)")
        found, reason = browser.find_print_pdf_via_iframes(sb, timeout=IFRAME_TIMEOUT)
        if not found:
            logger.error("FAILED: %s", reason)
            return 1

        logger.info("Waiting for PDF in %s...", download_dir)
        try:
            pdf_path = browser.wait_for_download(download_dir, timeout=DOWNLOAD_TIMEOUT)
            logger.info("SUCCESS: PDF downloaded to %s", pdf_path)
            return 0
        except TimeoutError as e:
            logger.error("%s", e)
            return 1
    finally:
        driver.quit()


def main() -> int:
    import os

    parser = argparse.ArgumentParser(
        description="Flow 2: Print PDF via iframe",
        epilog="make flow-2 = run with fresh Chrome. make flow-2-attach = attach to existing.",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--download-dir", default=DEFAULT_DOWNLOAD_DIR)
    parser.add_argument("--attach", action="store_true")
    args = parser.parse_args()

    download_dir = os.path.abspath(args.download_dir)
    os.makedirs(download_dir, exist_ok=True)

    if args.attach:
        return run_attach(args.port, download_dir)

    return run_with_sb(args.url, download_dir)


if __name__ == "__main__":
    sys.exit(main())
