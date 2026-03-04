from __future__ import annotations

import glob
import json
import logging
import os
import random
import re
import time
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from seleniumbase import SB

logger = logging.getLogger(__name__)

# CSS for the red-dot indicator (used in _paint_red_dot_on_element)
_RED_DOT_CSS = (
    "position:absolute;right:4px;top:50%;transform:translateY(-50%);width:12px;height:12px;border-radius:50%;background:red;z-index:9999;pointer-events:none"
)


class CdpLike(Protocol):
    """Protocol for CDP-like objects (evaluate, click, wait_for_element)."""

    def evaluate(self, expression: str) -> object: ...
    def wait_for_element(self, selector: str, timeout: int = 5) -> None: ...
    def click(self, selector: str) -> None: ...


class DriverLike(Protocol):
    """Protocol for WebDriver-like objects (refresh, execute_cdp_cmd)."""

    def refresh(self) -> None: ...
    def execute_cdp_cmd(self, cmd: str, params: dict) -> object: ...


class BrowserLike(Protocol):
    """Protocol for browser automation objects (SB or SbAdapter).

    Supports both SeleniumBase SB and tests.browser_utils.SbAdapter.
    driver may be None before the browser is started (SB/BaseCase has no stubs).
    """

    cdp: CdpLike
    driver: DriverLike | None

    def sleep(self, seconds: float) -> None: ...
    def activate_cdp_mode(self, url: str) -> None: ...


POLL_INTERVAL = 0.5


