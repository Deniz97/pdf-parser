from __future__ import annotations

import logging
from pathlib import Path

from pdf2image import convert_from_path
from PIL import Image
import pytesseract

logger = logging.getLogger(__name__)


def extract_text(pdf_path: str, dpi: int = 300) -> str:
    """Convert a PDF to images and OCR each page, returning the full text."""
    images = convert_from_path(pdf_path, dpi=dpi)
    pages: list[str] = []
    for i, image in enumerate(images):
        text = pytesseract.image_to_string(image)
        if text.strip():
            pages.append(text.strip())
    return "\n\n".join(pages)


def process_pdf_to_artifacts(
    pdf_path: str | Path,
    persist_dir: str | Path,
    dpi: int = 300,
) -> str:
    """Convert PDF to images and OCR to text. Persist each, skip if already exists.

    Saves page images under persist_dir/images/page_000.png, etc., and
    extracted text to persist_dir/extracted_text.txt. Reuses cached files when
    present.

    Returns the extracted text (full concatenated OCR output).
    """
    pdf_path = Path(pdf_path)
    persist_dir = Path(persist_dir)
    images_dir = persist_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    text_path = persist_dir / "extracted_text.txt"

    pages = convert_from_path(str(pdf_path), dpi=dpi)
    page_images: list[Path] = []

    for i, image in enumerate(pages):
        img_path = images_dir / f"page_{i:03d}.png"
        page_images.append(img_path)
        if not img_path.exists():
            image.save(str(img_path))
            logger.info("Saved %s", img_path)
        else:
            logger.info("Skipped (exists): %s", img_path)

    if text_path.exists():
        logger.info("Skipped OCR (exists): %s", text_path)
        return text_path.read_text()

    pages_text: list[str] = []
    for img_path in page_images:
        img = Image.open(img_path)
        text = pytesseract.image_to_string(img)
        if text.strip():
            pages_text.append(text.strip())

    full_text = "\n\n".join(pages_text)
    text_path.write_text(full_text)
    logger.info("Saved %s", text_path)
    return full_text
