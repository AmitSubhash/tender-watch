"""Static HTML dashboard generation from the tender database."""

from __future__ import annotations

import html
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .config import Settings
from .db import NOW_FORMAT, Database

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="900">
<title>TenderWatch</title>
<style>
  :root {{
    --bg: #f6f7f9; --card: #ffffff; --ink: #1a202c; --muted: #64748b;
    --accent: #1d4ed8; --new: #047857; --warn: #b45309; --danger: #b91c1c;
    --border: #e2e8f0;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font: 14px/1.45 -apple-system, "Segoe UI", Roboto, sans-serif;
         background: var(--bg); color: var(--ink); }}
  header {{ background: #0f172a; color: #f8fafc; padding: 14px 24px;
            display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }}
  header h1 {{ margin: 0; font-size: 18px; }}
  header .sub {{ color: #94a3b8; font-size: 12.5px; }}
  main {{ max-width: 1280px; margin: 0 auto; padding: 18px 24px 60px; }}
  .cards {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }}
  .card {{ background: var(--card); border: 1px solid var(--border);
           border-radius: 10px; padding: 12px 18px; min-width: 150px; }}
  .card .num {{ font-size: 26px; font-weight: 700; }}
  .card .label {{ color: var(--muted); font-size: 12px; }}
  .controls {{ display: flex; gap: 10px; margin: 10px 0 14px; flex-wrap: wrap; }}
  .controls input {{ flex: 1 1 320px; padding: 8px 12px; border: 1px solid var(--border);
                     border-radius: 8px; font-size: 14px; }}
  .controls button {{ padding: 8px 14px; border: 1px solid var(--border); cursor: pointer;
                      border-radius: 8px; background: var(--card); font-size: 13px; }}
  .controls button.active {{ background: var(--accent); color: #fff;
                             border-color: var(--accent); }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card);
           border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }}
  th {{ text-align: left; font-size: 11.5px; text-transform: uppercase;
        letter-spacing: 0.04em; color: var(--muted); padding: 10px 12px;
        border-bottom: 2px solid var(--border); background: #fbfcfe;
        position: sticky; top: 0; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid var(--border);
        vertical-align: top; }}
  tr:hover td {{ background: #f1f5fb; }}
  .badge {{ display: inline-block; padding: 1px 8px; border-radius: 999px;
            font-size: 11px; font-weight: 600; }}
  .badge.new {{ background: #d1fae5; color: var(--new); }}
  .portal {{ display: inline-block; background: #eef2ff; color: #3730a3;
             padding: 1px 8px; border-radius: 999px; font-size: 11px; }}
  .days {{ font-weight: 600; white-space: nowrap; }}
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
  <h1>TenderWatch</h1>
  <span class="sub">road and infrastructure tenders, refreshed {generated}</span>
  <span class="sub">{portal_count} portals tracked</span>
</header>
<main>
  <div class="cards">
    <div class="card"><div class="num">{open_matched}</div>
      <div class="label">open matching tenders</div></div>
    <div class="card"><div class="num">{new_24h}</div>
      <div class="label">new matches in 24h</div></div>
    <div class="card"><div class="num">{new_badge}</div>
      <div class="label">new matches in {badge_hours}h</div></div>
    <div class="card"><div class="num">{total}</div>
      <div class="label">tenders tracked total</div></div>
  </div>
  <div class="controls">
    <input id="search" type="search"
      placeholder="Filter by title, organisation, portal, tender id...">
    <button id="sortNew" class="active" onclick="sortRows('new')">Newest first</button>
    <button id="sortClose" onclick="sortRows('close')">Closing soon</button>
  </div>
  <table id="tenders">
    <thead><tr>
      <th></th><th>Title</th><th>Organisation</th><th>Portal</th>
      <th>Published</th><th>Closing</th><th>Left</th>
    </tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <h2>Portal health (last run)</h2>
  <table class="health">
    <thead><tr><th>Portal</th><th>Status</th><th>Finished</th>
      <th>Rows seen</th><th>New</th><th>Error</th></tr></thead>
    <tbody>
{health_rows}
    </tbody>
  </table>
  <p class="muted">Data from public government e-procurement listings.
  GePNIC portal rows link to the portal home (detail pages are session
  bound); search the tender id there. CPPP rows deep-link directly.</p>
</main>
<script>
  const search = document.getElementById('search');
  const tbody = document.querySelector('#tenders tbody');
  search.addEventListener('input', () => {{
    const q = search.value.toLowerCase();
    for (const tr of tbody.rows) {{
      tr.style.display = tr.textContent.toLowerCase().includes(q) ? '' : 'none';
    }}
  }});
  function sortRows(mode) {{
    const rows = Array.from(tbody.rows);
    rows.sort((a, b) => {{
      const ka = a.dataset[mode === 'new' ? 'seen' : 'closing'] || '';
      const kb = b.dataset[mode === 'new' ? 'seen' : 'closing'] || '';
      return mode === 'new' ? kb.localeCompare(ka) : ka.localeCompare(kb);
    }});
    rows.forEach(r => tbody.appendChild(r));
    document.getElementById('sortNew').classList.toggle('active', mode === 'new');
    document.getElementById('sortClose').classList.toggle('active', mode === 'close');
  }}
</script>
</body>
</html>
"""


def _days_left_cell(closing: str | None, now: datetime) -> str:
    if not closing:
        return '<td class="days muted">?</td>'
    try:
        closing_dt = datetime.strptime(closing, "%Y-%m-%d %H:%M")
    except ValueError:
        return '<td class="days muted">?</td>'
    days = (closing_dt - now).total_seconds() / 86400
    if days < 0:
        return '<td class="days muted">closed</td>'
    css = "red" if days < 3 else ("amber" if days < 7 else "green")
    return f'<td class="days {css}">{days:.0f}d</td>'


def _tender_row(row: sqlite3.Row, new_cutoff: str, now: datetime) -> str:
    title = html.escape(row["title"] or "(untitled)")
    if row["url"]:
        title_html = f'<a href="{html.escape(row["url"])}" target="_blank">{title}</a>'
    else:
        title_html = title
    ref = html.escape(row["ref_no"] or "")
    tender_id = html.escape(row["tender_id"])
    org = html.escape(row["organisation"] or "")
    is_new = (row["first_seen"] or "") >= new_cutoff
    badge = '<span class="badge new">NEW</span>' if is_new else ""
    return (
        f'    <tr data-seen="{html.escape(row["first_seen"] or "")}"'
        f' data-closing="{html.escape(row["closing"] or "9999")}">'
        f"<td>{badge}</td>"
        f'<td>{title_html}<br><span class="muted">{ref} &middot; {tender_id}</span></td>'
        f"<td>{org}</td>"
        f'<td><span class="portal">{html.escape(row["portal"])}</span></td>'
        f"<td>{html.escape(row['published'] or '')}</td>"
        f"<td>{html.escape(row['closing'] or '')}</td>"
        f"{_days_left_cell(row['closing'], now)}"
        f"</tr>"
    )


def render_dashboard(settings: Settings) -> Path:
    """Generate the static dashboard HTML file.

    Parameters
    ----------
    settings : Settings
        Provides database path, output path, and display options.

    Returns
    -------
    Path
        The written dashboard file path.
    """
    db = Database(settings.database_path)
    now = datetime.now()
    new_cutoff = (now - timedelta(hours=settings.new_badge_hours)).strftime(NOW_FORMAT)
    tenders = db.open_matched_tenders(limit=settings.dashboard_max_rows)
    rows_html = "\n".join(_tender_row(r, new_cutoff, now) for r in tenders)
    counts = db.summary_counts()
    new_24h = len(db.new_matched_since(24))
    new_badge = len(db.new_matched_since(settings.new_badge_hours))
    health = db.portal_health()
    health_html = "\n".join(
        (
            f"    <tr><td>{html.escape(h['portal'])}</td>"
            f'<td class="{"ok" if h["status"] == "ok" else "error"}">'
            f"{html.escape(h['status'] or '')}</td>"
            f"<td>{html.escape(h['finished'] or '')}</td>"
            f"<td>{h['seen']}</td><td>{h['new']}</td>"
            f'<td class="muted">{html.escape((h["error"] or "")[:120])}</td></tr>'
        )
        for h in health
    )
    page = PAGE_TEMPLATE.format(
        generated=now.strftime("%d %b %Y, %H:%M"),
        portal_count=len(health),
        open_matched=counts["open_matched"],
        new_24h=new_24h,
        new_badge=new_badge,
        badge_hours=settings.new_badge_hours,
        total=counts["total"],
        rows=rows_html,
        health_rows=health_html,
    )
    settings.dashboard_output.parent.mkdir(parents=True, exist_ok=True)
    settings.dashboard_output.write_text(page)
    db.close()
    return settings.dashboard_output
