"""Notification path-selection tests (CLI vs direct ntfy vs none)."""

from __future__ import annotations

import sqlite3

import tenderwatch.notify as notify


def test_no_push_when_disabled(settings) -> None:
    settings.notify_enabled = False
    assert notify.send_new_tender_push(settings, ["Road work"], 1) is False


def test_no_push_when_zero(settings) -> None:
    assert notify.send_new_tender_push(settings, [], 0) is False


def test_falls_back_to_ntfy(settings, monkeypatch) -> None:
    monkeypatch.setattr(notify.shutil, "which", lambda _: None)
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

    def fake_post(url, content, headers, timeout):
        captured.update(url=url, content=content, headers=headers)
        return FakeResponse()

    monkeypatch.setattr(notify.httpx, "post", fake_post)
    ok = notify.send_new_tender_push(settings, ["Construction of road"], 5)
    assert ok is True
    assert captured["url"].endswith("/test-topic")
    assert b"Construction of road" in captured["content"]
    assert "5 new" in captured["headers"]["Title"]
    assert "HINCOL" in captured["headers"]["Title"]


def test_deadline_push(settings, monkeypatch) -> None:
    monkeypatch.setattr(notify.shutil, "which", lambda _: None)
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

    monkeypatch.setattr(
        notify.httpx,
        "post",
        lambda url, content, headers, timeout: (
            captured.update(content=content, headers=headers) or FakeResponse()
        ),
    )
    # Build sqlite3.Row objects to mirror the DB query result shape.
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    rows = list(
        conn.execute(
            "SELECT 'Supply of CRMB' AS title, '2026-06-15 15:00' AS closing, 'product' AS tier"
        )
    )
    assert notify.send_deadline_push(settings, rows) is True
    assert b"PRODUCT" in captured["content"]
    assert b"CRMB" in captured["content"]
    assert "closing soon" in captured["headers"]["Title"]
    conn.close()


def test_skips_when_no_channel(settings, monkeypatch) -> None:
    monkeypatch.setattr(notify.shutil, "which", lambda _: None)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert notify.send_new_tender_push(settings, ["Road"], 1) is False