def _wait_for_document_ready(sb: SB, timeout: int = 10) -> None:
    """Poll until document.readyState === 'complete' or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ready = sb.cdp.evaluate("document.readyState === 'complete'")
            if ready:
                return
        except Exception as exc:
            logger.debug("Document ready check failed (retrying): %s", exc)
        time.sleep(POLL_INTERVAL)
    logger.warning("Document still not ready after %ds", timeout)


def _wait_for_main_iframe(sb: SB, deadline: float) -> bool:
    """Poll until main > iframe exists. Returns True if found, False when past deadline."""
    js = "document.querySelector('main iframe') !== null"
    while time.time() < deadline:
        try:
            if sb.cdp.evaluate(js):
                return True
        except Exception as exc:
            logger.debug("Main iframe check failed (retrying): %s", exc)
        time.sleep(POLL_INTERVAL)
    return False


def screenshot(sb: SB, path: str) -> None:
    """Save a browser screenshot to *path*."""
    sb.cdp.save_screenshot(path)
    logger.info("Screenshot saved: %s", path)


def activate(sb: SB, url: str, ready_timeout: int = 10) -> None:
    """Navigate to *url* and activate CDP mode for stealth interaction.

    Waits for document.readyState === 'complete' (or *ready_timeout* seconds).
    """
    logger.info("Activating CDP mode for %s", url)
    sb.activate_cdp_mode(url)
    _wait_for_document_ready(sb, timeout=ready_timeout)
    logger.info("CDP mode active")


def is_cloudflare_present(sb: SB) -> bool:
    """Return True if the page appears to be showing a Cloudflare challenge."""
    try:
        title = sb.cdp.evaluate("document.title")
        if title and "just a moment" in str(title).lower():
            return True
    except Exception as exc:
        logger.debug("Title check failed (assuming no Cloudflare): %s", exc)

    js = """
    (() => {
        const selectors = [
            '#challenge-running', '#challenge-stage',
            '.cf-turnstile', 'iframe[src*="challenges.cloudflare.com"]',
        ];
        return selectors.some(s => document.querySelector(s) !== null);
    })()
    """
    try:
        result = sb.cdp.evaluate(js)
        return bool(result)
    except Exception as exc:
        logger.debug("Cloudflare selector check failed: %s", exc)
        return False


def skip_cloudflare(sb: SB, timeout: int = 15) -> None:
    """Attempt to bypass a Cloudflare challenge if one is present.

    Calls solve_captcha() then waits for Cloudflare layout/tab indicators to
    disappear (or timeout). Uses *timeout* as max wait duration in seconds.
    """
    logger.info("Checking for Cloudflare challenge...")
    try:
        sb.solve_captcha()
    except Exception as exc:
        logger.debug("solve_captcha failed (no challenge or unsupported): %s", exc)
        logger.info("No Cloudflare challenge detected, continuing")
        return

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_cloudflare_present(sb):
            logger.info("Cloudflare challenge cleared")
            return
        time.sleep(POLL_INTERVAL)

    logger.warning("Cloudflare indicators still present after %ds timeout", timeout)


def find_print_pdf_via_iframes(sb: BrowserLike, timeout: int = 10, max_scroll_refreshes: int = 1) -> tuple[bool, str]:
    """Traverse iframe chain starting from the first iframe inside ``<main>`` to
    find and click the 'Print PDF' button via depth-first search.

    Switches into each nested iframe's document and looks for a ``<button>``
    whose text is exactly ``Print PDF``.  If the button exists but is scrolled
    out of view, refreshes the page (up to *max_scroll_refreshes* times) and
    retries.  Returns ``(True, "")`` if found and clicked, or ``(False, reason)``
    with a diagnostic message.
    """
    start = time.time()
    deadline = time.time() + timeout
    logger.info("iframe traversal: waiting for main iframe (Flash content)…")
    if not _wait_for_main_iframe(sb, deadline):
        return False, "main iframe did not appear within timeout"

    scroll_refreshes_done = 0

    js = """
    (() => {
        const diag = {
            iframesSearched: 0,
            buttonsFound: 0,
            buttonTexts: [],
            crossOriginErrors: [],
            maxDepthReached: 0,
        };

        function topLevelCoords(el) {
            const rect = el.getBoundingClientRect();
            let x = rect.left + rect.width / 2;
            let y = rect.top + rect.height / 2;
            let frame = el.ownerDocument.defaultView?.frameElement;
            while (frame) {
                const fr = frame.getBoundingClientRect();
                x += fr.left;
                y += fr.top;
                frame = frame.ownerDocument?.defaultView?.frameElement;
            }
            return { x, y };
        }

        function isInViewport(clickX, clickY) {
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            const margin = 20;
            return clickX >= margin && clickX <= vw - margin
                && clickY >= margin && clickY <= vh - margin;
        }

        function search(doc, depth) {
            if (depth > diag.maxDepthReached) diag.maxDepthReached = depth;
            if (depth > 50) return null;

            const buttons = doc.querySelectorAll('button');
            diag.buttonsFound += buttons.length;
            for (const btn of buttons) {
                const text = btn.textContent.trim();
                if (diag.buttonTexts.length < 20) diag.buttonTexts.push(text);
                if (text === 'Print PDF') {
                    const coords = topLevelCoords(btn);
                    const visible = isInViewport(coords.x, coords.y);
                    return { found: true, depth: depth,
                             clickX: coords.x, clickY: coords.y,
                             visible: visible };
                }
            }

            const iframes = doc.querySelectorAll('iframe');
            for (const iframe of iframes) {
                diag.iframesSearched++;
                try {
                    const inner = iframe.contentDocument
                              || iframe.contentWindow.document;
                    if (inner) {
                        const result = search(inner, depth + 1);
                        if (result) return result;
                    }
                } catch(e) {
                    diag.crossOriginErrors.push(
                        'depth=' + depth + ': ' + e.message
                    );
                    continue;
                }
            }
            return null;
        }

        const main = document.querySelector('main');
        if (!main)
            return { found: false, error: 'no main element', diag: diag };
        const root = main.querySelector('iframe');
        if (!root)
            return { found: false, error: 'no iframe inside main',
                     allIframes: main.querySelectorAll('iframe').length,
                     diag: diag };

        try {
            const doc = root.contentDocument || root.contentWindow.document;
            if (!doc)
                return { found: false,
                         error: 'cannot access iframe document', diag: diag };
            const result = search(doc, 0);
            if (result) { result.diag = diag; return result; }
            return { found: false,
                     error: 'button not found in iframe tree', diag: diag };
        } catch(e) {
            return { found: false,
                     error: 'cross-origin: ' + e.message, diag: diag };
        }
    })()
    """
    # Reset deadline so search loop gets full timeout from when iframe is ready
    deadline = time.time() + timeout
    last_error = "timeout with no attempts"
    last_diag: dict | None = None
    attempt = 0

    while time.time() < deadline:
        attempt += 1
        raw = sb.cdp.evaluate(js)
        result = json.loads(raw) if isinstance(raw, str) else raw
        elapsed_ms = (time.time() - start) * 1000

        diag = result.get("diag", {}) if isinstance(result, dict) else {}

        if isinstance(result, dict) and result.get("found"):
            visible = result.get("visible", True)
            if not visible and scroll_refreshes_done < max_scroll_refreshes:
                logger.info(
                    "iframe traversal: Print PDF found but scrolled out of view (attempt %d). Refreshing page and retrying…",
                    attempt,
                )
                scroll_refreshes_done += 1
                try:
                    if sb.driver:
                        sb.driver.refresh()
                    else:
                        return False, "driver not available for refresh"
                except Exception as exc:
                    logger.warning("Page refresh failed: %s", exc)
                    return False, f"refresh failed: {exc}"
                logger.info("iframe traversal: waiting for main iframe after refresh…")
                if not _wait_for_main_iframe(sb, deadline):
                    return False, "main iframe did not reappear after refresh"
                continue  # retry search
            logger.info(
                "iframe traversal: found Print PDF at depth %d in %.0fms (attempt %d, %d iframes searched, %d buttons seen)",
                result.get("depth", -1),
                elapsed_ms,
                attempt,
                diag.get("iframesSearched", 0),
                diag.get("buttonsFound", 0),
            )
            # Use CDP Input.dispatchMouseEvent (trusted events) — btn.click()
            # produces synthetic events that many sites block (e.g. isTrusted check).
            click_x = result.get("clickX")
            click_y = result.get("clickY")
            if click_x is not None and click_y is not None:
                ok, reason = _try_cdp_click(sb, float(click_x), float(click_y))
                if not ok:
                    return False, f"CDP click at ({click_x},{click_y}) failed: {reason}"
            return True, ""

        error = result.get("error", "unknown") if isinstance(result, dict) else str(result)
        last_error = error
        last_diag = diag

        diag_summary = f"iframes={diag.get('iframesSearched', '?')}, buttons={diag.get('buttonsFound', '?')}, maxDepth={diag.get('maxDepthReached', '?')}"
        if diag.get("buttonTexts"):
            diag_summary += f", texts={diag['buttonTexts']}"
        if diag.get("crossOriginErrors"):
            diag_summary += f", xorigin={diag['crossOriginErrors']}"
        if isinstance(result, dict) and "allIframes" in result:
            diag_summary += f", allIframesOnPage={result['allIframes']}"

        logger.info(
            "iframe traversal attempt %d (%.0fms): %s [%s]",
            attempt,
            elapsed_ms,
            error,
            diag_summary,
        )
        time.sleep(POLL_INTERVAL)

    elapsed_ms = (time.time() - start) * 1000

    summary = last_error
    if last_diag:
        parts = [
            f"iframes searched: {last_diag.get('iframesSearched', '?')}",
            f"buttons found: {last_diag.get('buttonsFound', '?')}",
            f"max depth: {last_diag.get('maxDepthReached', '?')}",
        ]
        if last_diag.get("buttonTexts"):
            parts.append(f"button texts: {last_diag['buttonTexts']}")
        if last_diag.get("crossOriginErrors"):
            parts.append(f"cross-origin errors: {last_diag['crossOriginErrors']}")
        summary += f" ({', '.join(parts)})"

    logger.warning(
        "iframe traversal: gave up after %d attempts / %.0fms — %s",
        attempt,
        elapsed_ms,
        summary,
    )
    return False, summary


def configure_download_dir(sb: SB, download_dir: str) -> None:
    """Configure Chrome to save downloads to *download_dir* via CDP.

    Uses Browser.setDownloadBehavior so the save dialog defaults to this path.
    """
    path = os.path.abspath(download_dir)
    os.makedirs(path, exist_ok=True)
    try:
        import mycdp.browser as cdp_browser

        cmd = cdp_browser.set_download_behavior(
            behavior="allow",
            download_path=path,
        )
        sb.cdp.loop.run_until_complete(sb.cdp.page.send(cmd))
        logger.info("Configured download directory: %s", path)
    except Exception as exc:
        logger.warning(
            "Could not set download path via CDP (%s); save dialog may use default",
            exc,
        )


def configure_download_dir_for_driver(driver: DriverLike, download_dir: str) -> None:
    """Configure download directory via CDP for a raw WebDriver.

    Use when attaching to an existing Chrome (e.g. via debuggerAddress) so
    PDFs go to a known path. Driver must support execute_cdp_cmd.
    """
    path = os.path.abspath(download_dir)
    os.makedirs(path, exist_ok=True)
    try:
        driver.execute_cdp_cmd(
            "Browser.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": path},
        )
        logger.info("Configured download directory: %s", path)
    except Exception as exc:
        logger.warning(
            "Could not set download path via CDP (%s); PDF may go to default Downloads",
            exc,
        )


def wait_for_download(download_dir: str, timeout: int = 30) -> str:
    """Poll ``download_dir`` until a ``.pdf`` file appears. Returns the path."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        pdfs = glob.glob(os.path.join(download_dir, "*.pdf"))
        ready = [p for p in pdfs if not p.endswith(".crdownload")]
        if ready:
            ready.sort(key=os.path.getmtime, reverse=True)
            return ready[0]
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"No PDF appeared in {download_dir} within {timeout}s")


