"""SQLite persistence for tenders, organisation counts, and run history."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .parsing import TenderRow

# All timestamps are stored and compared in IST. The tender portals publish
# closing times in IST, so pinning the clock here keeps "days left" and the
# deadline alerts correct regardless of where the scraper runs (a local Mac
# or a UTC GitHub Actions runner).
IST = ZoneInfo("Asia/Kolkata")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenders (
    portal           TEXT NOT NULL,
    tender_id        TEXT NOT NULL,
    title            TEXT,
    ref_no           TEXT,
    organisation     TEXT,
    published        TEXT,
    closing          TEXT,
    opening          TEXT,
    url              TEXT,
    first_seen       TEXT NOT NULL,
    last_seen        TEXT NOT NULL,
    matched          INTEGER NOT NULL DEFAULT 0,
    tier             TEXT,
    deadline_alerted TEXT,
    PRIMARY KEY (portal, tender_id)
);
CREATE INDEX IF NOT EXISTS idx_tenders_closing ON tenders (closing);
CREATE INDEX IF NOT EXISTS idx_tenders_first_seen ON tenders (first_seen);

CREATE TABLE IF NOT EXISTS org_counts (
    portal  TEXT NOT NULL,
    org     TEXT NOT NULL,
    count   INTEGER NOT NULL,
    updated TEXT NOT NULL,
    PRIMARY KEY (portal, org)
);

CREATE TABLE IF NOT EXISTS runs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    portal   TEXT NOT NULL,
    started  TEXT NOT NULL,
    finished TEXT,
    status   TEXT,
    seen     INTEGER DEFAULT 0,
    new      INTEGER DEFAULT 0,
    error    TEXT
);
"""

# Columns added after v0.1; applied to pre-existing databases at open time.
MIGRATIONS = {
    "tier": "ALTER TABLE tenders ADD COLUMN tier TEXT",
    "deadline_alerted": "ALTER TABLE tenders ADD COLUMN deadline_alerted TEXT",
}

NOW_FORMAT = "%Y-%m-%d %H:%M:%S"
MINUTE_FORMAT = "%Y-%m-%d %H:%M"


def now_string() -> str:
    """Return the current IST time as a sortable second-precision string."""
    return datetime.now(IST).strftime(NOW_FORMAT)


def now_minute() -> str:
    """Return the current IST time to the minute, matching ``closing`` format.

    Used for ``closing`` comparisons: closing times are stored without
    seconds, so comparing against a second-precision now would treat a
    tender closing in the current minute as already closed.
    """
    return datetime.now(IST).strftime(MINUTE_FORMAT)


def _future_minute(days: int) -> str:
    """Return the IST timestamp ``days`` days from now, to the minute."""
    return (datetime.now(IST) + timedelta(days=days)).strftime(MINUTE_FORMAT)


