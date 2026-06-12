# HINCOL TenderWatch — Coverage & Potential-Clients Audit

*Exhaustive audit of Indian road-tender sources (2026-06-13). Purpose: confirm
what the monitor covers, identify genuinely-missed sources, and map the
agencies and contractors that represent HINCOL's potential clients.*

---

## 1. Headline finding

**Almost every road-tender-floating agency in India bids through a portal the
monitor already scrapes.** Across UP, MP, Rajasthan, Punjab, Haryana, Delhi,
Maharashtra, the hill states, Jharkhand, the NE, and the central agencies, the
research repeatedly confirmed the same pattern: the PWDs, state road-development
corporations, expressway authorities, bridge corporations, industrial-area
corporations, urban authorities and rural-roads agencies all publish notices on
their own sites but route **e-bid submission through the state NIC GePNIC portal**
(or the central CPPP for central bodies). Those are exactly the **33 portals**
this tool scrapes.

So the answer to "what did we miss?" is: **very little on the GePNIC ecosystem.**
The genuine gaps are a handful of agencies on *custom* (non-NIC) portals, listed
in Section 3.

## 2. Now covered — 33 portals

- **Central (5):** etenders.gov.in (NHAI, MoRTH, NCRTC), **eprocure.gov.in/eprocure/app
  (DDA + central ministries + ports — added this audit)**, CPPP aggregate (CPSUs),
  defproc (BRO/MES), PMGSY rural roads (nationwide).
- **HINCOL plant states (6):** Maharashtra, UP, Haryana, Tamil Nadu, West Bengal, Assam.
- **22 more states/UTs:** Rajasthan, MP, Punjab, Delhi, Uttarakhand, Himachal, J&K,
  Ladakh, Odisha, Kerala, Jharkhand, Goa, Tripura, the NE states, Chandigarh, A&N, DNH.

This captures the large majority of Indian road-tender *volume*, including
NHAI national highways, state PWD/road-corp work, BRO border roads, and PMGSY
rural roads.

## 3. Genuinely-missed sources (custom portals — not on NIC GePNIC)

These agencies float bitumen-relevant work but on their own/custom platforms, so
the GePNIC adapter cannot reach them. Ranked by HINCOL value:

| Agency | State | Portal | Platform | Why it matters | Effort to add |
|---|---|---|---|---|---|
| **MSRDC** | Maharashtra* | msrdc.in | Custom (MahaOnline) | Mumbai-Pune & **Samruddhi Mahamarg** expressways — top bitumen volume | browser adapter |
| **Gujarat R&B + GSRDC + GIDC** | Gujarat* | rnb / gsrdc / gidc .nprocure.com | (n)Procure (bot-blocked) | entire Gujarat state-road system | browser adapter (n)Procure |
| **NHIDCL** | Central | nhidcl.com/en/tender | Custom | border/NE/hilly national highways | dedicated HTML adapter |
| **MMRDA** | Maharashtra* | etendermmrda.maharashtra.gov.in | Custom (Sify) | Mumbai metro-region roads/flyovers | browser adapter |
| **MIDC** | Maharashtra* | midcindia.org | Custom (PWIMS) | industrial-estate roads, asphalting | browser adapter |
| **Karnataka KPPP** | Karnataka* | kppp.karnataka.gov.in | SPA + **captcha** | state roads | blocked by captcha |
| **AP / Telangana** | AP*, TG | tender.apeprocurement / tender.telangana | Custom (JS popups) | state roads | browser adapter |
| **Chhattisgarh** | CG | eproc.cgstate.gov.in | IBM CHEPS (login) | state roads | login-gated |
| **Bihar** | Bihar | eproc2.bihar.gov.in | Custom (non-GePNIC) | state roads, expressways | dedicated adapter |
| UP Setu Nigam | UP* | bridgecorporationltd.com | Custom | bridges/ROBs (lower bitumen) | low priority |

(* = HINCOL plant state — highest commercial priority.)