def get_step_question(sb: BrowserLike, step: int) -> str:
    """Return the question text for the *step*-th form field (0-indexed).

    Looks for ``<label>`` elements in DOM order first, then falls back to
    heading and paragraph elements.
    """
    js = "JSON.stringify([...document.querySelectorAll('label')].map(l => l.textContent.trim()))"
    raw = sb.cdp.evaluate(js)
    labels = json.loads(raw) if isinstance(raw, str) else raw

    if isinstance(labels, list) and labels and step < len(labels) and labels[step]:
        return labels[step]

    raise RuntimeError(f"Could not find question text for step {step}")


def get_step_input_type(sb: BrowserLike, step: int) -> str:
    """Detect whether the *step*-th form field is ``'text'`` or ``'select'``.

    Finds all visible ``input[type="text"]``, ``textarea``, and ``select``
    elements in DOM order and checks the tag at the given index.
    """
    js = "JSON.stringify([...document.querySelectorAll('input[type=\"text\"], textarea, select')].map(el => el.tagName.toLowerCase()))"
    raw = sb.cdp.evaluate(js)
    tags = json.loads(raw) if isinstance(raw, str) else raw

    if not isinstance(tags, list) or not tags or step >= len(tags):
        raise RuntimeError(f"Could not detect input type for step {step}")

    return "select" if tags[step] == "select" else "text"


