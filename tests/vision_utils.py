"""Vision utilities for tests: template matching and OCR text detection.

Used by test_template_matching.py and test_ocr.py. The main bot pipeline
uses JS iframe traversal for Print PDF, not computer vision. This module
provides image-based localization for debugging and test assertions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

SCALES = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)

# Default crop region for Print PDF button (used by tests)
OCR_CROP_REGION: tuple[int, int, int, int] = (1250, 150, 1700, 350)


@dataclass
class MatchResult:
    """Result of a template match attempt."""

    confidence: float
    threshold: float
    top_left: tuple[int, int] | None
    size: tuple[int, int]
    center: tuple[int, int] | None

    @property
    def found(self) -> bool:
        return self.center is not None and self.confidence >= self.threshold


@dataclass
class OcrMatchResult:
    """Result of an OCR-based text detection attempt."""

    found: bool
    text: str
    confidence: int
    top_left: tuple[int, int] | None
    size: tuple[int, int] | None
    center: tuple[int, int] | None
    words: list[dict] = field(default_factory=list)


def find_template(
    screenshot: str | Path,
    template: str | Path,
    threshold: float = 0.8,
    scales: tuple[float, ...] = SCALES,
) -> MatchResult:
    """Locate *template* inside *screenshot* via multi-scale template matching.

    Tries several scale factors to handle DPI/resolution differences between
    the reference image and the live screenshot (e.g. Retina vs non-Retina).

    Returns a ``MatchResult`` with the best match info regardless of whether
    it exceeds *threshold*.
    """
    img = cv2.imread(str(screenshot), cv2.IMREAD_GRAYSCALE)
    tpl = cv2.imread(str(template), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Cannot read screenshot: {screenshot}")
    if tpl is None:
        raise FileNotFoundError(f"Cannot read template: {template}")

    best_val = -1.0
    best_loc: tuple[int, int] | None = None
    best_size: tuple[int, int] = (tpl.shape[1], tpl.shape[0])

    for scale in scales:
        resized = cv2.resize(tpl, None, fx=scale, fy=scale)
        rh, rw = resized.shape[:2]
        if rh > img.shape[0] or rw > img.shape[1]:
            continue

        result = cv2.matchTemplate(img, resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_size = (rw, rh)

    logger.info("Template match: confidence=%.3f threshold=%.2f", best_val, threshold)

    center: tuple[int, int] | None = None
    if best_loc is not None:
        center = (best_loc[0] + best_size[0] // 2, best_loc[1] + best_size[1] // 2)

    return MatchResult(
        confidence=best_val,
        threshold=threshold,
        top_left=best_loc,
        size=best_size,
        center=center,
    )


def highlight_match(
    screenshot: str | Path,
    result: MatchResult,
    output_path: str | Path,
) -> None:
    """Draw a rectangle around the best match and save the annotated image.

    Uses green for a match above threshold, red otherwise. Confidence is
    rendered as text near the rectangle.
    """
    img = cv2.imread(str(screenshot))
    if img is None:
        raise FileNotFoundError(f"Cannot read screenshot: {screenshot}")

    if result.top_left is None:
        cv2.imwrite(str(output_path), img)
        return

    color = (0, 255, 0) if result.found else (0, 0, 255)
    x, y = result.top_left
    w, h = result.size
    cv2.rectangle(img, (x, y), (x + w, y + h), color, 3)

    label = f"{result.confidence:.3f} ({'OK' if result.found else 'BELOW'})"
    cv2.putText(
        img,
        label,
        (x, max(y - 10, 20)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        color,
        2,
    )
    cv2.imwrite(str(output_path), img)
    logger.info("Debug screenshot saved: %s", output_path)


def get_image_size(path: str | Path) -> tuple[int, int]:
    """Return ``(width, height)`` of an image file."""
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {path}")
    h, w = img.shape[:2]
    return (w, h)


# ---------------------------------------------------------------------------
# OCR-based text detection
# ---------------------------------------------------------------------------


def find_text_ocr(
    screenshot: str | Path,
    target: str,
    crop: tuple[int, int, int, int] | None = None,
    psm: int = 7,
    oem: int = 3,
    invert: bool = True,
    grayscale: bool = True,
    scale: float = 2.0,
    threshold: int = 127,
    processed_debug_path: str | Path | None = None,
) -> OcrMatchResult:
    """Locate *target* text in a screenshot using Tesseract OCR.

    Pre-processes the image (crop, grayscale, invert, threshold, scale) to
    handle white-on-colored-background text like button labels. Returns
    absolute coordinates on the original (uncropped) screenshot.
    """
    img = Image.open(str(screenshot))
    crop_offset = (0, 0)

    if crop:
        img = img.crop(crop)
        crop_offset = (crop[0], crop[1])

    if grayscale:
        img = img.convert("L")
    if invert:
        img = ImageOps.invert(img.convert("RGB"))
    if threshold > 0:
        arr = np.array(img.convert("L"))
        _, arr = cv2.threshold(arr, threshold, 255, cv2.THRESH_BINARY)
        img = Image.fromarray(arr)
    if scale != 1.0:
        new_size = (int(img.width * scale), int(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    if processed_debug_path:
        img.save(str(processed_debug_path))
        logger.info("OCR processed (cropped) image saved: %s", processed_debug_path)

    config = f"--oem {oem} --psm {psm}"
    data = pytesseract.image_to_data(
        img,
        config=config,
        output_type=pytesseract.Output.DICT,
    )

    scale_inv = 1.0 / scale if scale != 1.0 else 1.0

    words: list[dict] = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue
        raw_x, raw_y = data["left"][i], data["top"][i]
        raw_w, raw_h = data["width"][i], data["height"][i]
        words.append(
            {
                "text": text,
                "conf": int(data["conf"][i]),
                "box": (
                    int(raw_x * scale_inv) + crop_offset[0],
                    int(raw_y * scale_inv) + crop_offset[1],
                    int(raw_w * scale_inv),
                    int(raw_h * scale_inv),
                ),
            }
        )
    target_parts = target.lower().split()
    n = len(target_parts)

    for w in words:
        if target.lower() in w["text"].lower():
            bx, by, bw, bh = w["box"]
            return OcrMatchResult(
                found=True,
                text=w["text"],
                confidence=w["conf"],
                top_left=(bx, by),
                size=(bw, bh),
                center=(bx + bw // 2, by + bh // 2),
                words=words,
            )

    if n > 1:
        for j in range(len(words) - n + 1):
            window = [w["text"].lower() for w in words[j : j + n]]
            if window == target_parts:
                span = words[j : j + n]
                xs = [w["box"][0] for w in span]
                ys = [w["box"][1] for w in span]
                x2s = [w["box"][0] + w["box"][2] for w in span]
                y2s = [w["box"][1] + w["box"][3] for w in span]

                bx, by = min(xs), min(ys)
                bw, bh = max(x2s) - bx, max(y2s) - by
                avg_conf = sum(w["conf"] for w in span) // n
                matched_text = " ".join(w["text"] for w in span)

                return OcrMatchResult(
                    found=True,
                    text=matched_text,
                    confidence=avg_conf,
                    top_left=(bx, by),
                    size=(bw, bh),
                    center=(bx + bw // 2, by + bh // 2),
                    words=words,
                )

    logger.warning(
        "OCR could not find '%s' — detected words: %s",
        target,
        [w["text"] for w in words],
    )
    return OcrMatchResult(
        found=False,
        text="",
        confidence=0,
        top_left=None,
        size=None,
        center=None,
        words=words,
    )


def highlight_ocr_match(
    screenshot: str | Path,
    result: OcrMatchResult,
    output_path: str | Path,
    crop: tuple[int, int, int, int] | None = None,
) -> None:
    """Draw bounding boxes for all detected words and highlight the match.

    Every detected word gets a thin cyan box with its text label.  The matched
    target (if any) gets a thicker orange/red box on top.  When *crop* is
    provided a dashed green rectangle shows the crop region.
    """
    img = cv2.imread(str(screenshot))
    if img is None:
        raise FileNotFoundError(f"Cannot read screenshot: {screenshot}")

    if crop:
        cv2.rectangle(
            img,
            (crop[0], crop[1]),
            (crop[2], crop[3]),
            (0, 200, 0),
            2,
        )

    for w in result.words:
        bx, by, bw, bh = w["box"]
        cv2.rectangle(img, (bx, by), (bx + bw, by + bh), (255, 255, 0), 1)
        cv2.putText(
            img,
            f"{w['text']} ({w['conf']})",
            (bx, max(by - 4, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 0),
            1,
        )

    if result.top_left is not None and result.size is not None:
        color = (255, 165, 0) if result.found else (0, 0, 255)
        x, y = result.top_left
        w, h = result.size
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 3)
        label = f"OCR: {result.text!r} conf={result.confidence}"
        cv2.putText(
            img,
            label,
            (x, max(y - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2,
        )

    cv2.imwrite(str(output_path), img)
    logger.info("OCR debug screenshot saved: %s", output_path)


def draw_click_marker(
    screenshot: str | Path,
    output_path: str | Path,
    click_css: tuple[float, float],
    click_px: tuple[int, int],
    pixel_ratio: float,
    label: str = "",
    strategy_lines: list[str] | None = None,
) -> None:
    """Draw a crosshair + circle at the exact click point on a screenshot.

    Produces a visual debug artifact showing precisely where the bot attempted
    to click, with coordinate annotations and (optionally) per-strategy results.
    """
    img = cv2.imread(str(screenshot))
    if img is None:
        raise FileNotFoundError(f"Cannot read screenshot: {screenshot}")

    cx, cy = click_px
    arm = 40
    color = (255, 0, 255)  # magenta
    dot_color = (0, 0, 255)  # red center dot

    cv2.line(img, (cx - arm, cy), (cx + arm, cy), color, 3)
    cv2.line(img, (cx, cy - arm), (cx, cy + arm), color, 3)
    cv2.circle(img, (cx, cy), arm, color, 2)
    cv2.circle(img, (cx, cy), 5, dot_color, -1)

    header = f"CSS({click_css[0]:.1f}, {click_css[1]:.1f})  px({cx}, {cy})  r={pixel_ratio:.2f}"
    if label:
        header = f"{label} | {header}"
    cv2.putText(
        img,
        header,
        (cx + arm + 10, cy - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        2,
    )

    if strategy_lines:
        y_offset = cy + arm + 25
        for line in strategy_lines:
            line_color = (0, 200, 0) if line.startswith("[OK]") else (0, 0, 255)
            cv2.putText(
                img,
                line,
                (cx - arm, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                line_color,
                1,
            )
            y_offset += 18

    cv2.imwrite(str(output_path), img)
    logger.info("Click marker debug saved: %s", output_path)
