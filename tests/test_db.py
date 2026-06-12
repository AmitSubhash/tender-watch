"""Database dedup, tiering, and deadline-alert tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from tenderwatch.db import IST, Database
from tenderwatch.filters import KeywordMatcher
from tenderwatch.parsing import TenderRow


def make_row(
    tender_id: str = "2026_TEST_1_1",
    title: str = "CC road work",
    closing: str = "2099-06-20 10:00",
) -> TenderRow:
    return TenderRow(
        tender_id=tender_id,
        title=title,
        ref_no="REF/1",
        organisation="PWD||Division",
        published="2026-06-12 10:00",
        closing=closing,
        opening="2099-06-21 10:00",
    )


def test_upsert_dedup(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.db")
    assert db.is_empty()
    assert db.upsert_tender("portal_a", make_row(), tier="road") is True
    assert db.upsert_tender("portal_a", make_row(), tier="road") is False
    assert len(db.open_matched_tenders()) == 1
    db.close()


def test_cross_portal_dedup_prefers_url(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.db")
    plain = make_row()
    linked = make_row()
    linked.url = "https://eprocure.gov.in/cppp/tendersfullview/x"
    db.upsert_tender("gepnic_portal", plain, tier="road")
    db.upsert_tender("cppp_agg", linked, tier="road")
    rows = db.open_matched_tenders()
    assert len(rows) == 1
    assert rows[0]["url"] is not None
    db.close()


def test_tier_stored_and_counted(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.db")
    db.upsert_tender("p", make_row("a", "Supply of bitumen emulsion"), tier="product")
    db.upsert_tender("p", make_row("b", "CC road work"), tier="road")
    counts = db.summary_counts()
    assert counts["open_matched"] == 2
    assert counts["open_product"] == 1
    db.close()


def test_org_state_roundtrip(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.db")
    db.set_org_count("p", "PWD", 7)
    state = db.get_org_state("p")
    assert state["PWD"][0] == 7
    assert state["PWD"][1]  # has an updated timestamp
    db.close()


def test_closing_soon_respects_tier_window(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.db")
    soon = (datetime.now(IST) + timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    week = (datetime.now(IST) + timedelta(days=8)).strftime("%Y-%m-%d %H:%M")
    # road tender closing in 8 days: outside 5-day road window
    db.upsert_tender("p", make_row("r", "CC road", closing=week), tier="road")
    # product tender closing in 8 days: inside 10-day product window
    db.upsert_tender("p", make_row("pr", "bitumen supply", closing=week), tier="product")
    # road tender closing in 3 days: inside road window
    db.upsert_tender("p", make_row("r2", "road repair", closing=soon), tier="road")
    due = db.tenders_closing_soon(road_within_days=5, product_within_days=10)
    ids = {r["tender_id"] for r in due}
    assert ids == {"pr", "r2"}
    db.close()


def test_deadline_alert_marked_once(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.db")
    soon = (datetime.now(IST) + timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
    db.upsert_tender("p", make_row("x", "road repair", closing=soon), tier="road")
    assert len(db.tenders_closing_soon(5, 10)) == 1
    db.mark_deadline_alerted("x")
    assert len(db.tenders_closing_soon(5, 10)) == 0  # not alerted twice
    db.close()


def test_rematch_sets_tier(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.db")
    db.upsert_tender("p", make_row("a", "Supply of furniture"), tier=None)
    db.upsert_tender("p", make_row("b", "Bitumen emulsion supply"), tier=None)
    matcher = KeywordMatcher(["bitumen", "emulsion"], ["road"], [])
    assert db.rematch_all(matcher) == 1
    assert db.count_null_tier_matched() == 0
    db.close()


def test_migration_adds_columns(tmp_path: Path) -> None:
    import sqlite3

    # Create an old-schema DB without tier / deadline_alerted.
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE tenders (portal TEXT, tender_id TEXT, title TEXT, ref_no TEXT,
           organisation TEXT, published TEXT, closing TEXT, opening TEXT, url TEXT,
           first_seen TEXT, last_seen TEXT, matched INTEGER, PRIMARY KEY (portal, tender_id))"""
    )
    conn.commit()
    conn.close()
    db = Database(path)  # should migrate without error
    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(tenders)")}
    assert "tier" in cols and "deadline_alerted" in cols
    db.close()