**Recommendation:** the highest-value missed source is **Maharashtra MSRDC + Gujarat
(n)Procure**, because both are plant states with massive expressway/state-road
programs on custom portals. These need a browser-based adapter (Playwright in CI,
or a Mac-side camofox job). NHIDCL (border highways, custom HTML) is the most
tractable single add. Karnataka is blocked by a captcha and not worth pursuing.

## 4. Potential clients — AGENCY accounts (buy-side; already visible in-dashboard)

These are the named buyers whose tenders the sales team should watch. All are
**already surfaced in the dashboard** via the covered portals (filter by state /
keyword). A target account list mapped to where their tenders appear:

- **Central:** NHAI, MoRTH, NHIDCL (custom), BRO/DGBR, NRRDA/PMGSY, NCRTC, CPWD.
- **Maharashtra:** PWD, PMRDA, BMC/MCGM, PMC (→ mahatenders); MSRDC, MMRDA, MIDC (custom).
- **Uttar Pradesh:** UP PWD, **UPEIDA (expressways)**, UPSHA (→ etender.up.nic.in); UP Setu Nigam (custom).
- **Madhya Pradesh:** MPRDC, MP PWD (→ mptenders); MPRRDA (→ PMGSY).
- **Rajasthan:** PWD, RSRDC, RSHA, RIICO (all → eproc.rajasthan.gov.in).
- **Punjab:** PWD(B&R), PIDB, Mandi Board (link roads), PUDA/GMADA (→ eproc.punjab.gov.in).
- **Haryana:** HSRDC, PWD(B&R), HSIIDC, HSVP (→ etenders.hry.nic.in / works.haryana.gov.in).
- **Delhi:** PWD Delhi, DSIIDC (→ Delhi portal); DDA, MCD/NDMC (→ central eprocure.gov.in — now covered).
- **Hill/East:** HP PWD + HPRIDC; Uttarakhand PWD + BRIDCUL; J&K PWD(R&B), JKPCC, ERA; Ladakh PWD;
  Jharkhand RCD; Bihar RCD, BSRDCL, BRPNNL (custom portal); Chhattisgarh CGRIDCL, PWD, CGRRDA (custom).

## 5. Potential clients — CONTRACTOR leads (demand-side; the actual bitumen buyers)

The agencies above *specify* bitumen; the EPC/HAM **contractors that win their
projects are the ones that actually purchase it** — HINCOL's most direct sales
targets. These do not float public bitumen tenders (they are buyers), so they are
**business-development leads, not scraper sources.** Curated list of India's major
road contractors (validate against HINCOL's existing customer book):

**Tier 1 — large, national:**
Larsen & Toubro (L&T Construction), Dilip Buildcon, GR Infraprojects, KNR
Constructions, PNC Infratech, Ashoka Buildcon, IRB Infrastructure, Adani Road
Transport, Megha Engineering (MEIL), Montecarlo, Cube Highways (O&M/asset owner),
Welspun Enterprises.

**Tier 2 — mid / fast-growing / regional:**
HG Infra Engineering, Gawar Construction, APCO Infratech, Ceigall India, J Kumar
Infraprojects, Patel Infrastructure, RCC Developers, Rohan Builders, Bharat Road
Network, Sadbhav Engineering, DRA Infracon, Vishvaraj Infrastructure.

**How to use:** when the dashboard surfaces a large road/expressway tender (esp.
NHAI HAM/EPC or a state expressway), the awarded contractor is the buyer to
approach for binder supply — especially for **PPP/concessionaire expressways**
(e.g. Ganga Expressway, Samruddhi) where bitumen is procured at the contractor
level, not as a separate agency tender.

## 6. Bottom line

- Portal coverage is **comprehensive on GePNIC** (33 portals; +1 this audit).
- The real expansion opportunities are **3-4 custom portals** (MSRDC, Gujarat
  nProcure, NHIDCL, MMRDA/MIDC) — all needing a browser-based adapter; MSRDC and
  Gujarat are the priority because they are plant states with the biggest pipelines.
- The biggest *commercial* lever isn't more portals — it's pairing the tender feed
  with the **contractor lead list** (Section 5) so HINCOL targets the firms that
  buy the binder, not just the agencies that specify it.
