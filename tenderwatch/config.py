"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class PortalConfig:
    """One portal entry from config.yaml."""

    id: str
    name: str
    type: str
    enabled: bool = False
    app_url: str = ""
    list_url: str = ""


@dataclass
class Settings:
    """Validated runtime settings."""

    database_path: Path
    request_delay_seconds: float
    timeout_seconds: float
    retries: int
    max_workers: int
    cppp_max_pages: int
    cppp_min_pages: int
    max_org_pages: int
    include_keywords: list[str]
    exclude_keywords: list[str]
    match_organisation: bool
    dashboard_output: Path
    dashboard_max_rows: int
    new_badge_hours: int
    notify_enabled: bool
    notify_command: str
    notify_max_titles: int
    portals: list[PortalConfig] = field(default_factory=list)


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load and validate config.yaml.

    Parameters
    ----------
    config_path : str or Path, optional
        Override path; defaults to config.yaml in the project root.

    Returns
    -------
    Settings
        Parsed configuration with paths resolved against the project root.
    """
    path = Path(config_path) if config_path else PROJECT_ROOT / "config.yaml"
    raw = yaml.safe_load(path.read_text())
    scrape = raw.get("scrape", {})
    filters = raw.get("filters", {})
    dashboard = raw.get("dashboard", {})
    notify = raw.get("notify", {})
    portals = [
        PortalConfig(
            id=p["id"],
            name=p.get("name", p["id"]),
            type=p.get("type", "gepnic"),
            enabled=bool(p.get("enabled", False)),
            app_url=p.get("app_url", ""),
            list_url=p.get("list_url", ""),
        )
        for p in raw.get("portals", [])
    ]
    return Settings(
        database_path=PROJECT_ROOT / raw.get("database", "data/tenders.db"),
        request_delay_seconds=float(scrape.get("request_delay_seconds", 0.4)),
        timeout_seconds=float(scrape.get("timeout_seconds", 45)),
        retries=int(scrape.get("retries", 2)),
        max_workers=int(scrape.get("max_workers", 6)),
        cppp_max_pages=int(scrape.get("cppp_max_pages", 40)),
        cppp_min_pages=int(scrape.get("cppp_min_pages", 3)),
        max_org_pages=int(scrape.get("max_org_pages", 30)),
        include_keywords=list(filters.get("include_keywords", [])),
        exclude_keywords=list(filters.get("exclude_keywords", [])),
        match_organisation=bool(filters.get("match_organisation", False)),
        dashboard_output=PROJECT_ROOT / dashboard.get("output", "dashboard/index.html"),
        dashboard_max_rows=int(dashboard.get("max_rows", 1500)),
        new_badge_hours=int(dashboard.get("new_badge_hours", 48)),
        notify_enabled=bool(notify.get("enabled", True)),
        notify_command=str(notify.get("command", "push-to-phone")),
        notify_max_titles=int(notify.get("max_titles", 3)),
        portals=portals,
    )
