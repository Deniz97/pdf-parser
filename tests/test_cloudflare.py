from __future__ import annotations

import pytest
from seleniumbase import SB

from bot import browser

URL = "https://staging.squadhealth.ai/interview"


@pytest.mark.cloudflare
def test_cloudflare_bypass() -> None:
    """Launch browser, navigate to the target URL, and bypass Cloudflare."""
    with SB(uc=True, headed=True) as sb:
        browser.activate(sb, URL)
        browser.skip_cloudflare(sb)

        title = sb.cdp.get_title()
        assert title, "page title is empty after Cloudflare bypass"
