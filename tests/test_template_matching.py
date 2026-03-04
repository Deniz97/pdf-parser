from __future__ import annotations

from pathlib import Path

from tests.vision_utils import find_template


def test_find_print_pdf_button(example_page: Path, print_pdf_button: Path) -> None:
    result = find_template(example_page, print_pdf_button)

    msg = f"template not found (confidence={result.confidence:.3f}, threshold={result.threshold})"
    assert result.found, msg
    assert result.center is not None
    assert result.confidence >= result.threshold