def fill_step(
    sb: BrowserLike,
    step: int,
    answer: str,
    input_type: str | None = None,
) -> str:
    """Fill the *step*-th form field with *answer*.

    For text inputs the field is cleared and the answer typed in.
    For ``<select>`` dropdowns the option whose visible text best matches
    *answer* is selected.

    Returns the detected input type (``'text'`` or ``'select'``).
    """
    if input_type is None:
        input_type = get_step_input_type(sb, step)

    safe_answer = json.dumps(answer)

    if input_type == "select":
        js = f"""
        (() => {{
            const fields = [...document.querySelectorAll(
                'input[type="text"], textarea, select'
            )];
            const field = fields[{step}];
            if (!field || field.tagName.toLowerCase() !== 'select') return false;
            const target = {safe_answer}.toLowerCase();
            const option = [...field.options].find(
                o => o.text.trim().toLowerCase() === target
                  || o.value.toLowerCase() === target
            );
            if (!option) return false;
            field.value = option.value;
            field.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return true;
        }})()
        """
    else:
        # Use native value setter to bypass React/controlled-input overrides
        js = f"""
        (() => {{
            const fields = [...document.querySelectorAll(
                'input[type="text"], textarea, select'
            )];
            const field = fields[{step}];
            if (!field) return false;
            field.focus();
            const proto = field.tagName.toLowerCase() === 'textarea'
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
            const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            nativeSetter.call(field, '');
            nativeSetter.call(field, {safe_answer});
            field.dispatchEvent(new Event('input', {{ bubbles: true }}));
            field.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return true;
        }})()
        """

    result = sb.cdp.evaluate(js)
    if not result:
        raise RuntimeError(f"Could not fill {input_type} field at step {step} with {answer!r}")
    return input_type


