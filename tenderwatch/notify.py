"""Phone notification on new matching tenders.

Two delivery paths, chosen at runtime:

* locally, the user's ``push-to-phone`` CLI (which already knows the ntfy
  topic from its own config) is used when present;
* in CI / on a server, where that CLI is absent, an ntfy push is sent
  directly over HTTP using the ``NTFY_TOPIC`` (and optional
  ``NTFY_SERVER``) environment variables.

If neither is available the push is skipped silently.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

import httpx

from .config import Settings

logger = logging.getLogger("tenderwatch")

DEFAULT_NTFY_SERVER = "https://ntfy.sh"


def _build_body(new_matched_titles: list[str], new_matched_total: int, max_titles: int) -> str:
    """Assemble the notification body from new tender titles."""
    shown = [t[:90] for t in new_matched_titles[:max_titles]]
    body_lines = [f"* {t}" for t in shown]
    remainder = new_matched_total - len(shown)
    if remainder > 0:
        body_lines.append(f"... and {remainder} more")
    return "\n".join(body_lines)


def _send_via_cli(command: str, title: str, body: str) -> bool:
    """Send through the local push-to-phone CLI."""
    try:
        subprocess.run(
            [command, "-t", title, "-m", body, "--tag", "motorway"],
            check=True,
            capture_output=True,
            timeout=60,
        )
        logger.info("push sent via CLI: %s", title)
        return True
    except Exception as exc:
        logger.warning("CLI push failed: %s", exc)
        return False


def _send_via_ntfy(topic: str, title: str, body: str) -> bool:
    """Send directly to an ntfy server over HTTP."""
    server = os.environ.get("NTFY_SERVER", DEFAULT_NTFY_SERVER).rstrip("/")
    headers = {"Title": title, "Tags": "motorway"}
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


def send_new_tender_push(
    settings: Settings, new_matched_titles: list[str], new_matched_total: int
) -> bool:
    """Send one summary push for newly found matching tenders.

    Parameters
    ----------
    settings : Settings
        Provides the notify command, enable flag, and title cap.
    new_matched_titles : list of str
        Titles of new keyword-matched tenders from this run.
    new_matched_total : int
        Total count of new matches (may exceed the titles list).

    Returns
    -------
    bool
        True when a push was delivered by either path.
    """
    if not settings.notify_enabled or new_matched_total == 0:
        return False
    title = f"TenderWatch: {new_matched_total} new matching tender(s)"
    body = _build_body(new_matched_titles, new_matched_total, settings.notify_max_titles)

    command = shutil.which(settings.notify_command)
    if command is not None:
        return _send_via_cli(command, title, body)

    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        return _send_via_ntfy(topic, title, body)

    logger.warning("no push channel available (no CLI, no NTFY_TOPIC), skipping")
    return False
