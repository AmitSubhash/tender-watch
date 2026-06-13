"""HTML parsing for GePNIC listing tables and the CPPP aggregate feed.

GePNIC (the NIC e-procurement platform behind etenders.gov.in and most
state portals) renders server-side Apache Tapestry pages. Two page types
matter here:

* the organisation directory (``FrontEndTendersByOrganisation``): rows of
  ``serial | organisation name | tender count`` where the count is an
  anchor whose session-bound href lists that organisation's tenders;
* tender listing tables: rows of ``serial | e-published | closing |
  opening | title/ref/tender-id | organisation chain``.

The CPPP aggregate feed at eprocure.gov.in/cppp is a plain HTML table
with stable deep links per tender.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

TENDER_ID_RE = re.compile(r"\d{4}_\w+_\d+_\d+")
BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")
GEPNIC_DATE_FORMAT = "%d-%b-%Y %I:%M %p"
ISO_MINUTE_FORMAT = "%Y-%m-%d %H:%M"


@dataclass
class TenderRow:
    """One tender as parsed from a listing table."""

    tender_id: str
    title: str
    ref_no: str
    organisation: str
    published: str | None
    closing: str | None
    opening: str | None
    url: str | None = None


@dataclass
class OrgEntry:
    """One organisation row from the GePNIC organisation directory."""

    name: str
    link: str
    count: int


def parse_gepnic_datetime(text: str) -> str | None:
    """Parse a GePNIC timestamp into a sortable ISO-like string.

    Parameters
    ----------
    text : str
        Raw cell text such as ``"12-Jun-2026 10:00 AM"``.

    Returns
    -------
    str or None
        ``"YYYY-MM-DD HH:MM"`` (24h) or None if the text is not a date.
    """
    cleaned = " ".join(text.split())
    try:
        return datetime.strptime(cleaned, GEPNIC_DATE_FORMAT).strftime(ISO_MINUTE_FORMAT)
    except ValueError:
        return None


def fallback_tender_id(*parts: str | None) -> str:
    """Build a deterministic id for rows that lack a GePNIC tender id.

    Parameters
    ----------
    *parts : str or None
        Any identifying fields (title, ref, closing date).

    Returns
    -------
    str
        ``"hash_<16 hex chars>"`` stable across runs for identical input.
    """
    digest = hashlib.sha1("|".join(p or "" for p in parts).encode()).hexdigest()
    return f"hash_{digest[:16]}"


def parse_org_directory(html: str) -> list[OrgEntry]:
    """Extract organisation rows from a FrontEndTendersByOrganisation page.

    Parameters
    ----------
    html : str
        Full page HTML.

    Returns
    -------
    list of OrgEntry
        One entry per organisation that currently has live tenders.
    """
    soup = BeautifulSoup(html, "lxml")
    entries: list[OrgEntry] = []
    for row in soup.select("table.list_table tr"):
        classes = row.get("class") or []
        if "even" not in classes and "odd" not in classes:
            continue
        cells = row.find_all("td")
        if len(cells) != 3:
            continue
        anchor = cells[2].find("a", href=True)
        if anchor is None:
            continue
        count_text = re.sub(r"[^\d]", "", anchor.get_text())
        if not count_text:
            continue
        name = cells[1].get_text(" ", strip=True)
        entries.append(OrgEntry(name=name, link=str(anchor["href"]), count=int(count_text)))
    return entries


def parse_gepnic_listing(html: str) -> list[TenderRow]:
    """Extract tender rows from any GePNIC 6-column listing table.

    Parameters
    ----------
    html : str
        Full page HTML of an organisation tender list (or similar listing).

    Returns
    -------
    list of TenderRow
        Parsed tenders; rows without parseable dates are skipped.

    Example
    -------
    >>> rows = parse_gepnic_listing(page_html)
    >>> rows[0].tender_id
    '2026_MCGM_1308095_1'
    """
    soup = BeautifulSoup(html, "lxml")
    rows: list[TenderRow] = []
    for row in soup.select("table.list_table tr"):
        classes = row.get("class") or []
        if "even" not in classes and "odd" not in classes:
            continue
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        published = parse_gepnic_datetime(cells[1].get_text(strip=True))
        closing = parse_gepnic_datetime(cells[2].get_text(strip=True))
        opening = parse_gepnic_datetime(cells[3].get_text(strip=True))
        if published is None and closing is None:
            continue
        title_cell = next((c for c in cells[4:] if TENDER_ID_RE.search(c.get_text())), None)
        if title_cell is None:
            continue
        cell_text = title_cell.get_text(" ", strip=True)
        id_matches = TENDER_ID_RE.findall(cell_text)
        brackets = BRACKET_RE.findall(cell_text)
        anchor = title_cell.find("a")
        title = (anchor.get_text(" ", strip=True) if anchor else cell_text).strip("[] ")
        ref_parts = [
            b.strip()
            for b in brackets
            if b.strip() != title and not TENDER_ID_RE.fullmatch(b.strip())
        ]
        org_cell_index = cells.index(title_cell) + 1
        organisation = (
            cells[org_cell_index].get_text(" ", strip=True)
            if org_cell_index < len(cells)
            else ""
        )
        tender_id = (
            id_matches[-1]
            if id_matches
            else fallback_tender_id(
                title, ref_parts[0] if ref_parts else None, closing, organisation
            )
        )
        rows.append(
            TenderRow(
                tender_id=tender_id,
                title=title,
                ref_no=", ".join(ref_parts),
                organisation=organisation,
                published=published,
                closing=closing,
                opening=opening,
            )
        )
    return rows


def parse_cppp_listing(
    html: str, base_url: str = "https://eprocure.gov.in"
) -> list[TenderRow]:
    """Extract tender rows from the CPPP aggregate feed table.

    Parameters
    ----------
    html : str
        Full page HTML of a ``cpppdata`` page.
    base_url : str
        Origin used to absolutise relative deep links.

    Returns
    -------
    list of TenderRow
        Parsed tenders with stable deep-link URLs where available.
    """
    soup = BeautifulSoup(html, "lxml")
    rows: list[TenderRow] = []
    for row in soup.select("tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        published = parse_gepnic_datetime(cells[1].get_text(strip=True))
        closing = parse_gepnic_datetime(cells[2].get_text(strip=True))
        opening = parse_gepnic_datetime(cells[3].get_text(strip=True))
        if published is None and closing is None:
            continue
        title_cell = cells[4]
        anchor = title_cell.find("a", href=True)
        title = anchor.get_text(" ", strip=True) if anchor else ""
        url = urljoin(base_url, str(anchor["href"])) if anchor else None
        # Only keep absolute http(s) links; drop javascript:/data:/protocol-
        # relative hrefs so they cannot become a clickable payload downstream.
        if url is not None and not url.startswith(("http://", "https://")):
            url = None
        cell_text = title_cell.get_text(" ", strip=True)
        id_matches = TENDER_ID_RE.findall(cell_text)
        tender_id = id_matches[-1] if id_matches else fallback_tender_id(title, closing)
        tail = cell_text.replace(title, "", 1)
        if id_matches:
            tail = tail.replace(id_matches[-1], "")
        ref_no = tail.strip(" /")
        organisation = cells[5].get_text(" ", strip=True)
        rows.append(
            TenderRow(
                tender_id=tender_id,
                title=title or cell_text[:200],
                ref_no=ref_no,
                organisation=organisation,
                published=published,
                closing=closing,
                opening=opening,
                url=url,
            )
        )
    return rows


def _msrdc_date(text: str, end_of_day: bool = False) -> str | None:
    """Convert an MSRDC ``DD/MM/YYYY`` date to the stored minute format."""
    try:
        dt = datetime.strptime(text.strip(), "%d/%m/%Y")
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%d ") + ("23:59" if end_of_day else "00:00")


def parse_msrdc_listing(html: str, base_url: str = "https://msrdc.in") -> list[TenderRow]:
    """Parse the MSRDC (Maharashtra State Road Development Corp) tender grid.

    MSRDC publishes a server-rendered ASP.NET table (``SitePH_grdTendersList``)
    with columns: Sr.No, Department, Tender No, Tender Name, Publication Date,
    Last Submission Date, File Size, View/Download. Dates are ``DD/MM/YYYY``.

    Parameters
    ----------
    html : str
        Full page HTML of TenderView.aspx.
    base_url : str
        Origin used to absolutise the download link.

    Returns
    -------
    list of TenderRow
        Parsed MSRDC tenders (organisation prefixed "MSRDC").
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id=lambda v: bool(v) and "grdTendersList" in v)
    rows: list[TenderRow] = []
    if table is None:
        return rows
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 7:
            continue
        published = _msrdc_date(cells[4].get_text(strip=True))
        closing = _msrdc_date(cells[5].get_text(strip=True), end_of_day=True)
        if published is None and closing is None:
            continue  # header / non-data row
        department = cells[1].get_text(" ", strip=True)
        tender_no = cells[2].get_text(" ", strip=True)
        title = cells[3].get_text(" ", strip=True)
        if not title:
            continue
        anchor = cells[-1].find("a", href=True)
        url = urljoin(base_url, str(anchor["href"])) if anchor else None
        if url is not None and not url.startswith(("http://", "https://")):
            url = None
        rows.append(
            TenderRow(
                tender_id=fallback_tender_id(tender_no, title, "msrdc"),
                title=title,
                ref_no=tender_no,
                organisation=f"MSRDC - {department}" if department else "MSRDC",
                published=published,
                closing=closing,
                opening=None,
                url=url,
            )
        )
    return rows


def find_next_page_link(html: str) -> str | None:
    """Find a "Next" pagination link on a GePNIC listing page, if any.

    Parameters
    ----------
    html : str
        Full page HTML.

    Returns
    -------
    str or None
        The href of the next-page anchor, or None when there is none.
    """
    soup = BeautifulSoup(html, "lxml")
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(strip=True)
        if text in {"Next", "Next >", ">", ">>"}:
            return str(anchor["href"])
        img = anchor.find("img", alt=True)
        if img is not None and "next" in str(img["alt"]).lower():  # type: ignore[index]
            return str(anchor["href"])
    return None
