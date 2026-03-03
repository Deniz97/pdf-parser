from __future__ import annotations

from pathlib import Path

from bot.vision import OCR_CROP_REGION, find_text_ocr


def test_find_print_pdf_text(example_page: Path) -> None:
    result = find_text_ocr(example_page, "Print PDF", crop=OCR_CROP_REGION)

    assert result.found, (
        f"OCR could not find 'Print PDF' — detected words: "
        f"{[w['text'] for w in result.words]}"
    )
    assert result.center is not None
    assert result.confidence > 0