def _paint_red_dot_on_element(sb: BrowserLike, selector: str) -> None:
    """Paint a red dot on the element to indicate it was found/clicked."""
    if ":contains(" in selector:
        m = re.match(r'(\w+):contains\("([^"]*)"\)', selector)
        if m:
            tag, text = m.groups()
            tag_esc, text_esc = json.dumps(tag), json.dumps(text)
            js = f"""
            (() => {{
                const el = Array.from(document.querySelectorAll({tag_esc})).find(
                    e => e.textContent.trim().includes({text_esc})
                );
                if (!el) return;
                const dot = document.createElement("div");
                dot.style.cssText = {json.dumps(_RED_DOT_CSS)};
                el.style.position = el.style.position || "relative";
                el.appendChild(dot);
            }})()
            """
        else:
            return
    else:
        sel_esc = json.dumps(selector)
        js = f"""
        (() => {{
            const el = document.querySelector({sel_esc});
            if (!el) return;
            const dot = document.createElement("div");
            dot.style.cssText = {json.dumps(_RED_DOT_CSS)};
            el.style.position = el.style.position || "relative";
            el.appendChild(dot);
        }})()
        """
    try:
        sb.cdp.evaluate(js)
    except Exception as exc:
        logger.debug("Paint red dot failed: %s", exc)


def click_submit(
    sb: BrowserLike,
    timeout: int = 5,
) -> None:
    """Click the submit button on the form."""
    selector = 'button[type="submit"]'
    sb.cdp.wait_for_element(selector, timeout=timeout)
    sb.cdp.click(selector)
    _paint_red_dot_on_element(sb, selector)
    return


def _do_cdp_mouse_click(driver: DriverLike, css_x: float, css_y: float) -> bool:
    """Dispatch CDP Input mouse events via execute_cdp_cmd (works with any driver)."""

    def send(method: str, params: dict) -> None:
        driver.execute_cdp_cmd(method, params)

    x, y = float(css_x), float(css_y)
    send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    time.sleep(random.uniform(0.05, 0.15))
    send(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
    )
    time.sleep(random.uniform(0.04, 0.10))
    send(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
    )
    time.sleep(0.3)
    return True


def _try_cdp_click(sb: BrowserLike, css_x: float, css_y: float) -> tuple[bool, str]:
    """CDP Input.dispatchMouseEvent — protocol-level, trusted events."""
    try:
        page = getattr(sb.cdp, "page", None)
        loop = getattr(sb.cdp, "loop", None)
        if page and loop:
            import mycdp as cdp

            input_mod = getattr(cdp, "input_")  # mycdp has input_ (avoids builtin shadow)
            _send = lambda cmd: loop.run_until_complete(page.send(cmd))  # noqa: E731
            _send(
                input_mod.dispatch_mouse_event(
                    type_="mouseMoved",
                    x=float(css_x),
                    y=float(css_y),
                )
            )
            time.sleep(random.uniform(0.05, 0.15))
            _send(
                input_mod.dispatch_mouse_event(
                    type_="mousePressed",
                    x=float(css_x),
                    y=float(css_y),
                    button=input_mod.MouseButton.LEFT,
                    click_count=1,
                )
            )
            time.sleep(random.uniform(0.04, 0.10))
            _send(
                input_mod.dispatch_mouse_event(
                    type_="mouseReleased",
                    x=float(css_x),
                    y=float(css_y),
                    button=input_mod.MouseButton.LEFT,
                    click_count=1,
                )
            )
            time.sleep(0.3)
            return True, "mousePressed + mouseReleased dispatched"
        # Fallback for attach script (sb has .driver but no cdp.page)
        if sb.driver:
            _do_cdp_mouse_click(sb.driver, css_x, css_y)
            return True, "mousePressed + mouseReleased via execute_cdp_cmd"
        return False, "driver not available for CDP click"
    except Exception as exc:
        return False, str(exc)
