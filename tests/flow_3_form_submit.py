#!/usr/bin/env python3
"""Flow 3: Fill form and submit.

Run:  Full flow from beginning (open URL, Cloudflare, Print PDF, OCR, fill, submit).
Attach: Use existing exampl-pdf.pdf, OCR it, fill form, click submit (form page already open).

Usage:
  make flow-3              # Run full bot
  make flow-3-attach       # Attach (Chrome on form page, use tests/exampl-pdf.pdf)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo_root / "src"))
sys.path.insert(0, str(_repo_root))

from dotenv import load_dotenv

from bot import browser, ocr
from bot.main import run as bot_run
from bot.main import parse_args as bot_parse_args
from tests.browser_utils import DEFAULT_URL, DEFAULT_PORT, connect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

NUM_STEPS = 3
EXAMPLE_PDF = Path(__file__).resolve().parent / "exampl-pdf.pdf"


def run_full_flow(url: str) -> int:
    """Run full bot flow from beginning (uses main.run)."""
    load_dotenv()
    args = bot_parse_args(["--url", url])
    bot_run(args)
    return 0


def run_attach(port: int, pdf_path: Path, url: str) -> int:
    """Attach, use local PDF, fill form and submit."""
    load_dotenv()
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
        # Ensure we're on the form page
        if url not in driver.current_url:
            logger.info("Navigating to %s", url)
            sb.activate_cdp_mode(url)
            sb.sleep(3)
            if browser.is_cloudflare_present(sb):
                browser.skip_cloudflare(sb)
                sb.sleep(2)

        if not pdf_path.exists():
            logger.error("PDF not found: %s", pdf_path)
            return 1

        persist_dir = Path(__file__).resolve().parent / "outputs" / "flow3_ocr"
        persist_dir.mkdir(parents=True, exist_ok=True)
        logger.info("OCR on %s", pdf_path)
        pdf_text = ocr.process_pdf_to_artifacts(str(pdf_path), str(persist_dir))
        logger.info("Extracted %d chars", len(pdf_text))

        logger.info("Filling form and submitting")
        browser.run_answer_and_submit(sb, pdf_text, NUM_STEPS)
        logger.info("SUCCESS: Form filled and submitted")
        return 0
    finally:
        driver.quit()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Flow 3: Fill form and submit",
        epilog="make flow-3 = full bot. make flow-3-attach = attach, use exampl-pdf.pdf.",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--pdf", default=str(EXAMPLE_PDF), help="PDF for attach mode")
    parser.add_argument("--attach", action="store_true")
    args = parser.parse_args()

    if args.attach:
        return run_attach(args.port, Path(args.pdf), args.url)

    return run_full_flow(args.url)


if __name__ == "__main__":
    sys.exit(main())
