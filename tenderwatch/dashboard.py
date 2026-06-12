"""Static HTML dashboard generation from the tender database."""

from __future__ import annotations

import html
import sqlite3
from datetime import datetime, timedelta

from .config import PortalConfig, Settings
from .db import IST, NOW_FORMAT, Database

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="900">
<title>{brand}</title>
<style>
  :root {{
    --bg: #f4f6f8; --card: #ffffff; --ink: #14233a; --muted: #5f7088;
    --accent: #0b5fa5; --new: #047857; --warn: #b45309; --danger: #b91c1c;
    --product: #7c2d12; --product-bg: #fde68a; --border: #dde5ee; --ink-inv: #f8fafc;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font: 14px/1.45 -apple-system, "Segoe UI", Roboto, sans-serif;
         background: var(--bg); color: var(--ink); }}
  header {{ background: #0b2440; color: var(--ink-inv); padding: 14px 24px;
            display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }}
  header h1 {{ margin: 0; font-size: 19px; letter-spacing: 0.01em; }}
  header .sub {{ color: #9fb3cc; font-size: 12.5px; }}
  main {{ max-width: 1320px; margin: 0 auto; padding: 18px 24px 60px; }}
  .cards {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }}
  .card {{ background: var(--card); border: 1px solid var(--border);
           border-radius: 10px; padding: 12px 18px; min-width: 140px; }}
  .card.hero {{ border-color: var(--accent); box-shadow: 0 1px 0 var(--accent) inset; }}
  .card .num {{ font-size: 26px; font-weight: 700; }}
  .card .num.product {{ color: var(--product); }}
  .card .num.urgent {{ color: var(--danger); }}
  .card .label {{ color: var(--muted); font-size: 12px; }}
  .controls {{ display: flex; gap: 8px; margin: 10px 0 14px; flex-wrap: wrap; align-items: center; }}
  .controls input {{ flex: 1 1 300px; padding: 8px 12px; border: 1px solid var(--border);
                     border-radius: 8px; font-size: 14px; }}
  .controls button {{ padding: 8px 13px; border: 1px solid var(--border); cursor: pointer;
                      border-radius: 8px; background: var(--card); font-size: 13px; }}
  .controls button.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card);
           border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }}
  th {{ text-align: left; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.04em;
        color: var(--muted); padding: 10px 12px; border-bottom: 2px solid var(--border);
        background: #fbfcfe; position: sticky; top: 0; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  tr:hover td {{ background: #eef4fb; }}
  .badge {{ display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 10.5px;
            font-weight: 700; margin-right: 4px; }}
  .badge.new {{ background: #d1fae5; color: var(--new); }}
  .badge.product {{ background: var(--product-bg); color: var(--product); }}
  .badge.road {{ background: #e2e8f0; color: #475569; }}
  .state {{ font-weight: 600; }}
  .plant {{ color: var(--product); }}
  .days {{ font-weight: 700; white-space: nowrap; }}
  .days.red {{ color: var(--danger); }}
  .days.amber {{ color: var(--warn); }}
  .days.green {{ color: var(--new); }}
  .muted {{ color: var(--muted); font-size: 12px; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  h2 {{ font-size: 15px; margin: 26px 0 10px; }}
  .health td, .health th {{ padding: 6px 12px; font-size: 12.5px; }}
  .ok {{ color: var(--new); font-weight: 600; }}
  .error {{ color: var(--danger); font-weight: 600; }}
</style>
</head>
<body>
<header>
  <h1>{brand}</h1>
  <span class="sub">{subtitle}</span>
  <span class="sub">refreshed {generated} IST &middot; {portal_count} portals</span>
</header>
<main>
  <div class="cards">
    <div class="card hero"><div class="num urgent">{closing_7d}</div>
      <div class="label">closing within 7 days</div></div>
    <div class="card"><div class="num product">{open_product}</div>
      <div class="label">open product tenders</div></div>
    <div class="card"><div class="num">{open_matched}</div>
      <div class="label">open matching tenders</div></div>
    <div class="card"><div class="num">{new_24h}</div>
      <div class="label">new in 24h</div></div>
    <div class="card"><div class="num">{total}</div>
      <div class="label">tenders tracked</div></div>
  </div>
  <div class="controls">
    <input id="search" type="search" placeholder="Filter by title, organisation, state, tender id...">
    <button id="fAll" class="active" onclick="setFilter('all')">All</button>
    <button id="fProduct" onclick="setFilter('product')">Product only</button>
    <button id="fClosing" onclick="setFilter('closing')">Closing &le;7d</button>
    <span style="width:8px"></span>
    <button id="sNew" class="active" onclick="sortRows('new')">Newest</button>
    <button id="sClose" onclick="sortRows('close')">Closing soon</button>
  </div>
  <table id="tenders">
    <thead><tr>
      <th></th><th>Title</th><th>Organisation</th><th>State</th>
      <th>Published</th><th>Closing</th><th>Left</th>
    </tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <h2>Portal health (last run)</h2>
  <table class="health">
    <thead><tr><th>Portal</th><th>State</th><th>Status</th><th>Finished</th>
      <th>Rows seen</th><th>New</th><th>Error</th></tr></thead>
    <tbody>
{health_rows}
    </tbody>
  </table>
  <p class="muted">Public government e-procurement listings. Product tenders name a
  HINCOL product or bituminous binder; road tenders are general pavement work.
  ★ marks a HINCOL plant state. GePNIC rows open the portal home (detail pages
  are session bound; search the tender id there); CPPP rows deep-link.</p>
</main>
<script>
  const search = document.getElementById('search');
  const tbody = document.querySelector('#tenders tbody');
  let filter = 'all';
  function apply() {{
    const q = search.value.toLowerCase();
    for (const tr of tbody.rows) {{
      const textOk = tr.textContent.toLowerCase().includes(q);
      let fOk = true;
      if (filter === 'product') fOk = tr.dataset.tier === 'product';
      else if (filter === 'closing') fOk = parseFloat(tr.dataset.days) <= 7 && parseFloat(tr.dataset.days) >= 0;
      tr.style.display = (textOk && fOk) ? '' : 'none';
    }}
  }}
  function setFilter(f) {{
    filter = f;
    for (const id of ['fAll','fProduct','fClosing'])
      document.getElementById(id).classList.remove('active');
    document.getElementById({{all:'fAll',product:'fProduct',closing:'fClosing'}}[f]).classList.add('active');
    apply();
  }}
  function sortRows(mode) {{
    const rows = Array.from(tbody.rows);
    rows.sort((a, b) => {{
      if (mode === 'new') return (b.dataset.seen||'').localeCompare(a.dataset.seen||'');
      return (parseFloat(a.dataset.days) || 1e9) - (parseFloat(b.dataset.days) || 1e9);
    }});
    rows.forEach(r => tbody.appendChild(r));
    document.getElementById('sNew').classList.toggle('active', mode === 'new');
    document.getElementById('sClose').classList.toggle('active', mode === 'close');
  }}
  search.addEventListener('input', apply);
</script>
</body>
</html>
"""


def _days_left(closing: str | None, now: datetime) -> float | None:
    """Return days until closing (may be negative), or None if unparseable."""
    if not closing:
        return None
    try:
        closing_dt = datetime.strptime(closing, "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    except ValueError:
        return None
    return (closing_dt - now).total_seconds() / 86400


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
    url = (
        row["url"]
        if row["url"] and str(row["url"]).startswith(("http://", "https://"))
        else None
    )
    title_html = (
        f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{title}</a>'
        if url
        else title
    )
    ref = html.escape(row["ref_no"] or "")
    tender_id = html.escape(row["tender_id"])
    org = html.escape(row["organisation"] or "")
    portal_meta = meta.get(row["portal"])
    state = portal_meta.state if portal_meta else ""
    is_plant = bool(portal_meta and portal_meta.hincol == "plant")
    state_html = f'<span class="state">{html.escape(state)}</span>'
    if is_plant:
        state_html += ' <span class="plant" title="HINCOL plant state">&#9733;</span>'
    is_new = (row["first_seen"] or "") >= new_cutoff
    tier = row["tier"] or "road"
    badges = ""
    if is_new:
        badges += '<span class="badge new">NEW</span>'
    badges += (
        '<span class="badge product">PRODUCT</span>'
        if tier == "product"
        else '<span class="badge road">road</span>'
    )
    days = _days_left(row["closing"], now)
    return (
        f'    <tr data-seen="{html.escape(row["first_seen"] or "")}"'
        f' data-tier="{html.escape(tier)}"'
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


def render_dashboard(settings: Settings):
    """Generate the static dashboard HTML file.

    Parameters
    ----------
    settings : Settings
        Provides database path, output path, branding, and display options.

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
    rows_html = "\n".join(_tender_row(r, new_cutoff, now, meta) for r in tenders)
    closing_7d = sum(
        1 for r in tenders if (d := _days_left(r["closing"], now)) is not None and 0 <= d <= 7
    )
    counts = db.summary_counts()
    new_24h = len(db.new_matched_since(24))
    health = db.portal_health()
    health_html = "\n".join(
        (
            f"    <tr><td>{html.escape(h['portal'])}</td>"
            f"<td>{html.escape(meta[h['portal']].state if h['portal'] in meta else '')}</td>"
            f'<td class="{"ok" if h["status"] == "ok" else "error"}">'
            f"{html.escape(h['status'] or '')}</td>"
            f"<td>{html.escape(h['finished'] or '')}</td>"
            f"<td>{h['seen']}</td><td>{h['new']}</td>"
            f'<td class="muted">{html.escape((h["error"] or "")[:120])}</td></tr>'
        )
        for h in health
    )
    page = PAGE_TEMPLATE.format(
        brand=html.escape(settings.dashboard_brand),
        subtitle=html.escape(settings.dashboard_subtitle),
        generated=now.strftime("%d %b %Y, %H:%M"),
        portal_count=len(health),
        closing_7d=closing_7d,
        open_product=counts["open_product"],
        open_matched=counts["open_matched"],
        new_24h=new_24h,
        total=counts["total"],
        rows=rows_html,
        health_rows=health_html,
    )
    settings.dashboard_output.parent.mkdir(parents=True, exist_ok=True)
    settings.dashboard_output.write_text(page)
    db.close()
    return settings.dashboard_output
