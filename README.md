# TenderWatch

Automated monitoring of Indian government e-procurement portals for road
and infrastructure tenders. Scrapes captcha-free public listing routes,
stores everything in SQLite, renders a local dashboard, and pushes a
phone notification when new keyword-matched tenders appear.

## What it covers

| Portal | Route used | Status |
|---|---|---|
| etenders.gov.in (central: MoRTH, NHAI, NHIDCL, ministries) | organisation directory drill | working |
| eprocure.gov.in CPPP aggregate (NTPC, ONGC, AAI, ARMY, MES, CPSUs) | paged feed with deep links | working |
| mahatenders.gov.in (Maharashtra, incl. MSRDC orgs) | organisation directory drill | working |
| mptenders.gov.in (Madhya Pradesh) | organisation directory drill | working |
| etender.up.nic.in (Uttar Pradesh, incl. UPPWD) | organisation directory drill | working |
| etenders.kerala.gov.in (Kerala) | organisation directory drill | working |
| tendersodisha.gov.in (Odisha) | organisation directory drill | working |
| tntenders.gov.in (Tamil Nadu) | organisation directory drill | working |
| defproc.gov.in (BRO, MES defence works) | organisation directory drill | working |
| Telangana, AP, Karnataka, Chhattisgarh, Gujarat (nprocure), GeM | JavaScript portals | not yet (needs camofox adapter, see roadmap) |

Notes on indirect coverage: NHAI and MoRTH publish on etenders.gov.in;
BRO and MES publish on defproc.gov.in; many CPSUs (AAI, NTPC, railways
PSUs) flow through the CPPP aggregate feed. PMGSY rural road tenders
appear on the respective state portals. Commercial aggregators
(BidAssist, TenderDetail, Tender247, TendersOnTime, Tata nexarc) are
deliberately not scraped: they are paid services repackaging the same
source data pulled here.

## How it works

1. Each GePNIC portal exposes a captcha-free organisation directory
   (`FrontEndTendersByOrganisation`) listing every organisation with its
   live tender count. The scraper drills into an organisation only when
   its count changed since the last run, so refreshes are cheap (the
   full tender list of an organisation arrives on a single page).
2. The CPPP aggregate feed is paged newest-first; paging stops as soon
   as a full page contains nothing new.
3. Everything seen is upserted into SQLite keyed on (portal, tender id),
   so "new since last run" is exact. Keywords only control highlighting
   and notifications, never what is stored. Cross-portal duplicates are
   collapsed at display time, preferring the copy with a deep link.
4. After each cycle the dashboard regenerates and one summary push goes
   to the phone via `push-to-phone` when new matches appeared.

## Usage

```bash
.venv/bin/python run.py                    # full cycle: scrape, render, notify
.venv/bin/python run.py --baseline         # first pull or full re-pull, no push
.venv/bin/python run.py --portals up       # restrict to one portal
.venv/bin/python run.py --dashboard-only   # re-render HTML only
.venv/bin/python run.py --rematch          # re-apply keywords to stored tenders
open dashboard/index.html                  # view the dashboard
```

## Scheduling (every 2 hours)

```bash
cp launchd/com.amit.tenderwatch.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.amit.tenderwatch.plist
# pause / resume
launchctl unload ~/Library/LaunchAgents/com.amit.tenderwatch.plist
```

Change the cadence by editing `StartInterval` (seconds) in the plist.
The Mac must be awake for runs to fire; launchd coalesces missed runs
to the next wake. The portals update during IST business hours, so a
2 hour interval loses nothing in practice.

## Configuration

Everything lives in `config.yaml`:

- `filters.include_keywords` / `exclude_keywords`: matching is word
  boundary based for ASCII (so `rob` matches "ROB" but not "Robert")
  and substring based for Devanagari. Transliterated Marathi/Hindi
  road terms (rasta, sadak, khadikaran, ...) are included because many
  rural tenders are titled in Romanized Marathi or Hindi.
- `filters.match_organisation`: set true to also match department names
  (catches vaguely titled tenders from road departments, at the cost of
  more noise).
- `scrape.request_delay_seconds`: politeness delay between requests.
- `notify.enabled`: phone push on/off.
- Portal entries can be enabled/disabled individually.

After changing keywords run `run.py --rematch` to re-flag stored tenders.

## Development

```bash
.venv/bin/ruff format . && .venv/bin/ruff check .
PYTHONPATH=. .venv/bin/pytest -q
```

Parser tests run against captured real HTML fragments from the portals,
so a GePNIC markup change shows up as a test failure, and the live page
samples used during development are in `samples/` (gitignored).

## Roadmap

- Telangana / AP / Karnataka / Chhattisgarh / Gujarat adapters via the
  local camofox browser server (these portals require JavaScript).
- GeM bid search adapter (mostly goods/services, lower priority).
- Tender value extraction (requires detail-page fetches; GePNIC detail
  links are session bound and rate limited, so only fetch for matched
  tenders).
- Daily morning digest email draft via the Outlook MCP (draft only).

## Data and etiquette

Only public tender listings published for open dissemination are read.
Requests are serial per portal with a delay, retries are bounded, and
the org-count diff strategy keeps steady-state load to a few dozen
requests per portal per cycle. TLS verification is disabled because
several gov.in hosts serve incomplete certificate chains; nothing
sensitive is transmitted.