class Database:
    """Thin SQLite wrapper. Create one instance per thread."""

    def __init__(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), timeout=60)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=60000")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after the initial schema to old databases."""
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(tenders)")}
        for column, statement in MIGRATIONS.items():
            if column not in existing:
                self.conn.execute(statement)
        # Created here (not in SCHEMA) so it only runs once the tier column
        # is guaranteed to exist, including on migrated pre-tier databases.
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tenders_tier ON tenders (tier)")

    def close(self) -> None:
        """Close the underlying connection."""
        self.conn.close()

    def is_empty(self) -> bool:
        """Return True when no tenders have ever been stored."""
        row = self.conn.execute("SELECT COUNT(*) AS n FROM tenders").fetchone()
        return row["n"] == 0

    def upsert_tender(self, portal: str, row: TenderRow, tier: str | None) -> bool:
        """Insert or refresh one tender.

        Parameters
        ----------
        portal : str
            Portal id the tender was scraped from.
        row : TenderRow
            Parsed tender fields.
        tier : str or None
            Relevance tier ("product"/"road") or None if not relevant.

        Returns
        -------
        bool
            True when the tender was not previously in the database.
        """
        now = now_string()
        matched = int(tier is not None)
        cursor = self.conn.execute(
            "SELECT 1 FROM tenders WHERE portal = ? AND tender_id = ?",
            (portal, row.tender_id),
        )
        exists = cursor.fetchone() is not None
        if exists:
            # Refresh volatile fields and the tier (keywords may have changed),
            # but never clear an existing deadline alert.
            self.conn.execute(
                """UPDATE tenders SET last_seen = ?, closing = COALESCE(?, closing),
                   url = COALESCE(?, url), matched = ?, tier = ?
                   WHERE portal = ? AND tender_id = ?""",
                (now, row.closing, row.url, matched, tier, portal, row.tender_id),
            )
        else:
            self.conn.execute(
                """INSERT INTO tenders (portal, tender_id, title, ref_no, organisation,
                   published, closing, opening, url, first_seen, last_seen, matched, tier)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    portal,
                    row.tender_id,
                    row.title,
                    row.ref_no,
                    row.organisation,
                    row.published,
                    row.closing,
                    row.opening,
                    row.url,
                    now,
                    now,
                    matched,
                    tier,
                ),
            )
        self.conn.commit()
        return not exists

    def get_org_counts(self, portal: str) -> dict[str, int]:
        """Return the stored organisation tender counts for a portal."""
        rows = self.conn.execute(
            "SELECT org, count FROM org_counts WHERE portal = ?", (portal,)
        ).fetchall()
        return {r["org"]: r["count"] for r in rows}

    def get_org_state(self, portal: str) -> dict[str, tuple[int, str]]:
        """Return ``{org: (count, last_updated)}`` for re-drill decisions."""
        rows = self.conn.execute(
            "SELECT org, count, updated FROM org_counts WHERE portal = ?", (portal,)
        ).fetchall()
        return {r["org"]: (r["count"], r["updated"]) for r in rows}

    def set_org_count(self, portal: str, org: str, count: int) -> None:
        """Store one organisation's current tender count."""
        self.conn.execute(
            """INSERT INTO org_counts (portal, org, count, updated)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (portal, org) DO UPDATE SET count = excluded.count,
               updated = excluded.updated""",
            (portal, org, count, now_string()),
        )
        self.conn.commit()

    def record_run(
        self,
        portal: str,
        started: str,
        status: str,
        seen: int,
        new: int,
        error: str | None = None,
    ) -> None:
        """Append one per-portal scrape outcome to the run history."""
        self.conn.execute(
            """INSERT INTO runs (portal, started, finished, status, seen, new, error)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (portal, started, now_string(), status, seen, new, error),
        )
        self.conn.commit()

    def open_matched_tenders(self, limit: int = 2000) -> list[sqlite3.Row]:
        """Return keyword-matched tenders that have not closed yet.

        Cross-portal duplicates (same tender id) are collapsed, preferring
        the copy that carries a deep-link URL. Product-tier tenders sort
        ahead of road-tier, then newest first.
        """
        return self.conn.execute(
            """SELECT *, MAX(url IS NOT NULL) AS has_url FROM tenders
               WHERE matched = 1 AND (closing IS NULL OR closing >= ?)
               GROUP BY tender_id
               ORDER BY (tier = 'product') DESC, first_seen DESC LIMIT ?""",
            (now_minute(), limit),
        ).fetchall()

    def new_matched_since(self, hours: int) -> list[sqlite3.Row]:
        """Return matched tenders first seen within the last N hours."""
        cutoff = (datetime.now(IST) - timedelta(hours=hours)).strftime(NOW_FORMAT)
        return self.conn.execute(
            """SELECT *, MAX(url IS NOT NULL) AS has_url FROM tenders
               WHERE matched = 1 AND first_seen >= ?
               GROUP BY tender_id ORDER BY (tier = 'product') DESC, first_seen DESC""",
            (cutoff,),
        ).fetchall()

    def tenders_closing_soon(
        self, road_within_days: int, product_within_days: int
    ) -> list[sqlite3.Row]:
        """Return open, not-yet-alerted matched tenders nearing their deadline.

        Product-tier tenders use the (longer) product lead time; all others
        use the road lead time. Cross-portal duplicates are collapsed.

        Parameters
        ----------
        road_within_days : int
            Lead window for road-tier tenders.
        product_within_days : int
            Lead window for product-tier tenders.

        Returns
        -------
        list of sqlite3.Row
            Tenders to alert on, soonest deadline first.
        """
        return self.conn.execute(
            """SELECT *, MAX(url IS NOT NULL) AS has_url FROM tenders
               WHERE matched = 1 AND deadline_alerted IS NULL
                 AND closing IS NOT NULL AND closing >= ?
                 AND (
                   (tier = 'product' AND closing <= ?)
                   OR (tier IS NOT 'product' AND closing <= ?)
                 )
               GROUP BY tender_id
               ORDER BY closing ASC""",
            (
                now_minute(),
                _future_minute(product_within_days),
                _future_minute(road_within_days),
            ),
        ).fetchall()

    def mark_deadline_alerted(self, tender_id: str) -> None:
        """Flag every copy of a tender id as having had its deadline alerted."""
        self.conn.execute(
            "UPDATE tenders SET deadline_alerted = ? WHERE tender_id = ?",
            (now_string(), tender_id),
        )
        self.conn.commit()

    def portal_health(self) -> list[sqlite3.Row]:
        """Return the most recent run per portal."""
        return self.conn.execute(
            """SELECT r.* FROM runs r
               JOIN (SELECT portal, MAX(id) AS max_id FROM runs GROUP BY portal) m
               ON r.portal = m.portal AND r.id = m.max_id
               ORDER BY r.portal"""
        ).fetchall()

    def summary_counts(self) -> dict[str, int]:
        """Return headline totals for the dashboard."""
        total = self.conn.execute("SELECT COUNT(*) AS n FROM tenders").fetchone()["n"]
        now = now_minute()
        open_matched = self.conn.execute(
            """SELECT COUNT(DISTINCT tender_id) AS n FROM tenders
               WHERE matched = 1 AND (closing IS NULL OR closing >= ?)""",
            (now,),
        ).fetchone()["n"]
        open_product = self.conn.execute(
            """SELECT COUNT(DISTINCT tender_id) AS n FROM tenders
               WHERE tier = 'product' AND (closing IS NULL OR closing >= ?)""",
            (now,),
        ).fetchone()["n"]
        return {"total": total, "open_matched": open_matched, "open_product": open_product}

    def count_null_tier_matched(self) -> int:
        """Return how many matched tenders still lack a tier (need backfill)."""
        return self.conn.execute(
            "SELECT COUNT(*) AS n FROM tenders WHERE matched = 1 AND tier IS NULL"
        ).fetchone()["n"]

    def rematch_all(self, matcher) -> int:
        """Recompute matched flag and tier for every stored tender.

        Parameters
        ----------
        matcher : KeywordMatcher
            The matcher built from the current config.

        Returns
        -------
        int
            Number of tenders now flagged as matched.
        """
        rows = self.conn.execute(
            "SELECT portal, tender_id, title, organisation FROM tenders"
        ).fetchall()
        matched_count = 0
        for r in rows:
            tier = matcher.tier(r["title"] or "", r["organisation"] or "")
            matched_count += int(tier is not None)
            self.conn.execute(
                "UPDATE tenders SET matched = ?, tier = ? WHERE portal = ? AND tender_id = ?",
                (int(tier is not None), tier, r["portal"], r["tender_id"]),
            )
        self.conn.commit()
        return matched_count
