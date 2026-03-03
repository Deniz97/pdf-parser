from __future__ import annotations

from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent


@pytest.fixture
def example_page() -> Path:
    p = TESTS_DIR / "example-page.png"
    assert p.exists(), f"fixture image missing: {p}"
    return p


@pytest.fixture
def print_pdf_button() -> Path:
    p = TESTS_DIR / "print-pdf-button.png"
    assert p.exists(), f"fixture image missing: {p}"
    return p
