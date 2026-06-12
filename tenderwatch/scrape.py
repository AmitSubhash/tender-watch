"""Portal scrapers: the GePNIC organisation-drill adapter and the CPPP feed.

Both adapters are polite by design: requests within a portal are serial
with a configurable delay, and the GePNIC adapter only re-fetches an
organisation's tender list when its advertised tender count changed
since the previous run.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urljoin

import httpx

from .config import PortalConfig, Settings
from .db import IST, NOW_FORMAT, Database, now_string
from .filters import KeywordMatcher
from .parsing import (
    OrgEntry,
    find_next_page_link,
    parse_cppp_listing,
    parse_gepnic_listing,
    parse_org_directory,
)

logger = logging.getLogger("tenderwatch")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

SESSION_ERROR_MARKERS = ("session has timed out", "page=ErrorNotice", "Invalid Request")


@dataclass
class PortalStats:
    """Outcome of scraping one portal in one run."""

    portal: str
    status: str = "ok"
    seen: int = 0
    new: int = 0
    new_matched_titles: list[str] = field(default_factory=list)
    error: str | None = None


def make_client(settings: Settings) -> httpx.Client:
    """Build an httpx client with browser headers and lenient TLS.

    TLS verification is disabled because several gov.in portals serve
    incomplete certificate chains; only public tender listings are read.
    """
    return httpx.Client(
        headers=BROWSER_HEADERS,
        verify=False,
        timeout=settings.timeout_seconds,
        follow_redirects=True,
    )


def fetch(client: httpx.Client, url: str, settings: Settings) -> str:
    """GET a URL with retries and the configured politeness delay.

    Parameters
    ----------
    client : httpx.Client
        Session-bound client (cookies persist across calls).
    url : str
        Absolute URL to fetch.
    settings : Settings
        Provides retry count and per-request delay.

    Returns
    -------
    str
        Response body text.
    """
    last_error: Exception | None = None
    for attempt in range(settings.retries + 1):
        try:
            time.sleep(settings.request_delay_seconds)
            response = client.get(url)
            response.raise_for_status()
            return response.text
        except Exception as exc:
            last_error = exc
            wait = 2.0 * (attempt + 1)
            logger.debug("retry %d for %s after %s", attempt + 1, url, exc)
            time.sleep(wait)
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def _looks_like_session_error(html: str) -> bool:
    lowered = html.lower()
    return any(marker.lower() in lowered for marker in SESSION_ERROR_MARKERS)


def _fetch_org_directory(
    client: httpx.Client, portal: PortalConfig, settings: Settings
) -> list[OrgEntry]:
    """Fetch and parse the full organisation directory for a portal."""
    url = f"{portal.app_url}?page=FrontEndTendersByOrganisation&service=page"
    html = fetch(client, url, settings)
    entries = parse_org_directory(html)
    pages = 1
    next_link = find_next_page_link(html)
    while next_link and pages < settings.max_org_pages:
        html = fetch(client, urljoin(portal.app_url, next_link), settings)
        more = parse_org_directory(html)
        if not more:
            break
        entries.extend(more)
        next_link = find_next_page_link(html)
        pages += 1
    return entries


def scrape_gepnic_portal(
    portal: PortalConfig,
    settings: Settings,
    matcher: KeywordMatcher,
    full: bool = False,
) -> PortalStats:
    """Scrape one GePNIC portal via the organisation directory.

    Parameters
    ----------
    portal : PortalConfig
        Portal entry with ``app_url`` set.
    settings : Settings
        Runtime settings.
    matcher : KeywordMatcher
        Used to flag relevant tenders at insert time.
    full : bool
        When True, drill every organisation regardless of stored counts.

    Returns
    -------
    PortalStats
        Seen/new counts and any error.
    """
    stats = PortalStats(portal=portal.id)
    started = now_string()
    db = Database(settings.database_path)
    client = make_client(settings)
    try:
        orgs = _fetch_org_directory(client, portal, settings)
        if not orgs:
            raise RuntimeError("organisation directory parsed to zero entries")
        # GePNIC validates that a DirectLink drill is reached from the listing
        # page; set the Referer so drills look like real in-session navigation.
        client.headers["Referer"] = (
            f"{portal.app_url}?page=FrontEndTendersByOrganisation&service=page"
        )
        stored = db.get_org_state(portal.id)
        baseline = full or not stored
        redrill_cutoff = (
            datetime.now(IST) - timedelta(hours=settings.force_redrill_hours)
        ).strftime(NOW_FORMAT)
        # Drill an org when: first ever seen, its tender count changed, OR it
        # has not been re-checked within force_redrill_hours. The time-based
        # re-scan catches "churn" (one tender closes as another opens, leaving
        # the count unchanged) that a pure count-diff would silently miss.
        targets = [
            org
            for org in orgs
            if baseline
            or org.name not in stored
            or stored[org.name][0] != org.count
            or stored[org.name][1] < redrill_cutoff
        ]
        logger.info(
            "[%s] %d orgs listed, %d to drill%s",
            portal.id,
            len(orgs),
            len(targets),
            " (baseline)" if baseline else "",
        )
        for org in targets:
            try:
                html = fetch(client, urljoin(portal.app_url, org.link), settings)
                if _looks_like_session_error(html):
                    orgs_refreshed = _fetch_org_directory(client, portal, settings)
                    refreshed = {o.name: o for o in orgs_refreshed}
                    if org.name not in refreshed:
                        logger.warning(
                            "[%s] org '%s' gone after session refresh", portal.id, org.name
                        )
                        continue
                    html = fetch(
                        client, urljoin(portal.app_url, refreshed[org.name].link), settings
                    )
                    if _looks_like_session_error(html):
                        logger.warning(
                            "[%s] org '%s' still session-error; skipping (count not stored)",
                            portal.id,
                            org.name,
                        )
                        continue
                rows = parse_gepnic_listing(html)
                # Defensive pagination: GePNIC org listings return the full
                # list on a single page in practice, but follow any next-page
                # link so a future paginated portal is not silently truncated.
                next_link = find_next_page_link(html)
                pages = 1
                while next_link and pages < settings.max_org_pages:
                    html = fetch(client, urljoin(portal.app_url, next_link), settings)
                    more = parse_gepnic_listing(html)
                    if not more:
                        break
                    rows.extend(more)
                    next_link = find_next_page_link(html)
                    pages += 1
                if not rows:
                    # Zero rows for an org the directory says has tenders means a
                    # captcha / structural change. Do NOT store the count, so the
                    # org is retried next run instead of being frozen out.
                    logger.warning(
                        "[%s] org '%s' (count=%d) parsed 0 rows; not storing count",
                        portal.id,
                        org.name,
                        org.count,
                    )
                    continue
                if len(rows) < org.count:
                    logger.info(
                        "[%s] org '%s': parsed %d of %d tenders",
                        portal.id,
                        org.name,
                        len(rows),
                        org.count,
                    )
                for row in rows:
                    tier = matcher.tier(row.title, row.organisation)
                    is_new = db.upsert_tender(portal.id, row, tier)
                    stats.seen += 1
                    if is_new:
                        stats.new += 1
                        if tier is not None:
                            stats.new_matched_titles.append(row.title)
                db.set_org_count(portal.id, org.name, org.count)
            except Exception as exc:
                logger.warning("[%s] org '%s' failed: %s", portal.id, org.name, exc)
        stats.status = "ok"
    except Exception as exc:
        stats.status = "error"
        stats.error = str(exc)
        logger.error("[%s] portal failed: %s", portal.id, exc)
    finally:
        db.record_run(portal.id, started, stats.status, stats.seen, stats.new, stats.error)
        db.close()
        client.close()
    return stats


def scrape_cppp_feed(
    portal: PortalConfig,
    settings: Settings,
    matcher: KeywordMatcher,
    full: bool = False,
) -> PortalStats:
    """Scrape the CPPP aggregate feed page by page.

    Pages are sorted newest-published first, so paging stops once a full
    page yields zero new tenders (after a minimum page count).

    Parameters
    ----------
    portal : PortalConfig
        Portal entry with ``list_url`` set.
    settings : Settings
        Runtime settings.
    matcher : KeywordMatcher
        Used to flag relevant tenders at insert time.
    full : bool
        When True, always fetch up to ``cppp_max_pages``.

    Returns
    -------
    PortalStats
        Seen/new counts and any error.
    """
    stats = PortalStats(portal=portal.id)
    started = now_string()
    db = Database(settings.database_path)
    client = make_client(settings)
    try:
        for page in range(settings.cppp_max_pages):
            html = fetch(client, f"{portal.list_url}?page={page}", settings)
            rows = parse_cppp_listing(html)
            if not rows:
                break
            new_on_page = 0
            for row in rows:
                tier = matcher.tier(row.title, row.organisation)
                is_new = db.upsert_tender(portal.id, row, tier)
                stats.seen += 1
                if is_new:
                    stats.new += 1
                    new_on_page += 1
                    if tier is not None:
                        stats.new_matched_titles.append(row.title)
            if not full and new_on_page == 0 and page + 1 >= settings.cppp_min_pages:
                break
        stats.status = "ok"
    except Exception as exc:
        stats.status = "error"
        stats.error = str(exc)
        logger.error("[%s] portal failed: %s", portal.id, exc)
    finally:
        db.record_run(portal.id, started, stats.status, stats.seen, stats.new, stats.error)
        db.close()
        client.close()
    return stats


def scrape_portal(
    portal: PortalConfig,
    settings: Settings,
    matcher: KeywordMatcher,
    full: bool = False,
) -> PortalStats:
    """Dispatch to the right adapter for a portal's type."""
    if portal.type == "gepnic":
        return scrape_gepnic_portal(portal, settings, matcher, full)
    if portal.type == "cppp":
        return scrape_cppp_feed(portal, settings, matcher, full)
    return PortalStats(portal=portal.id, status="skipped", error="unsupported type")
