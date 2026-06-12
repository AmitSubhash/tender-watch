"""Dashboard rendering smoke tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from tenderwatch.dashboard import render_dashboard
from tenderwatch.db import IST, Database
from tenderwatch.parsing import TenderRow


def _row(tender_id, title, closing) -> TenderRow:
    return TenderRow(
        tender_id=tender_id,
        title=title,
        ref_no="R/1",
        organisation="PWD",
        published="2026-06-12 10:00",
        closing=closing,
        opening=None,
    )


def test_render_dashboard(settings) -> None:
    db = Database(settings.database_path)
    soon = (datetime.now(IST) + timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
    far = (datetime.now(IST) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
    db.upsert_tender("westbengal", _row("a", "Bitumen emulsion supply", soon), tier="product")
    db.upsert_tender("westbengal", _row("b", "CC road work", far), tier="road")
    db.record_run("westbengal", "2026-06-12 10:00:00", "ok", 2, 2)
    db.close()

    path = render_dashboard(settings)
    page = path.read_text()
    assert "HINCOL TenderWatch" in page
    assert "Bitumen emulsion supply" in page
    assert "PRODUCT" in page
    assert "West Bengal" in page
    assert "&#9733;" in page  # HINCOL plant star
    assert "closing within 7 days" in page


def test_render_escapes_titles(settings) -> None:
    db = Database(settings.database_path)
    far = (datetime.now(IST) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
    db.upsert_tender(
        "westbengal", _row("x", "Road <script>alert(1)</script>", far), tier="road"
    )
    db.close()
    page = render_dashboard(settings).read_text()
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
