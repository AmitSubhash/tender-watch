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
from .notify import send_deadline_push, send_new_tender_push
from .scrape import PortalStats, scrape_portal

logger = logging.getLogger("tenderwatch")


def build_matcher(settings: Settings) -> KeywordMatcher:
    """Construct the tiered keyword matcher from settings."""
    return KeywordMatcher(
        settings.product_keywords,
        settings.road_keywords,
        settings.exclude_keywords,
        settings.match_organisation,
    )


def _acquire_lock(lock_path: Path) -> bool:
    """Atomically create a pid lockfile; return False if another run is alive."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # O_EXCL: atomic "create only if absent", closes the TOCTOU window.
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            other_pid = int(lock_path.read_text().strip())
            os.kill(other_pid, 0)
            return False  # holder still alive
        except (ValueError, ProcessLookupError, PermissionError):
            lock_path.unlink(missing_ok=True)  # stale lock, reclaim
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                return False
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
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
        Suppress phone pushes for this run.

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
        matcher = build_matcher(settings)
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

        db = Database(settings.database_path)
        try:
            # Backfill tiers for any rows predating the tier column (one pass
            # after a schema migration), so the dashboard and alerts are correct.
            if db.count_null_tier_matched() > 0:
                relabelled = db.rematch_all(matcher)
                logger.info("tier backfill: relabelled, %d matched", relabelled)

            render_dashboard(settings)

            new_matched_titles = [t for s in results for t in s.new_matched_titles]
            if baseline:
                logger.info(
                    "baseline run: %d tenders, seeding alert state, no push",
                    sum(s.new for s in results),
                )
            elif not no_notify and new_matched_titles:
                send_new_tender_push(settings, new_matched_titles, len(new_matched_titles))

            # Deadline alerts ("respond at the right time"). On baseline we
            # only seed the alerted state (no push); afterwards each tender
            # that newly enters its deadline window is pushed exactly once.
            closing_soon = db.tenders_closing_soon(
                settings.deadline_road_within_days,
                settings.deadline_product_within_days,
            )
            if closing_soon:
                if not baseline and not no_notify:
                    send_deadline_push(settings, closing_soon)
                for row in closing_soon:
                    db.mark_deadline_alerted(row["tender_id"])
                logger.info("deadline: %d tender(s) flagged closing-soon", len(closing_soon))
        finally:
            db.close()
        return results
    finally:
        lock_path.unlink(missing_ok=True)
