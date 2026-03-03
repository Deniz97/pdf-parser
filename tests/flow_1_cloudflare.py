#!/usr/bin/env python3
"""Flow 1: Open URL, pass Cloudflare.

Run:  Launch Chrome, open URL, pass Cloudflare.
Attach: Connect to existing Chrome (navigate to URL first), pass Cloudflare.

Usage:
  make flow-1              # Run with fresh Chrome
  make flow-1-attach       # Attach (Chrome must be running)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add repo root and src for imports
_repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo_root / "src"))
sys.path.insert(0, str(_repo_root))

from seleniumbase import SB

from bot import browser
from tests.browser_utils import DEFAULT_URL, DEFAULT_PORT, connect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_with_sb(url: str) -> int:
    """Run flow with SeleniumBase (fresh Chrome)."""
    with SB(uc=True, headed=True) as sb:
        logger.info("Opening %s", url)
        browser.activate(sb, url)
        logger.info("Skipping Cloudflare")
        browser.skip_cloudflare(sb)
        title = sb.cdp.get_title()
        assert title, "page title is empty after Cloudflare bypass"
        logger.info("SUCCESS: Past Cloudflare. Title: %s", title)
    return 0


def run_attach(url: str, port: int) -> int:
    """Attach to Chrome and pass Cloudflare."""
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
        # Navigate if not already there
        if url not in driver.current_url:
            logger.info("Navigating to %s", url)
            sb.activate_cdp_mode(url)
        else:
            sb.sleep(1)

        logger.info("Skipping Cloudflare")
        browser.skip_cloudflare(sb)
        sb.sleep(2)
        title = sb.cdp.get_title()
        if not title:
            logger.error("Page title empty after Cloudflare")
            return 1
        logger.info("SUCCESS: Past Cloudflare. Title: %s", title)
        return 0
    finally:
        driver.quit()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Flow 1: Open URL, pass Cloudflare",
        epilog="make flow-1 = run with fresh Chrome. make flow-1-attach = attach to existing.",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--attach", action="store_true", help="Attach to existing Chrome")
    args = parser.parse_args()

    if args.attach:
        return run_attach(args.url, args.port)

    return run_with_sb(args.url)


if __name__ == "__main__":
    sys.exit(main())
