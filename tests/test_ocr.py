from __future__ import annotations

from pathlib import Path

from tests.vision_utils import OCR_CROP_REGION, find_text_ocr


def test_find_print_pdf_text(example_page: Path) -> None:
    result = find_text_ocr(example_page, "Print PDF", crop=OCR_CROP_REGION)

    words_list = [w["text"] for w in result.words]
    assert result.found, f"OCR could not find 'Print PDF' — detected words: {words_list}"
    assert result.center is not None
    assert result.confidence > 0
