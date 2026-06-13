"""Static HTML dashboard generation from the tender database.

Charts are rendered as inline SVG generated server-side from the data, so
the dashboard is fully self-contained (no JavaScript chart library, no CDN)
and renders identically on GitHub Pages and in a screenshot.
"""

from __future__ import annotations

import html
import math
import sqlite3
from collections import Counter
from datetime import datetime, timedelta

from .config import PortalConfig, Settings
from .db import IST, NOW_FORMAT, Database

# ---------------------------------------------------------------------------
# colour system
# ---------------------------------------------------------------------------
C_INK = "#14233a"
C_MUTED = "#64748b"
C_ACCENT = "#0b5fa5"
C_PRODUCT = "#c2410c"
C_ROAD = "#64748b"
C_RED = "#dc2626"
C_AMBER = "#d97706"
C_GREEN = "#059669"
C_GRID = "#e7edf4"

# Quick keyword-filter chips shown on the dashboard. Each is (label, regex
# tested case-insensitively against the tender title). Tweak freely.
KEYWORD_CHIPS = [
    ("Runway", r"runway"),
    ("Taxiway", r"taxiway"),
    ("Asphalt", r"asphalt"),
    ("Road", r"\broad"),
    ("Pot hole", r"pot\s*hole"),
    ("Repair", r"repair"),
    ("Surfacing", r"surfac"),
    ("Bitumen", r"bitumen|bituminous"),
    ("PMB", r"\bp\.?m\.?b\b|modified bitumen|crmb"),
    ("Emulsion", r"emulsion"),
]


def _keyword_chip_html() -> str:
    """Render the keyword quick-filter chips."""
    return "".join(
        f'<button class="kwchip" data-rx="{html.escape(rx)}">{html.escape(lbl)}</button>'
        for lbl, rx in KEYWORD_CHIPS
    )


def _days_left(closing: str | None, now: datetime) -> float | None:
    """Return days until closing (may be negative), or None if unparseable."""
    if not closing:
        return None
    try:
        closing_dt = datetime.strptime(closing, "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    except ValueError:
        return None
    return (closing_dt - now).total_seconds() / 86400


def _urgency_colour(days: float) -> str:
    return C_RED if days < 3 else (C_AMBER if days < 7 else C_ACCENT)


def _svg_closing_histogram(rows: list[sqlite3.Row], now: datetime) -> str:
    """Bars of how many open matched tenders close on each of the next 14 days."""
    horizon = 14
    buckets = [0] * horizon
    for r in rows:
        d = _days_left(r["closing"], now)
        if d is not None and 0 <= d < horizon:
            buckets[int(d)] += 1
    peak = max(buckets) or 1
    w, h, pad_b, pad_l = 360, 150, 22, 26
    plot_h = h - pad_b - 8
    bar_w = (w - pad_l - 8) / horizon
    bars = []
    for i, count in enumerate(buckets):
        bh = (count / peak) * plot_h
        x = pad_l + i * bar_w
        y = 8 + plot_h - bh
        colour = _urgency_colour(i + 0.5)
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w - 3:.1f}" height="{bh:.1f}" '
            f'rx="2" fill="{colour}"><title>{count} closing in {i}-{i + 1}d</title></rect>'
        )
        if count:
            bars.append(
                f'<text x="{x + (bar_w - 3) / 2:.1f}" y="{y - 3:.1f}" font-size="9" '
                f'fill="{C_MUTED}" text-anchor="middle">{count}</text>'
            )
    for lbl in (0, 7, 13):
        x = pad_l + lbl * bar_w + (bar_w - 3) / 2
        bars.append(
            f'<text x="{x:.1f}" y="{h - 6}" font-size="9" fill="{C_MUTED}" '
            f'text-anchor="middle">{lbl}d</text>'
        )
    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
        f'aria-label="tenders closing per day">{"".join(bars)}</svg>'
    )


