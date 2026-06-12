"""Notification path-selection tests (CLI vs direct ntfy vs none)."""

from __future__ import annotations

import tenderwatch.notify as notify
from tenderwatch.config import Settings


def make_settings(tmp_path) -> Settings:
    return Settings(
        database_path=tmp_path / "t.db",
        request_delay_seconds=0.0,
        timeout_seconds=5,
        retries=0,
        max_workers=1,
        cppp_max_pages=1,
        cppp_min_pages=1,
        max_org_pages=1,
        include_keywords=["road"],
        exclude_keywords=[],
        match_organisation=False,
        dashboard_output=tmp_path / "index.html",
        dashboard_max_rows=10,
        new_badge_hours=48,
        notify_enabled=True,
        notify_command="push-to-phone",
        notify_max_titles=3,
        portals=[],
    )


def test_no_push_when_disabled(tmp_path) -> None:
    settings = make_settings(tmp_path)
    settings.notify_enabled = False
    assert notify.send_new_tender_push(settings, ["Road work"], 1) is False


def test_no_push_when_zero(tmp_path) -> None:
    settings = make_settings(tmp_path)
    assert notify.send_new_tender_push(settings, [], 0) is False


def test_falls_back_to_ntfy(tmp_path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    monkeypatch.setattr(notify.shutil, "which", lambda _: None)
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

    def fake_post(url, content, headers, timeout):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(notify.httpx, "post", fake_post)
    ok = notify.send_new_tender_push(settings, ["Construction of road"], 5)
    assert ok is True
    assert captured["url"].endswith("/test-topic")
    assert b"Construction of road" in captured["content"]
    assert "5 new matching" in captured["headers"]["Title"]


def test_skips_when_no_channel(tmp_path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    monkeypatch.setattr(notify.shutil, "which", lambda _: None)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert notify.send_new_tender_push(settings, ["Road"], 1) is False
