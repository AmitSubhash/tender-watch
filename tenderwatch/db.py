"""SQLite persistence for tenders, organisation counts, and run history."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .parsing import TenderRow

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenders (
    portal       TEXT NOT NULL,
    tender_id    TEXT NOT NULL,
    title        TEXT,
    ref_no       TEXT,
    organisation TEXT,
    published    TEXT,
    closing      TEXT,
    opening      TEXT,
    url          TEXT,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    matched      INTEGER NOT NULL DEFAULT 0,
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

NOW_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_string() -> str:
    """Return the current local time as a sortable string."""
    return datetime.now().strftime(NOW_FORMAT)


class Database:
    """Thin SQLite wrapper. Create one instance per thread."""

    def __init__(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), timeout=60)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=60000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        """Close the underlying connection."""
        self.conn.close()

    def is_empty(self) -> bool:
        """Return True when no tenders have ever been stored."""
        row = self.conn.execute("SELECT COUNT(*) AS n FROM tenders").fetchone()
        return row["n"] == 0

    def upsert_tender(self, portal: str, row: TenderRow, matched: bool) -> bool:
        """Insert or refresh one tender.

        Parameters
        ----------
        portal : str
            Portal id the tender was scraped from.
        row : TenderRow
            Parsed tender fields.
        matched : bool
            Whether the tender matches the configured keywords.

        Returns
        -------
        bool
            True when the tender was not previously in the database.
        """
        now = now_string()
        cursor = self.conn.execute(
            "SELECT 1 FROM tenders WHERE portal = ? AND tender_id = ?",
            (portal, row.tender_id),
        )
        exists = cursor.fetchone() is not None
        if exists:
            self.conn.execute(
                """UPDATE tenders SET last_seen = ?, closing = COALESCE(?, closing),
                   url = COALESCE(?, url) WHERE portal = ? AND tender_id = ?""",
                (now, row.closing, row.url, portal, row.tender_id),
            )
        else:
            self.conn.execute(
                """INSERT INTO tenders (portal, tender_id, title, ref_no, organisation,
                   published, closing, opening, url, first_seen, last_seen, matched)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    int(matched),
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

    def open_matched_tenders(self, limit: int = 1500) -> list[sqlite3.Row]:
        """Return keyword-matched tenders that have not closed yet.

        Cross-portal duplicates (same tender id) are collapsed, preferring
        the copy that carries a deep-link URL.
        """
        now = now_string()
        # SQLite picks bare-column values from the row where the single
        # MIN/MAX aggregate occurs, so each tender_id resolves to its
        # deep-linked copy when one exists.
        return self.conn.execute(
            """SELECT *, MAX(url IS NOT NULL) AS has_url FROM tenders
               WHERE matched = 1 AND (closing IS NULL OR closing >= ?)
               GROUP BY tender_id
               ORDER BY first_seen DESC LIMIT ?""",
            (now, limit),
        ).fetchall()

    def new_matched_since(self, hours: int) -> list[sqlite3.Row]:
        """Return matched tenders first seen within the last N hours."""
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime(NOW_FORMAT)
        return self.conn.execute(
            """SELECT *, MAX(url IS NOT NULL) AS has_url FROM tenders
               WHERE matched = 1 AND first_seen >= ?
               GROUP BY tender_id ORDER BY first_seen DESC""",
            (cutoff,),
        ).fetchall()

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
        matched = self.conn.execute(
            "SELECT COUNT(*) AS n FROM tenders WHERE matched = 1"
        ).fetchone()["n"]
        open_matched = self.conn.execute(
            """SELECT COUNT(DISTINCT tender_id) AS n FROM tenders
               WHERE matched = 1 AND (closing IS NULL OR closing >= ?)""",
            (now_string(),),
        ).fetchone()["n"]
        return {"total": total, "matched": matched, "open_matched": open_matched}

    def rematch_all(self, matcher) -> int:
        """Recompute the matched flag for every stored tender.

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
            matched = matcher.matches(r["title"] or "", r["organisation"] or "")
            matched_count += int(matched)
            self.conn.execute(
                "UPDATE tenders SET matched = ? WHERE portal = ? AND tender_id = ?",
                (int(matched), r["portal"], r["tender_id"]),
            )
        self.conn.commit()
        return matched_count
