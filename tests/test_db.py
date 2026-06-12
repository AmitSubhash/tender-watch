"""Database dedup and rematch tests."""

from __future__ import annotations

from pathlib import Path

from tenderwatch.db import Database
from tenderwatch.filters import KeywordMatcher
from tenderwatch.parsing import TenderRow


def make_row(tender_id: str = "2026_TEST_1_1", title: str = "Road work") -> TenderRow:
    return TenderRow(
        tender_id=tender_id,
        title=title,
        ref_no="REF/1",
        organisation="PWD||Division",
        published="2026-06-12 10:00",
        closing="2099-06-20 10:00",
        opening="2099-06-21 10:00",
    )


def test_upsert_dedup(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.db")
    assert db.is_empty()
    assert db.upsert_tender("portal_a", make_row(), matched=True) is True
    assert db.upsert_tender("portal_a", make_row(), matched=True) is False
    assert not db.is_empty()
    open_rows = db.open_matched_tenders()
    assert len(open_rows) == 1
    db.close()


def test_cross_portal_dedup_prefers_url(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.db")
    plain = make_row()
    linked = make_row()
    linked.url = "https://eprocure.gov.in/cppp/tendersfullview/x"
    db.upsert_tender("gepnic_portal", plain, matched=True)
    db.upsert_tender("cppp_agg", linked, matched=True)
    rows = db.open_matched_tenders()
    assert len(rows) == 1
    assert rows[0]["url"] is not None
    db.close()


def test_org_counts_roundtrip(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.db")
    db.set_org_count("p", "PWD", 5)
    db.set_org_count("p", "PWD", 7)
    assert db.get_org_counts("p") == {"PWD": 7}
    db.close()


def test_rematch(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.db")
    db.upsert_tender("p", make_row(title="Supply of furniture"), matched=False)
    matcher = KeywordMatcher(["furniture"])
    assert db.rematch_all(matcher) == 1
    db.close()
