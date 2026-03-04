from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Callable
from datetime import datetime

from dotenv import load_dotenv
from seleniumbase import SB

from bot import browser, chrome_utils, llm, ocr
from bot.browser import BrowserLike
from bot.config import NUM_STEPS, REPO_ROOT

logger = logging.getLogger(__name__)


# Hardcoded defaults (no CLI args for these)
DEFAULT_USER_DATA_DIR = "user_data"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_DOWNLOAD_TIMEOUT = 30
DEFAULT_IFRAME_TIMEOUT = 10
DEFAULT_SUBMIT_SELECTOR: str | None = None


def run_answer_and_submit(
    sb: BrowserLike,
    pdf_text: str,
    num_steps: int,
    model: str = "gpt-4o-mini",
    submit_selector: str | None = None,
    on_before_fill: Callable[[int, str, str, str], None] | None = None,
    on_after_fill: Callable[[int, str, str, str], None] | None = None,
) -> None:
    """Answer each form question using the PDF context and LLM, then submit.

    For each step: get question, detect input type, ask LLM, call *on_before_fill*
    if provided, fill field, call *on_after_fill* if provided. Finally clicks
    the submit button.
    """
    for i in range(num_steps):
        question = browser.get_step_question(sb, i)
        input_type = browser.get_step_input_type(sb, i)
        answer = llm.ask(
            question,
            pdf_text,
            model=model,
            answer_type=input_type,
        )
        if on_before_fill:
            on_before_fill(i, question, input_type, answer)
        browser.fill_step(sb, i, answer, input_type=input_type)
        if on_after_fill:
            on_after_fill(i, question, input_type, answer)
    browser.click_submit(sb, selector=submit_selector, timeout=10)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bot that answers a multi-question form using a downloaded PDF and an LLM.",
    )
    parser.add_argument("--url", required=True, help="URL of the form page")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (no visible window)",
    )

    args = parser.parse_args(argv)
    return args


def _click_print_pdf(sb: BrowserLike, timeout: int = 10) -> None:
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


# Pipeline stages for progress display and snapshot naming. Append/remove stages
# here rather than using magic arithmetic; step numbers stay consistent.
def _pipeline_stages(num_steps: int) -> list[str]:
    base = ["open", "cloudflare", "print_pdf", "pdf_download", "ocr"]
    answers = [f"answer_{i + 1}" for i in range(num_steps)]
    return base + answers + ["submit"]


def run(args: argparse.Namespace) -> None:
    user_data_dir = _resolve_user_data_dir()
    n = NUM_STEPS
    stages = _pipeline_stages(n)
    total = len(stages)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = REPO_ROOT / "outputs" / run_id
    out.mkdir(parents=True, exist_ok=True)
    download_dir = os.path.abspath(str(out / "download"))
    os.makedirs(download_dir, exist_ok=True)
    print(f"Run {run_id} — outputs → {out}")

    def snap(name: str) -> None:
        browser.screenshot(sb, str(out / f"{name}.png"))

    chrome_utils.write_pdf_download_prefs(user_data_dir, download_dir)

    with SB(
        uc=True,
        headed=not args.headless,
        window_size="1920,1080",
        external_pdf=True,  # Chrome: always_open_pdf_externally so Print PDF triggers download
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
                sb.sleep(1)
                if not browser.is_cloudflare_present(sb):
                    print(f"         Cloudflare cleared after {cf_attempt} attempt(s)")
                    break
                print(f"         Cloudflare still present (attempt {cf_attempt}/{max_cf_attempts}), retrying...")
            else:
                print("         Warning: Cloudflare may still be present after max attempts")
        snap("step_2_after_cloudflare")

        snap("step_3_before_print_pdf_click")
        print(f"[3/{total}] Clicking Print PDF button (iframe traversal)")
        _click_print_pdf(sb, timeout=DEFAULT_IFRAME_TIMEOUT)
        snap("step_3_after_print_pdf_click")

        snap("step_4_before_pdf_check_download")
        print(f"[4/{total}] Waiting for PDF in {download_dir}")
        pdf_path = browser.wait_for_download(download_dir, timeout=DEFAULT_DOWNLOAD_TIMEOUT)
        print(f"         Downloaded: {pdf_path}")
        snap("step_4_after_pdf_check_download")

        snap("step_5_before_pdf_ocr_processing")
        print(f"[5/{total}] Extracting text from PDF via OCR (persist in {out}/ocr)")
        persist_dir = out / "ocr"
        pdf_text = ocr.process_pdf_to_artifacts(str(pdf_path), str(persist_dir))
        print(f"         Extracted {len(pdf_text)} characters")
        snap("step_5_after_pdf_ocr_processing")

        def on_before_fill(i: int, question: str, input_type: str, answer: str) -> None:
            step = stages.index(f"answer_{i + 1}") + 1
            snap(f"step_{step}_before_answer_{i + 1}")
            print(f"[{step}/{total}] Answering question {i + 1}/{n}")
            print(f"         Question: {question}")
            print(f"         Type: {input_type}")
            print(f"         Answer: {answer}")

        def on_after_fill(i: int, question: str, input_type: str, answer: str) -> None:
            step = stages.index(f"answer_{i + 1}") + 1
            snap(f"step_{step}_after_answer_{i + 1}")

        submit_step = stages.index("submit") + 1
        snap(f"step_{submit_step}_before_submit")
        print(f"[{total}/{total}] Submitting")
        run_answer_and_submit(
            sb,
            pdf_text,
            n,
            model=DEFAULT_MODEL,
            submit_selector=DEFAULT_SUBMIT_SELECTOR,
            on_before_fill=on_before_fill,
            on_after_fill=on_after_fill,
        )
        snap(f"step_{submit_step}_after_submit")
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