def _svg_state_bars(state_counts: list[tuple[str, int, bool]]) -> str:
    """Horizontal bars of the top states by open matched tender count.

    Each item is (state, count, is_plant_state).
    """
    top = state_counts[:11]
    peak = max((c for _, c, _ in top), default=1)
    row_h, w, label_w = 18, 360, 118
    h = len(top) * row_h + 6
    bar_max = w - label_w - 34
    parts = []
    for i, (state, count, is_plant) in enumerate(top):
        y = i * row_h + 4
        bw = max(2, (count / peak) * bar_max)
        colour = C_PRODUCT if is_plant else C_ACCENT
        star = " ★" if is_plant else ""
        parts.append(
            f'<text x="0" y="{y + 11}" font-size="10.5" fill="{C_INK}">'
            f"{html.escape(state[:16])}{star}</text>"
            f'<rect x="{label_w}" y="{y + 2}" width="{bw:.1f}" height="{row_h - 7}" '
            f'rx="2" fill="{colour}"/>'
            f'<text x="{label_w + bw + 4:.1f}" y="{y + 11}" font-size="10" '
            f'fill="{C_MUTED}">{count}</text>'
        )
    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
        f'aria-label="top states by open tenders">{"".join(parts)}</svg>'
    )


def _svg_tier_donut(product: int, road: int) -> str:
    """Donut showing the product vs road split of open matched tenders."""
    total = product + road or 1
    frac = product / total
    r, cx, cy, sw = 46, 60, 60, 18
    circ = 2 * math.pi * r
    prod_len = frac * circ
    return f"""<svg viewBox="0 0 240 120" width="100%" role="img" aria-label="tier split">
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{C_ROAD}" stroke-width="{sw}"/>
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{C_PRODUCT}" stroke-width="{sw}"
    stroke-dasharray="{prod_len:.1f} {circ - prod_len:.1f}" stroke-dashoffset="{circ / 4:.1f}"
    transform="rotate(-90 {cx} {cy})" stroke-linecap="butt"/>
  <text x="{cx}" y="{cy - 2}" font-size="20" font-weight="700" fill="{C_PRODUCT}"
    text-anchor="middle">{product}</text>
  <text x="{cx}" y="{cy + 14}" font-size="9" fill="{C_MUTED}" text-anchor="middle">product</text>
  <g font-size="11.5" fill="{C_INK}">
    <rect x="130" y="44" width="11" height="11" rx="2" fill="{C_PRODUCT}"/>
    <text x="147" y="53">Product {product}</text>
    <rect x="130" y="64" width="11" height="11" rx="2" fill="{C_ROAD}"/>
    <text x="147" y="73">Road {road}</text>
  </g>
</svg>"""


def _days_cell(days: float | None) -> str:
    if days is None:
        return '<td class="days muted">?</td>'
    if days < 0:
        return '<td class="days muted">closed</td>'
    css = "red" if days < 3 else ("amber" if days < 7 else "green")
    return f'<td class="days {css}">{days:.0f}d</td>'


