"""Run orchestration: scrape portals in parallel, render, notify."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .config import Settings
from .dashboard import render_dashboard
from .db import Database
from .filters import KeywordMatcher
from .notify import send_new_tender_push
from .scrape import PortalStats, scrape_portal

logger = logging.getLogger("tenderwatch")


def _acquire_lock(lock_path: Path) -> bool:
    """Create a pid lockfile; returns False when another run is alive."""
    if lock_path.exists():
        try:
            other_pid = int(lock_path.read_text().strip())
            os.kill(other_pid, 0)
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(os.getpid()))
    return True


def run_cycle(
    settings: Settings,
    only_portals: list[str] | None = None,
    full: bool = False,
    no_notify: bool = False,
) -> list[PortalStats]:
    """Execute one full scrape-render-notify cycle.

    Parameters
    ----------
    settings : Settings
        Loaded configuration.
    only_portals : list of str, optional
        Restrict scraping to these portal ids.
    full : bool
        Drill every organisation / page regardless of stored state.
    no_notify : bool
        Suppress the phone push for this run.

    Returns
    -------
    list of PortalStats
        Per-portal outcomes.
    """
    lock_path = settings.database_path.parent / ".tenderwatch.lock"
    if not _acquire_lock(lock_path):
        logger.warning("another run is in progress, exiting")
        return []
    try:
        db = Database(settings.database_path)
        baseline = db.is_empty()
        db.close()
        matcher = KeywordMatcher(
            settings.include_keywords,
            settings.exclude_keywords,
            settings.match_organisation,
        )
        portals = [
            p
            for p in settings.portals
            if p.enabled and (only_portals is None or p.id in only_portals)
        ]
        logger.info("starting cycle: %d portals, baseline=%s", len(portals), baseline)
        results: list[PortalStats] = []
        with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
            futures = {
                pool.submit(scrape_portal, p, settings, matcher, full): p.id for p in portals
            }
            for future in as_completed(futures):
                stats = future.result()
                results.append(stats)
                logger.info(
                    "[%s] %s: seen=%d new=%d",
                    stats.portal,
                    stats.status,
                    stats.seen,
                    stats.new,
                )
        render_dashboard(settings)
        new_matched_titles = [t for s in results for t in s.new_matched_titles]
        if baseline:
            logger.info(
                "baseline run complete (%d tenders), skipping notification",
                sum(s.new for s in results),
            )
        elif not no_notify and new_matched_titles:
            send_new_tender_push(settings, new_matched_titles, len(new_matched_titles))
        return results
    finally:
        lock_path.unlink(missing_ok=True)
