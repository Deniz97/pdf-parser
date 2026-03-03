from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from seleniumbase import SB

from bot import browser, ocr

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

NUM_STEPS = 3


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


# Hardcoded defaults (no CLI args for these)
DEFAULT_HEADLESS = False
DEFAULT_USER_DATA_DIR = "user_data"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_DOWNLOAD_TIMEOUT = 30
DEFAULT_IFRAME_TIMEOUT = 10
DEFAULT_SUBMIT_SELECTOR: str | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bot that answers a multi-question form using a downloaded PDF and an LLM.",
    )
    parser.add_argument("--url", required=True, help="URL of the form page")

    args = parser.parse_args(argv)
    return args


def _click_print_pdf(sb: object, timeout: int = 10) -> None:
    """Click the Print PDF button via iframe traversal.

    With PDF auto-download prefs, clicking triggers direct download (no popup).
    """
    found, reason = browser.find_print_pdf_via_iframes(sb, timeout=timeout)
    if not found:
        raise RuntimeError(reason or "Print PDF button not found in iframe tree")


def _resolve_user_data_dir() -> str:
    """Return the path to use for Chrome user data (hardcoded default)."""
    default = REPO_ROOT / DEFAULT_USER_DATA_DIR
    default.mkdir(parents=True, exist_ok=True)
    return str(default)


def run(args: argparse.Namespace) -> None:
    user_data_dir = _resolve_user_data_dir()
    n = NUM_STEPS
    total = 6 + n

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = REPO_ROOT / "outputs" / run_id
    out.mkdir(parents=True, exist_ok=True)
    download_dir = os.path.abspath(str(out / "download"))
    os.makedirs(download_dir, exist_ok=True)
    print(f"Run {run_id} — outputs → {out}")

    def snap(name: str) -> None:
        browser.screenshot(sb, str(out / f"{name}.png"))

    _write_pdf_download_prefs(user_data_dir, download_dir)

    with SB(
        uc=True,
        headed=not DEFAULT_HEADLESS,
        window_size="1920,1080",
        external_pdf=True, # Ensure Chrome has always_open_pdf_externally (so Print PDF triggers download)
        user_data_dir=user_data_dir,
    ) as sb:
        print(f"[1/{total}] Opening {args.url}")
        browser.activate(sb, args.url)
        browser.configure_download_dir(sb, download_dir)
        snap("step_1_after_open")

        snap("step_2_before_cloudflare")
        print(f"[2/{total}] Skipping Cloudflare challenge")
        if not browser.is_cloudflare_present(sb):
            print("         No Cloudflare challenge detected, continuing")
        else:
            max_cf_attempts = 5
            for cf_attempt in range(1, max_cf_attempts + 1):
                browser.skip_cloudflare(sb)
                sb.sleep(2)
                if not browser.is_cloudflare_present(sb):
                    print(f"         Cloudflare cleared after {cf_attempt} attempt(s)")
                    break
                print(
                    f"         Cloudflare still present (attempt {cf_attempt}/{max_cf_attempts}), retrying..."
                )
            else:
                print(
                    "         Warning: Cloudflare may still be present after max attempts"
                )
        snap("step_2_after_cloudflare")

        snap("step_3_before_print_pdf_click")
        print(f"[3/{total}] Clicking Print PDF button (iframe traversal)")
        _click_print_pdf(sb, timeout=DEFAULT_IFRAME_TIMEOUT)
        sb.sleep(2)
        snap("step_3_after_print_pdf_click")

        snap("step_4_before_pdf_check_download")
        print(f"[4/{total}] Waiting for PDF in {download_dir}")
        pdf_path = browser.wait_for_download(
            download_dir, timeout=DEFAULT_DOWNLOAD_TIMEOUT
        )
        print(f"         Downloaded: {pdf_path}")
        snap("step_4_after_pdf_check_download")

        snap("step_5_before_pdf_ocr_processing")
        print(f"[5/{total}] Extracting text from PDF via OCR (persist in {out}/ocr)")
        persist_dir = out / "ocr"
        pdf_text = ocr.process_pdf_to_artifacts(str(pdf_path), str(persist_dir))
        print(f"         Extracted {len(pdf_text)} characters")
        snap("step_5_after_pdf_ocr_processing")

        def on_before_fill(i: int, question: str, input_type: str, answer: str) -> None:
            step = 6 + i
            snap(f"step_{step}_before_answer_{i + 1}")
            print(f"[{step}/{total}] Answering question {i + 1}/{n}")
            print(f"         Question: {question}")
            print(f"         Type: {input_type}")
            print(f"         Answer: {answer}")

        def on_after_fill(i: int, question: str, input_type: str, answer: str) -> None:
            snap(f"step_{6 + i}_after_answer_{i + 1}")

        snap(f"step_{total}_before_submit")
        print(f"[{total}/{total}] Submitting")
        browser.run_answer_and_submit(
            sb,
            pdf_text,
            n,
            model=DEFAULT_MODEL,
            submit_selector=DEFAULT_SUBMIT_SELECTOR,
            on_before_fill=on_before_fill,
            on_after_fill=on_after_fill,
        )
        snap(f"step_{total}_after_submit")
        print("Done!")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    load_dotenv()
    args = parse_args(argv)
    run(args)


if __name__ == "__main__":
    main()