def _tender_row(
    row: sqlite3.Row, new_cutoff: str, now: datetime, meta: dict[str, PortalConfig]
) -> str:
    title = html.escape(row["title"] or "(untitled)")
    portal_meta = meta.get(row["portal"])
    # Every row gets a link: a stable deep link where we have one (CPPP/MSRDC),
    # otherwise the portal's search page (GePNIC detail links are session-bound,
    # so the user pastes the visible tender id there).
    deep = (
        row["url"]
        if row["url"] and str(row["url"]).startswith(("http://", "https://"))
        else None
    )
    if deep:
        link = deep
    elif portal_meta and portal_meta.app_url:
        link = f"{portal_meta.app_url}?page=FrontEndAdvancedSearch&service=page"
    elif portal_meta and portal_meta.list_url:
        link = portal_meta.list_url
    else:
        link = None
    title_html = (
        f'<a href="{html.escape(link)}" target="_blank" rel="noopener">{title}</a>'
        if link
        else title
    )
    ref = html.escape(row["ref_no"] or "")
    tender_id = html.escape(row["tender_id"])
    org = html.escape(row["organisation"] or "")
    state = portal_meta.state if portal_meta else ""
    is_plant = bool(portal_meta and portal_meta.hincol == "plant")
    state_html = f'<span class="state">{html.escape(state)}</span>'
    if is_plant:
        state_html += ' <span class="plant" title="HINCOL plant state">&#9733;</span>'
    is_new = (row["first_seen"] or "") >= new_cutoff
    tier = row["tier"] or "road"
    badges = '<span class="badge new">NEW</span>' if is_new else ""
    badges += (
        '<span class="badge product">PRODUCT</span>'
        if tier == "product"
        else '<span class="badge road">road</span>'
    )
    days = _days_left(row["closing"], now)
    return (
        f'    <tr data-seen="{html.escape(row["first_seen"] or "")}"'
        f' data-tier="{html.escape(tier)}"'
        f' data-state="{html.escape(state)}"'
        f' data-plant="{"1" if is_plant else "0"}"'
        f' data-days="{"" if days is None else f"{days:.2f}"}">'
        f"<td>{badges}</td>"
        f'<td>{title_html}<br><span class="muted">{ref} &middot; {tender_id}</span></td>'
        f"<td>{org}</td>"
        f"<td>{state_html}</td>"
        f"<td>{html.escape(row['published'] or '')}</td>"
        f"<td>{html.escape(row['closing'] or '')}</td>"
        f"{_days_cell(days)}"
        f"</tr>"
    )


def _build_charts(tenders: list[sqlite3.Row], now: datetime, meta, counts) -> dict:
    """Compute chart SVGs and headline figures from the open matched tenders."""
    state_counter: Counter = Counter()
    plant_states = set()
    for r in tenders:
        pm = meta.get(r["portal"])
        state = pm.state if pm else r["portal"]
        state_counter[state] += 1
        if pm and pm.hincol == "plant":
            plant_states.add(state)
    state_rows = [(s, c, s in plant_states) for s, c in state_counter.most_common()]
    closing_7d = sum(
        1 for r in tenders if (d := _days_left(r["closing"], now)) is not None and 0 <= d <= 7
    )
    road = max(0, counts["open_matched"] - counts["open_product"])
    return {
        "hist": _svg_closing_histogram(tenders, now),
        "states": _svg_state_bars(state_rows),
        "donut": _svg_tier_donut(counts["open_product"], road),
        "closing_7d": closing_7d,
        "state_count": len(state_counter),
    }


