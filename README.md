# HINCOL TenderWatch

Automated monitoring of Indian government e-procurement portals for road,
bituminous, and infrastructure tenders, tuned for **Hindustan Colas
(HINCOL)**: bitumen emulsions, modified bitumen (CRMB/PMB/NRMB),
microsurfacing, cold mix, and allied products.

It scrapes captcha-free public listing routes across **31 portals (nearly
every state and union territory)**, stores everything in SQLite, flags
tenders by relevance tier, renders a live dashboard, and pushes phone
alerts both when new matching tenders appear **and when an open tender's
bid deadline is approaching** so the team can respond in time.

**Live dashboard:** https://amitsubhash.github.io/tender-watch/

## What makes it HINCOL-specific

1. **Two relevance tiers.**
   - **Product** (Tier 1): the tender names a HINCOL product or bituminous
     binder (bitumen, emulsion, CRMB, PMB, microsurfacing, cold mix, VG10/30/40,
     DBM, mastic asphalt, ...). These are the highest-value leads because
     HINCOL's materials are explicitly specified.
   - **Road** (Tier 2): general road / pavement / runway work (highway,
     widening, resurfacing, pothole/road repair, PMGSY, CC road, ...), where
     a bituminous binder is likely needed even if not named. Includes
     transliterated Hindi/Marathi terms (rasta, sadak, khadikaran).
2. **Deadline alerts ("respond at the right time").** When a flagged, still-open
   tender's bid-submission deadline comes within the lead window (10 days for
   product tenders, 5 for road), it triggers a one-time phone push and is
   surfaced in the dashboard's "closing within 7 days" view.
3. **Plant-state awareness.** Portals are tagged by state and HINCOL presence;
   tenders in a HINCOL plant state are starred (lower logistics cost = more
   competitive bids). Plants: Maharashtra, UP, Haryana, Gujarat, Karnataka,
   Tamil Nadu, Andhra Pradesh, West Bengal, Assam.

## Coverage

**31 portals scraped** (GePNIC organisation-directory route + the CPPP
aggregate feed):

- **National:** etenders.gov.in (MoRTH, NHAI, NHIDCL), CPPP aggregate
  (NTPC, AAI, ARMY, MES, CPSUs), defproc (BRO/MES).
- **States/UTs:** Maharashtra, Uttar Pradesh, Haryana, Tamil Nadu, West
  Bengal, Assam, Madhya Pradesh, Odisha, Kerala, Jharkhand, Rajasthan,
  Uttarakhand, Punjab, Himachal Pradesh, Delhi, Jammu & Kashmir, Ladakh,
  Goa, Tripura, Arunachal Pradesh, Manipur, Meghalaya, Mizoram, Nagaland,
  Sikkim, Chandigarh, Andaman & Nicobar, Dadra & Nagar Haveli.

**Not yet scraped** (custom, JavaScript-rendered portals; planned via a
camofox-based adapter): Karnataka, Andhra Pradesh, Gujarat, Telangana,
Chhattisgarh, Bihar. Three of these (Karnataka, AP, Gujarat) are HINCOL
plant states, so they are the top roadmap priority.

Commercial aggregators (BidAssist, TenderDetail, Tender247, etc.) are
deliberately not scraped: they repackage the same source data pulled here.

## How it works

GePNIC portals are scraped two ways, because NIC soft-throttles the
expensive per-organisation drilling at scale (it returns an "ErrorNotice"
page after a burst of drill requests from one IP):

1. **Incremental (every run):** one captcha-free GET per portal to
   `FrontEndAdvancedSearchResult`, which returns the ~20 most recently
   published tenders newest-first, with no per-organisation drilling. This
   is the throttle-resilient monitoring path and works on every GePNIC
   instance tested. It is the right signal for "what was just published."
2. **Backlog (weekly `--full`):** drills every organisation's full tender
   list for completeness. NIC may throttle this; organisations that come
   back as a session/error page are skipped **without storing their count**,
   so they are retried on the next full run — coverage self-heals rather
   than freezing an org out.
3. The CPPP aggregate feed (national CPSUs) is paged newest-first; paging
   stops once a full page contains nothing new.
4. Everything is upserted into SQLite keyed on (portal, tender id), so
   "new since last run" is exact. Keywords only set the relevance tier;
   they never affect what is stored. Cross-portal duplicates collapse at
   display time, preferring the copy with a deep link.
5. All timestamps are handled in **IST** (the portals publish closing times
   in IST), so "days left" and deadline windows are correct regardless of
   where the scraper runs.

## Hosting (GitHub Actions + Pages)

Runs entirely in the cloud via `.github/workflows/tenderwatch.yml`:

- **Scrape cadence:** every 3 hours (cron `0 */3 * * *`), plus a **weekly
  full re-scan** Sunday 03:00 IST that re-drills every organisation as a
  safety net, plus a manual "Run workflow" button.
- **Database persistence:** the SQLite DB is restored from and saved to a
  force-pushed `data` branch each run (one commit, no history bloat). The
  restore verifies the DB is non-empty and passes `PRAGMA integrity_check`
  before use, and the persist step refuses to overwrite the branch with a
  DB under 50 rows — so a transient failure can never wipe the history.
- **Dashboard:** published to GitHub Pages after every run; self-refreshes
  every 15 minutes in the browser.
- **Phone alerts from the cloud:** new-tender and deadline pushes use the
  `NTFY_TOPIC` repository secret (`gh secret set NTFY_TOPIC`).

GitHub disables scheduled workflows after 60 days with no repo commits;
the auto-commits to the `data` branch and the manual Run button keep it
alive.

## Usage

```bash
.venv/bin/python run.py                 # full cycle: scrape, render, alert
.venv/bin/python run.py --full          # re-drill every org regardless of counts
.venv/bin/python run.py --portals rajasthan,goa
.venv/bin/python run.py --dashboard-only
.venv/bin/python run.py --rematch       # re-apply keyword tiers to stored tenders
open dashboard/index.html
```

## Configuration

Everything lives in `config.yaml`:

- `filters.product_keywords` / `road_keywords` / `exclude_keywords`: matching
  is word-boundary based for ASCII (so `rob` matches "ROB" not "Robert") and
  substring based for Devanagari. After editing, run `run.py --rematch`.
- `deadline.product_within_days` / `road_within_days`: deadline-alert lead times.
- `scrape.force_redrill_hours`, `request_delay_seconds`, `max_workers`.
- Portals can be enabled/disabled individually and carry `state` + `hincol`
  (plant/depot/national) tags.

## Development

```bash
.venv/bin/ruff format . && .venv/bin/ruff check .
PYTHONPATH=. .venv/bin/pytest -q     # 27 tests: parsing, db, tiers, deadline, scrape, dashboard, notify
```

Parser and adapter tests run against captured real portal HTML, so a
GePNIC markup change surfaces as a test failure.

## Roadmap

- **camofox adapter** for the JavaScript portals (Karnataka, AP, Gujarat —
  all HINCOL plant states — plus Telangana, Chhattisgarh, Bihar).
- Tender value extraction for matched tenders (prioritise large contracts).
- CSV / Excel export for the procurement team.
- Daily morning digest email (draft-only).

## Data and etiquette

Only public tender listings are read. Requests are serial per portal with
a delay, retries are bounded, and the count-diff strategy keeps steady-state
load to a few dozen requests per portal per cycle. TLS verification is
disabled because several gov.in hosts serve incomplete certificate chains;
nothing sensitive is transmitted.
