"""Phone notification on new matching tenders and approaching deadlines.

Two delivery paths, chosen at runtime:

* locally, the user's ``push-to-phone`` CLI (which already knows the ntfy
  topic from its own config) is used when present;
* in CI / on a server, where that CLI is absent, an ntfy push is sent
  directly over HTTP using the ``NTFY_TOPIC`` (and optional
  ``NTFY_SERVER`` / ``NTFY_TOKEN``) environment variables.

If neither is available the push is skipped silently.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import subprocess

import httpx

from .config import Settings

logger = logging.getLogger("tenderwatch")

DEFAULT_NTFY_SERVER = "https://ntfy.sh"


def _send_via_cli(command: str, title: str, body: str, tag: str) -> bool:
    """Send through the local push-to-phone CLI."""
    try:
        subprocess.run(
            [command, "-t", title, "-m", body, "--tag", tag],
            check=True,
            capture_output=True,
            timeout=60,
        )
        logger.info("push sent via CLI: %s", title)
        return True
    except Exception as exc:
        logger.warning("CLI push failed: %s", exc)
        return False


def _send_via_ntfy(topic: str, title: str, body: str, tag: str) -> bool:
    """Send directly to an ntfy server over HTTP."""
    server = os.environ.get("NTFY_SERVER", DEFAULT_NTFY_SERVER).rstrip("/")
    headers = {"Title": title, "Tags": tag}
    token = os.environ.get("NTFY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = httpx.post(
            f"{server}/{topic}",
            content=body.encode("utf-8"),
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        logger.info("push sent via ntfy: %s", title)
        return True
    except Exception as exc:
        logger.warning("ntfy push failed: %s", exc)
        return False


def _dispatch(settings: Settings, title: str, body: str, tag: str) -> bool:
    """Send one push by whichever channel is available."""
    command = shutil.which(settings.notify_command)
    if command is not None:
        return _send_via_cli(command, title, body, tag)
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        return _send_via_ntfy(topic, title, body, tag)
    logger.warning("no push channel available (no CLI, no NTFY_TOPIC), skipping")
    return False


def _titles_body(titles: list[str], total: int, max_titles: int) -> str:
    """Build a bulleted body from titles with an 'and N more' tail."""
    shown = [t[:90] for t in titles[:max_titles]]
    lines = [f"* {t}" for t in shown]
    remainder = total - len(shown)
    if remainder > 0:
        lines.append(f"... and {remainder} more")
    return "\n".join(lines)


def send_new_tender_push(
    settings: Settings, new_matched_titles: list[str], new_matched_total: int
) -> bool:
    """Send one summary push for newly found matching tenders.

    Parameters
    ----------
    settings : Settings
        Notify settings (enable flag, command, title cap).
    new_matched_titles : list of str
        Titles of new keyword-matched tenders from this run.
    new_matched_total : int
        Total count of new matches (may exceed the titles list).

    Returns
    -------
    bool
        True when a push was delivered.
    """
    if not settings.notify_enabled or new_matched_total == 0:
        return False
    title = f"{settings.dashboard_brand}: {new_matched_total} new tender(s)"
    body = _titles_body(new_matched_titles, new_matched_total, settings.notify_max_titles)
    return _dispatch(settings, title, body, "motorway")


def send_deadline_push(settings: Settings, rows: list[sqlite3.Row]) -> bool:
    """Send one push for relevant tenders whose deadline is approaching.

    This is the "respond at the right time" alert: each tender appears in
    at most one deadline push over its lifetime (the caller marks them).

    Parameters
    ----------
    settings : Settings
        Notify settings.
    rows : list of sqlite3.Row
        Tenders closing soon (each has title, closing, tier).

    Returns
    -------
    bool
        True when a push was delivered.
    """
    if not settings.notify_enabled or not rows:
        return False
    title = f"{settings.dashboard_brand}: {len(rows)} tender(s) closing soon"
    descriptions = []
    for row in rows:
        flag = "[PRODUCT] " if row["tier"] == "product" else ""
        closing = (row["closing"] or "")[:16]
        descriptions.append(f"{flag}{(row['title'] or '')[:80]} (closes {closing})")
    body = _titles_body(descriptions, len(rows), settings.notify_max_titles)
    return _dispatch(settings, title, body, "alarm_clock")