def render_dashboard(settings: Settings):
    """Generate the static dashboard HTML file.

    Returns
    -------
    pathlib.Path
        The written dashboard file path.
    """
    db = Database(settings.database_path)
    now = datetime.now(IST)
    new_cutoff = (now - timedelta(hours=settings.new_badge_hours)).strftime(NOW_FORMAT)
    meta = settings.portal_meta()
    tenders = db.open_matched_tenders(limit=settings.dashboard_max_rows)
    counts = db.summary_counts()
    new_24h = len(db.new_matched_since(24))
    charts = _build_charts(tenders, now, meta, counts)
    rows_html = "\n".join(_tender_row(r, new_cutoff, now, meta) for r in tenders)
    # State dropdown options (states present among the open matched tenders).
    state_present: Counter = Counter()
    for r in tenders:
        pm = meta.get(r["portal"])
        state_present[pm.state if pm else r["portal"]] += 1
    state_options = "".join(
        f'<option value="{html.escape(s)}">{html.escape(s)} ({c})</option>'
        for s, c in sorted(state_present.items())
    )
    health = db.portal_health()
    ok_portals = sum(1 for h in health if h["status"] == "ok")
    health_html = "\n".join(
        (
            f"    <tr><td>{html.escape(h['portal'])}</td>"
            f"<td>{html.escape(meta[h['portal']].state if h['portal'] in meta else '')}</td>"
            f'<td class="{"ok" if h["status"] == "ok" else "error"}">'
            f"{html.escape(h['status'] or '')}</td>"
            f"<td>{html.escape(h['finished'] or '')}</td>"
            f"<td>{h['seen']}</td><td>{h['new']}</td>"
            f'<td class="muted">{html.escape((h["error"] or "")[:90])}</td></tr>'
        )
        for h in health
    )
    page = PAGE_TEMPLATE.format(
        brand=html.escape(settings.dashboard_brand),
        subtitle=html.escape(settings.dashboard_subtitle),
        generated=now.strftime("%d %b %Y, %H:%M"),
        portal_count=len(health),
        ok_portals=ok_portals,
        state_count=charts["state_count"],
        closing_7d=charts["closing_7d"],
        open_product=counts["open_product"],
        open_matched=counts["open_matched"],
        new_24h=new_24h,
        total=counts["total"],
        hist_svg=charts["hist"],
        states_svg=charts["states"],
        donut_svg=charts["donut"],
        state_options=state_options,
        keyword_chips=_keyword_chip_html(),
        rows=rows_html,
        health_rows=health_html,
    )
    settings.dashboard_output.parent.mkdir(parents=True, exist_ok=True)
    settings.dashboard_output.write_text(page)
    db.close()
    return settings.dashboard_output


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="900">
<title>{brand}</title>
<style>
  :root {{
    --bg:#eef2f7; --panel:#ffffff; --ink:#14233a; --muted:#64748b;
    --accent:#0b5fa5; --product:#c2410c; --new:#059669; --warn:#d97706;
    --danger:#dc2626; --border:#dce4ee;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;font:14px/1.45 -apple-system,"Segoe UI",Roboto,Helvetica,sans-serif;
    background:var(--bg);color:var(--ink)}}
  header{{background:linear-gradient(110deg,#0a2540,#0b3a66 60%,#0b5fa5);
    color:#fff;padding:18px 28px}}
  header .row{{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;
    max-width:1340px;margin:0 auto}}
  header h1{{margin:0;font-size:20px;font-weight:700;letter-spacing:.2px}}
  header .sub{{color:#aec6e2;font-size:12.5px}}
  main{{max-width:1340px;margin:0 auto;padding:20px 28px 64px}}
  .kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:16px}}
  .kpi{{background:var(--panel);border:1px solid var(--border);border-radius:12px;
    padding:14px 16px}}
  .kpi .n{{font-size:27px;font-weight:750;line-height:1}}
  .kpi .l{{color:var(--muted);font-size:11.5px;margin-top:5px;text-transform:uppercase;
    letter-spacing:.04em}}
  .kpi.hero{{background:linear-gradient(180deg,#fff,#fff6ef);border-color:#f2c9a6}}
  .kpi.hero .n{{color:var(--danger)}}
  .kpi .n.prod{{color:var(--product)}}
  .charts{{display:grid;grid-template-columns:1.35fr 1.3fr .9fr;gap:12px;margin-bottom:18px}}
  .panel{{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px 16px}}
  .panel h3{{margin:0 0 10px;font-size:12.5px;color:var(--muted);text-transform:uppercase;
    letter-spacing:.05em;font-weight:650}}
  .filterbar{{background:var(--panel);border:1px solid var(--border);border-radius:12px;
    padding:12px 14px;margin-bottom:14px}}
  .controls{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
  .controls+.controls{{margin-top:9px}}
  .controls input[type=search]{{flex:1 1 280px;padding:9px 13px;border:1px solid var(--border);
    border-radius:9px;font-size:14px;background:#fff}}
  .controls select{{padding:8px 11px;border:1px solid var(--border);border-radius:9px;
    font-size:13px;background:#fff;color:var(--ink);max-width:200px}}
  .chk{{display:inline-flex;align-items:center;gap:5px;font-size:13px;color:var(--product);
    padding:7px 10px;border:1px solid var(--border);border-radius:9px;cursor:pointer;font-weight:600}}
  .grp{{display:inline-flex;border:1px solid var(--border);border-radius:9px;overflow:hidden}}
  .grp button{{padding:7px 11px;border:0;border-right:1px solid var(--border);cursor:pointer;
    background:#fff;font-size:12.5px;color:var(--ink)}}
  .grp button:last-child{{border-right:0}}
  .grp button.active{{background:var(--accent);color:#fff}}
  .count{{font-size:12.5px;color:var(--muted);margin-left:auto;font-variant-numeric:tabular-nums}}
  .reset{{padding:7px 11px;border:1px solid var(--border);border-radius:9px;cursor:pointer;
    background:#fff;font-size:12.5px;color:var(--muted)}}
  .kwrow{{border-top:1px dashed var(--border);padding-top:9px}}
  .kwlabel{{font-size:12px;color:var(--muted);font-weight:600;align-self:center}}
  .grp-kw{{display:inline-flex;gap:6px;flex-wrap:wrap}}
  .kwchip{{padding:5px 11px;border:1px solid var(--border);border-radius:999px;cursor:pointer;
    background:#fff;font-size:12.5px;color:var(--ink)}}
  .kwchip.active{{background:var(--product);color:#fff;border-color:var(--product)}}
  .sortchip{{padding:5px 11px;border:1px solid var(--border);border-radius:999px;cursor:pointer;
    background:#fff;font-size:12.5px;color:var(--ink)}}
  .sortchip.active{{background:var(--accent);color:#fff;border-color:var(--accent)}}
  table{{width:100%;border-collapse:collapse;background:var(--panel);
    border:1px solid var(--border);border-radius:12px;overflow:hidden}}
  th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.04em;
    color:var(--muted);padding:11px 12px;border-bottom:2px solid var(--border);
    background:#f7fafd;position:sticky;top:0}}
  td{{padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:top}}
  tr:hover td{{background:#f1f6fc}}
  .badge{{display:inline-block;padding:1px 7px;border-radius:999px;font-size:10px;
    font-weight:700;margin-right:4px}}
  .badge.new{{background:#d1fae5;color:var(--new)}}
  .badge.product{{background:#fde7d3;color:var(--product)}}
  .badge.road{{background:#e8edf3;color:#52617a}}
  .state{{font-weight:600}} .plant{{color:var(--product)}}
  .days{{font-weight:750;white-space:nowrap}}
  .days.red{{color:var(--danger)}} .days.amber{{color:var(--warn)}} .days.green{{color:var(--new)}}
  .muted{{color:var(--muted);font-size:12px}}
  a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}}
  h2{{font-size:15px;margin:26px 0 10px}}
  .health td,.health th{{padding:6px 12px;font-size:12.5px}}
  .ok{{color:var(--new);font-weight:600}} .error{{color:var(--danger);font-weight:600}}
  @media(max-width:900px){{.kpis{{grid-template-columns:repeat(2,1fr)}}.charts{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<header><div class="row">
  <h1>{brand}</h1>
  <span class="sub">{subtitle}</span>
  <span class="sub">refreshed {generated} IST &middot; {ok_portals}/{portal_count} portals live &middot; {state_count} states</span>
</div></header>
<main>
  <div class="kpis">
    <div class="kpi hero"><div class="n">{closing_7d}</div><div class="l">closing &le; 7 days</div></div>
    <div class="kpi"><div class="n prod">{open_product}</div><div class="l">product tenders</div></div>
    <div class="kpi"><div class="n">{open_matched}</div><div class="l">open matching</div></div>
    <div class="kpi"><div class="n">{new_24h}</div><div class="l">new in 24h</div></div>
    <div class="kpi"><div class="n">{total}</div><div class="l">tracked</div></div>
  </div>
  <div class="charts">
    <div class="panel"><h3>Bid deadlines &mdash; tenders closing per day (next 14d)</h3>{hist_svg}</div>
    <div class="panel"><h3>Open tenders by state &nbsp;<span style="color:#c2410c">&#9733; plant</span></h3>{states_svg}</div>
    <div class="panel"><h3>Product vs road</h3>{donut_svg}</div>
  </div>
  <div class="filterbar">
    <div class="controls">
      <input id="search" type="search" placeholder="Search title, organisation, tender id...">
      <select id="fState" title="Filter by state"><option value="">All states</option>{state_options}</select>
      <label class="chk"><input type="checkbox" id="fPlant"> &#9733; Plant states</label>
    </div>
    <div class="controls">
      <span class="grp" id="gTier">
        <button class="active" data-tier="all">All tiers</button>
        <button data-tier="product">Product</button>
        <button data-tier="road">Road</button>
      </span>
      <span class="grp" id="gClose">
        <button class="active" data-close="any">Any deadline</button>
        <button data-close="3">&le;3d</button>
        <button data-close="7">&le;7d</button>
        <button data-close="14">&le;14d</button>
        <button data-close="open">Open only</button>
      </span>
      <span id="count" class="count"></span>
      <button class="reset" onclick="exportCSV()">&#8615; CSV</button>
      <button id="reset" class="reset" onclick="resetFilters()">Reset</button>
    </div>
    <div class="controls kwrow">
      <span class="kwlabel">Keywords:</span>
      <span class="grp-kw" id="gKw">{keyword_chips}</span>
    </div>
    <div class="controls kwrow">
      <span class="kwlabel">Sort by (click multiple, in order):</span>
      <span class="grp-kw" id="gSort">
        <button class="sortchip" data-sort="product">Product first</button>
        <button class="sortchip" data-sort="plant">Plant state first</button>
        <button class="sortchip" data-sort="closing">Closing soonest</button>
        <button class="sortchip" data-sort="newest">Newest</button>
        <button class="sortchip" data-sort="value">Highest days left</button>
        <button class="sortchip" data-sort="state">State A-Z</button>
      </span>
    </div>
  </div>
  <table id="tenders">
    <thead><tr><th></th><th>Title</th><th>Organisation</th><th>State</th>
      <th>Published</th><th>Closing</th><th>Left</th></tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <h2>Portal health (last run)</h2>
  <table class="health">
    <thead><tr><th>Portal</th><th>State</th><th>Status</th><th>Finished</th>
      <th>Seen</th><th>New</th><th>Error</th></tr></thead>
    <tbody>
{health_rows}
    </tbody>
  </table>
  <p class="muted">Public government e-procurement listings. Product tenders name a HINCOL
  product or bituminous binder; road tenders are general pavement work. &#9733; marks a
  HINCOL plant state. GePNIC rows open the portal home (detail pages are session bound;
  search the tender id there); CPPP rows deep-link.</p>
</main>
<script>
  const $=id=>document.getElementById(id);
  const search=$('search'),tbody=document.querySelector('#tenders tbody'),countEl=$('count');
  const total=tbody.rows.length;
  let tier='all',close='any',kwActive=[];
  function pickGroup(groupId,attr,val){{
    for(const b of $(groupId).children) b.classList.toggle('active', b.dataset[attr]===val);
  }}
  function apply(){{
    const q=search.value.toLowerCase();
    const state=$('fState').value, plant=$('fPlant').checked;
    let shown=0;
    for(const tr of tbody.rows){{
      const d=parseFloat(tr.dataset.days);
      let ok = !q || tr.textContent.toLowerCase().includes(q);
      if(ok && state) ok = tr.dataset.state===state;
      if(ok && plant) ok = tr.dataset.plant==='1';
      if(ok && tier!=='all') ok = tr.dataset.tier===tier;
      if(ok && close!=='any'){{
        if(close==='open') ok = !(d<0);
        else ok = d>=0 && d<=parseFloat(close);
      }}
      if(ok && kwActive.length){{           // keyword chips: match title against ANY active chip
        const title=tr.cells[1].textContent;
        ok = kwActive.some(rx=>rx.test(title));
      }}
      tr.style.display=ok?'':'none';
      if(ok) shown++;
    }}
    countEl.textContent=`${{shown}} of ${{total}}`;
  }}
  function setTier(t){{tier=t;pickGroup('gTier','tier',t);apply();}}
  function setClose(c){{close=c;pickGroup('gClose','close',c);apply();}}
  function rebuildKw(){{kwActive=[...$('gKw').querySelectorAll('.kwchip.active')]
    .map(b=>new RegExp(b.dataset.rx,'i'));}}
  // ---- multi-key sort: pick several keys; they apply in the order clicked ----
  let sortKeys=[];
  const num=v=>{{const x=parseFloat(v);return isNaN(x)?1e9:x;}};
  const CMP={{
    product:(a,b)=>((b.dataset.tier==='product')-(a.dataset.tier==='product')),
    plant:(a,b)=>((b.dataset.plant==='1')-(a.dataset.plant==='1')),
    closing:(a,b)=>num(a.dataset.days)-num(b.dataset.days),
    newest:(a,b)=>(b.dataset.seen||'').localeCompare(a.dataset.seen||''),
    value:(a,b)=>num(b.dataset.days)-num(a.dataset.days),
    state:(a,b)=>(a.dataset.state||'').localeCompare(b.dataset.state||''),
  }};
  function applySort(){{
    if(!sortKeys.length) return;
    const rows=Array.from(tbody.rows);
    rows.sort((a,b)=>{{for(const k of sortKeys){{const c=CMP[k](a,b);if(c)return c;}}return 0;}});
    rows.forEach(r=>tbody.appendChild(r));
  }}
  function toggleSort(k){{
    const i=sortKeys.indexOf(k);
    if(i>=0) sortKeys.splice(i,1); else sortKeys.push(k);
    for(const b of $('gSort').children){{
      const base=b.dataset.label||(b.dataset.label=b.textContent);
      const idx=sortKeys.indexOf(b.dataset.sort);
      b.classList.toggle('active', idx>=0);
      b.textContent = idx>=0 ? (idx+1)+'. '+base : base;
    }}
    applySort();
  }}
  function resetFilters(){{search.value='';$('fState').value='';$('fPlant').checked=false;
    $('gKw').querySelectorAll('.kwchip.active').forEach(b=>b.classList.remove('active'));
    kwActive=[];sortKeys=[];
    for(const b of $('gSort').children){{b.classList.remove('active');
      if(b.dataset.label)b.textContent=b.dataset.label;}}
    setTier('all');setClose('any');}}
  $('gTier').onclick=e=>{{if(e.target.dataset.tier)setTier(e.target.dataset.tier);}};
  $('gClose').onclick=e=>{{if(e.target.dataset.close)setClose(e.target.dataset.close);}};
  $('gSort').onclick=e=>{{if(e.target.dataset.sort)toggleSort(e.target.dataset.sort);}};
  $('gKw').onclick=e=>{{if(e.target.classList.contains('kwchip')){{
    e.target.classList.toggle('active');rebuildKw();apply();}}}};
  // ---- export the currently-filtered rows to CSV (for the bid team) ----
  function exportCSV(){{
    const q=v=>'"'+String(v).replace(/"/g,'""').replace(/\\s+/g,' ').trim()+'"';
    const out=[['Title','Organisation','State','Tier','Published','Closing','Days left','Tender ID','Link'].join(',')];
    for(const tr of tbody.rows){{
      if(tr.style.display==='none') continue;
      const a=tr.cells[1].querySelector('a');
      const idspan=tr.cells[1].querySelector('.muted');
      const title=(a?a.textContent:tr.cells[1].firstChild.textContent)||'';
      out.push([q(title),q(tr.cells[2].textContent),q(tr.dataset.state),q(tr.dataset.tier),
        q(tr.cells[4].textContent),q(tr.cells[5].textContent),q(tr.cells[6].textContent),
        q(idspan?idspan.textContent:''),q(a?a.href:'')].join(','));
    }}
    const blob=new Blob([out.join('\\n')],{{type:'text/csv;charset=utf-8'}});
    const u=URL.createObjectURL(blob),el=document.createElement('a');
    el.href=u; el.download='hincol-tenders.csv'; el.click(); URL.revokeObjectURL(u);
  }}
  $('fState').onchange=apply; $('fPlant').onchange=apply; search.addEventListener('input',apply);
  toggleSort('product');toggleSort('closing');  // sensible default: product first, then soonest
  apply();
</script>
</body>
</html>
"""
