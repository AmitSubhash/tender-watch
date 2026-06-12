#!/usr/bin/env python3
"""TenderWatch CLI entry point.

Usage examples:
    python run.py                        # scrape, render dashboard, notify
    python run.py --baseline             # first full pull, no notifications
    python run.py --portals mahatenders  # one portal only
    python run.py --dashboard-only       # re-render HTML from the database
    python run.py --rematch              # re-apply keywords to stored tenders
"""

from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from tenderwatch.config import load_settings  # noqa: E402
from tenderwatch.dashboard import render_dashboard  # noqa: E402
from tenderwatch.db import Database  # noqa: E402
from tenderwatch.filters import KeywordMatcher  # noqa: E402
from tenderwatch.runner import run_cycle  # noqa: E402


def setup_logging() -> None:
    """Configure rotating file plus console logging."""
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(log_dir / "tenderwatch.log", maxBytes=1_000_000, backupCount=3),
        logging.StreamHandler(),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> int:
    """Parse arguments and run the requested action."""
    parser = argparse.ArgumentParser(description="TenderWatch scraper")
    parser.add_argument("--baseline", action="store_true", help="full pull, no notify")
    parser.add_argument("--full", action="store_true", help="ignore stored org counts")
    parser.add_argument("--no-notify", action="store_true", help="skip phone push")
    parser.add_argument("--portals", type=str, default=None, help="comma-separated ids")
    parser.add_argument("--dashboard-only", action="store_true")
    parser.add_argument("--rematch", action="store_true", help="re-apply keywords")
    args = parser.parse_args()

    setup_logging()
    settings = load_settings()

    if args.rematch:
        matcher = KeywordMatcher(
            settings.include_keywords,
            settings.exclude_keywords,
            settings.match_organisation,
        )
        db = Database(settings.database_path)
        matched = db.rematch_all(matcher)
        db.close()
        logging.info("rematch complete: %d tenders flagged", matched)
        render_dashboard(settings)
        return 0

    if args.dashboard_only:
        path = render_dashboard(settings)
        logging.info("dashboard written to %s", path)
        return 0

    only = args.portals.split(",") if args.portals else None
    results = run_cycle(
        settings,
        only_portals=only,
        full=args.full or args.baseline,
        no_notify=args.no_notify or args.baseline,
    )
    failed = [r for r in results if r.status == "error"]
    return 1 if failed and len(failed) == len(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
