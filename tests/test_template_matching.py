from __future__ import annotations

from pathlib import Path

from bot.vision import find_template


def test_find_print_pdf_button(example_page: Path, print_pdf_button: Path) -> None:
    result = find_template(example_page, print_pdf_button)

    assert result.found, (
        f"template not found (confidence={result.confidence:.3f}, "
        f"threshold={result.threshold})"
    )
    assert result.center is not None
    assert result.confidence >= result.threshold
