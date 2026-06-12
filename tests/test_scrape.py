"""Scraper adapter tests with a stubbed fetch (no network)."""

from __future__ import annotations

import tenderwatch.scrape as scrape
from tenderwatch.config import PortalConfig
from tenderwatch.db import Database
from tenderwatch.filters import KeywordMatcher

ORG_DIR = """
<table class="list_table"><tr class="list_header"><td>S</td><td>Org</td><td>Count</td></tr>
<tr class="even"><td>1</td><td>Good Org</td>
  <td><a id="DirectLink" href="/nicgep/app?good">3</a></td></tr>
<tr class="odd"><td>2</td><td>Captcha Org</td>
  <td><a id="DirectLink_0" href="/nicgep/app?captcha">5</a></td></tr>
</table>
"""

GOOD_LISTING = """
<table class="list_table">
<tr class="list_header"><td>S</td><td>Pub</td><td>Close</td><td>Open</td><td>Title</td><td>Org</td></tr>
<tr class="even"><td>1</td><td>12-Jun-2026 10:00 AM</td><td>20-Jun-2026 10:00 AM</td>
  <td>21-Jun-2026 10:00 AM</td>
  <td><a id="DirectLink" href="/x">[Bitumen emulsion supply for road]</a> [REF/9][2026_WB_900_1]</td>
  <td>Good Org</td></tr>
</table>
"""

CAPTCHA_PAGE = "<html><body>Please enter captcha</body></html>"


def _portal() -> PortalConfig:
    return PortalConfig(
        id="westbengal",
        name="WB",
        type="gepnic",
        app_url="https://wbtenders.gov.in/nicgep/app",
        enabled=True,
    )


def test_gepnic_zero_row_org_does_not_store_count(settings, monkeypatch) -> None:
    """A captcha/empty org must NOT have its count stored (CRITICAL-2 guard)."""

    def fake_fetch(client, url, _settings):
        if "FrontEndTendersByOrganisation" in url:
            return ORG_DIR
        if "good" in url:
            return GOOD_LISTING
        return CAPTCHA_PAGE  # the "captcha" org returns an unparseable page

    class DummyClient:
        headers: dict = {}

        def close(self) -> None:
            pass

    monkeypatch.setattr(scrape, "fetch", fake_fetch)
    monkeypatch.setattr(scrape, "make_client", lambda s: DummyClient())
    matcher = KeywordMatcher(settings.product_keywords, settings.road_keywords, [])

    stats = scrape.scrape_gepnic_portal(_portal(), settings, matcher, full=True)
    assert stats.status == "ok"

    db = Database(settings.database_path)
    # Good org's tender was stored and flagged product.
    rows = db.open_matched_tenders()
    assert len(rows) == 1
    assert rows[0]["tier"] == "product"
    # Good org count stored; captcha org count NOT stored, so it retries next run.
    state = db.get_org_state("westbengal")
    assert "Good Org" in state
    assert "Captcha Org" not in state
    db.close()
