"""Phone notification via the user's existing push-to-phone (ntfy) CLI."""

from __future__ import annotations

import logging
import shutil
import subprocess

from .config import Settings

logger = logging.getLogger("tenderwatch")


def send_new_tender_push(
    settings: Settings, new_matched_titles: list[str], new_matched_total: int
) -> bool:
    """Send one summary push for newly found matching tenders.

    Parameters
    ----------
    settings : Settings
        Provides the notify command and title cap.
    new_matched_titles : list of str
        Titles of new keyword-matched tenders from this run.
    new_matched_total : int
        Total count of new matches (may exceed the titles list).

    Returns
    -------
    bool
        True when the push was handed to the CLI successfully.
    """
    if not settings.notify_enabled or new_matched_total == 0:
        return False
    command = shutil.which(settings.notify_command)
    if command is None:
        logger.warning("notify command '%s' not found, skipping push", settings.notify_command)
        return False
    shown = [t[:90] for t in new_matched_titles[: settings.notify_max_titles]]
    body_lines = [f"* {t}" for t in shown]
    remainder = new_matched_total - len(shown)
    if remainder > 0:
        body_lines.append(f"... and {remainder} more")
    title = f"TenderWatch: {new_matched_total} new matching tender(s)"
    try:
        subprocess.run(
            [command, "-t", title, "-m", "\n".join(body_lines), "--tag", "motorway"],
            check=True,
            capture_output=True,
            timeout=60,
        )
        logger.info("push sent: %s", title)
        return True
    except Exception as exc:
        logger.warning("push failed: %s", exc)
        return False
