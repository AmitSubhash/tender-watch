"""Shared test fixtures."""

from __future__ import annotations

import pytest

from tenderwatch.config import PortalConfig, Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    """A minimal Settings instance pointed at a temp database."""
    return Settings(
        database_path=tmp_path / "t.db",
        request_delay_seconds=0.0,
        timeout_seconds=5,
        retries=0,
        max_workers=1,
        cppp_max_pages=1,
        cppp_min_pages=1,
        max_org_pages=1,
        force_redrill_hours=24,
        product_keywords=["bitumen", "emulsion", "crmb", "pmb", "asphalt", "pothole"],
        road_keywords=["road", "highway", "bridge", "cc road", "rob", "सड़क"],
        exclude_keywords=[],
        match_organisation=False,
        deadline_road_within_days=5,
        deadline_product_within_days=10,
        dashboard_brand="HINCOL TenderWatch",
        dashboard_subtitle="test",
        dashboard_output=tmp_path / "index.html",
        dashboard_max_rows=100,
        new_badge_hours=48,
        notify_enabled=True,
        notify_command="push-to-phone",
        notify_max_titles=3,
        portals=[
            PortalConfig(
                id="westbengal",
                name="West Bengal",
                type="gepnic",
                app_url="https://wbtenders.gov.in/nicgep/app",
                state="West Bengal",
                hincol="plant",
                enabled=True,
            )
        ],
    )
