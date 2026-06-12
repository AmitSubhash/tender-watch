"""Portal scrapers: the GePNIC adapter and the CPPP aggregate feed.

The GePNIC adapter has two modes. Normal runs use the captcha-free
"tenders by date" listing (recent tenders, one request per portal) which
is resilient to NIC's rate-limiting. Full runs (``--full``, scheduled
weekly) additionally drill every organisation for the complete backlog;
NIC soft-throttles drilling at scale, so the drill is best-effort and any
throttled organisation is retried on the next full run. Both adapters are
polite: requests within a portal are serial with a configurable delay.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from .config import PortalConfig, Settings
from .db import Database, now_string
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


def _ingest_rows(
    db: Database, portal_id: str, rows, matcher: KeywordMatcher, stats: PortalStats
) -> None:
    """Upsert parsed tender rows, updating seen/new stats and matched titles."""
    for row in rows:
        tier = matcher.tier(row.title, row.organisation)
        is_new = db.upsert_tender(portal_id, row, tier)
        stats.seen += 1
        if is_new:
            stats.new += 1
            if tier is not None:
                stats.new_matched_titles.append(row.title)


def _fetch_recent_tenders(
    client: httpx.Client, portal: PortalConfig, settings: Settings
) -> list:
    """Fetch the captcha-free advanced-search listing (recent tenders).

    This is the throttle-resilient incremental route: one GET per portal,
    no per-organisation DirectLink drilling (which NIC rate-limits at
    scale). ``FrontEndAdvancedSearchResult`` returns the ~20 most recently
    published tenders across all organisations, newest first, and works on
    every GePNIC instance tested (unlike ``FrontEndListTendersbyDate``,
    which several portals have disabled).
    """
    url = f"{portal.app_url}?page=FrontEndAdvancedSearchResult&service=page"
    return parse_gepnic_listing(fetch(client, url, settings))


def _drill_all_orgs(
    client: httpx.Client,
    portal: PortalConfig,
    settings: Settings,
    matcher: KeywordMatcher,
    db: Database,
    stats: PortalStats,
) -> None:
    """Drill every organisation's full tender list (the deep backlog pass).

    Expensive: one request per organisation. NIC soft-throttles this at
    scale, so it is a best-effort weekly pass. Organisations that come back
    as a session/error page are skipped WITHOUT storing their count, so they
    are retried on the next full run rather than frozen out.
    """
    orgs = _fetch_org_directory(client, portal, settings)
    if not orgs:
        raise RuntimeError("organisation directory parsed to zero entries")
    client.headers["Referer"] = (
        f"{portal.app_url}?page=FrontEndTendersByOrganisation&service=page"
    )
    logger.info("[%s] full drill: %d orgs", portal.id, len(orgs))
    for org in orgs:
        try:
            html = fetch(client, urljoin(portal.app_url, org.link), settings)
            if _looks_like_session_error(html):
                refreshed = {o.name: o for o in _fetch_org_directory(client, portal, settings)}
                if org.name not in refreshed:
                    continue
                html = fetch(
                    client, urljoin(portal.app_url, refreshed[org.name].link), settings
                )
                if _looks_like_session_error(html):
                    logger.warning("[%s] org '%s' throttled; skipping", portal.id, org.name)
                    continue
            rows = parse_gepnic_listing(html)
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
                logger.warning(
                    "[%s] org '%s' (count=%d) parsed 0 rows; not storing count",
                    portal.id,
                    org.name,
                    org.count,
                )
                continue
            _ingest_rows(db, portal.id, rows, matcher, stats)
            db.set_org_count(portal.id, org.name, org.count)
        except Exception as exc:
            logger.warning("[%s] org '%s' failed: %s", portal.id, org.name, exc)


def scrape_gepnic_portal(
    portal: PortalConfig,
    settings: Settings,
    matcher: KeywordMatcher,
    full: bool = False,
) -> PortalStats:
    """Scrape one GePNIC portal.

    Normal runs use the cheap, captcha-free "by date" listing (recent
    tenders, one request, resilient to NIC throttling). Full runs (``--full``,
    scheduled weekly) additionally drill every organisation for the complete
    backlog.

    Parameters
    ----------
    portal : PortalConfig
        Portal entry with ``app_url`` set.
    settings : Settings
        Runtime settings.
    matcher : KeywordMatcher
        Used to flag relevant tenders at insert time.
    full : bool
        When True, also run the deep per-organisation backlog drill.

    Returns
    -------
    PortalStats
        Seen/new counts and any error.
    """
    stats = PortalStats(portal=portal.id)
    started = now_string()
    db = Database(settings.database_path)
    client = make_client(settings)
    recent_ok = False
    try:
        # Incremental every run: recent tenders, drill-free and captcha-free.
        try:
            recent = _fetch_recent_tenders(client, portal, settings)
            _ingest_rows(db, portal.id, recent, matcher, stats)
            recent_ok = True
            logger.info("[%s] recent: %d rows, %d new", portal.id, len(recent), stats.new)
        except Exception as exc:
            stats.error = f"recent-listing fetch failed: {exc}"
            logger.warning("[%s] recent listing failed: %s", portal.id, exc)

        # Deep backlog only on demand (weekly): per-org drilling at scale.
        if full:
            _drill_all_orgs(client, portal, settings, matcher, db, stats)

        # "ok" if the cheap listing loaded (even with zero recent tenders) or we
        # ingested rows from the drill; "error" only if the portal gave nothing.
        stats.status = "ok" if (recent_ok or stats.seen > 0) else "error"
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
