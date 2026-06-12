#!/usr/bin/env python3
"""Probe candidate tender portal endpoints and report reachability.

Stdlib only so it runs before the venv is ready. Saves response bodies
to samples/ for endpoints that look like tender listings, so adapter
selectors can be designed against real HTML.
"""

from __future__ import annotations

import http.cookiejar
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

SAMPLES_DIR = Path(__file__).parent / "samples"

NIC_LISTING = "?page=FrontEndLatestActiveTenders&service=page"

CANDIDATES: list[tuple[str, str]] = [
    ("etenders_central", f"https://etenders.gov.in/eprocure/app{NIC_LISTING}"),
    ("eprocure_cppp", f"https://eprocure.gov.in/eprocure/app{NIC_LISTING}"),
    ("eprocure_cppp_agg", "https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata"),
    ("mahatenders", f"https://mahatenders.gov.in/nicgep/app{NIC_LISTING}"),
    ("mptenders", f"https://mptenders.gov.in/nicgep/app{NIC_LISTING}"),
    ("kerala", f"https://etenders.kerala.gov.in/nicgep/app{NIC_LISTING}"),
    ("odisha", f"https://tendersodisha.gov.in/nicgep/app{NIC_LISTING}"),
    ("tamilnadu", f"https://tntenders.gov.in/nicgep/app{NIC_LISTING}"),
    ("up", f"https://etender.up.nic.in/nicgep/app{NIC_LISTING}"),
    ("defproc", f"https://defproc.gov.in/nicgep/app{NIC_LISTING}"),
    ("aai_etenders", f"https://etenders.aai.aero/nicgep/app{NIC_LISTING}"),
    ("telangana", "https://tender.telangana.gov.in"),
    ("ap", "https://tender.apeprocurement.gov.in"),
    ("karnataka", "https://eproc.karnataka.gov.in"),
    ("chhattisgarh", "https://eproc.cgstate.gov.in"),
    ("gujarat_nprocure", "https://www.nprocure.com"),
    ("nhai", "https://nhai.gov.in"),
    ("bro", "https://bro.gov.in/tenders.asp"),
    ("mes", "https://mes.gov.in/en/tenders"),
    ("aai_site", "https://www.aai.aero/en/tender/e-tender"),
    ("gem_bidplus", "https://bidplus.gem.gov.in/all-bids"),
    ("dfccil", "https://www.dfccil.com"),
]

MARKERS = [
    "Latest Active Tenders",
    "FrontEndLatestActiveTenders",
    "list_table",
    "Closing Date",
    "Organisation Chain",
    "Tender Title",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "identity",
}


def probe(name: str, url: str) -> dict:
    """Fetch one URL with a fresh cookie session and report what came back."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=ctx),
    )
    req = urllib.request.Request(url, headers=HEADERS)
    result: dict = {"name": name, "url": url}
    try:
        with opener.open(req, timeout=30) as resp:
            body = resp.read(1_500_000)
            text = body.decode("utf-8", errors="replace")
            result["status"] = resp.status
            result["final_url"] = resp.geturl()
            result["bytes"] = len(body)
            result["markers"] = [m for m in MARKERS if m in text]
            if result["markers"]:
                SAMPLES_DIR.mkdir(exist_ok=True)
                (SAMPLES_DIR / f"{name}.html").write_text(text, errors="replace")
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        result["error"] = f"HTTPError {exc.code}"
    except Exception as exc:
        result["status"] = None
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def main() -> None:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda c: probe(*c), CANDIDATES))
    for r in results:
        status = r.get("status")
        markers = r.get("markers", [])
        flag = "LISTING" if markers else ("ok" if status == 200 else "FAIL")
        err = r.get("error", "")
        print(
            f"{r['name']:<20} {str(status):<6} {r.get('bytes', 0):>9} "
            f"{flag:<8} markers={len(markers)} {err}"
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
