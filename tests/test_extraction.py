"""Fixture-based tests. No network: pages are saved in tests/fixtures and Claude is replaced by a fake."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from dte import db, fetch, llm
from dte.config import Source
from dte.models import TZ, ExtractedEvent, ExtractionResult

FIX = Path(__file__).parent / "fixtures"
TODAY = datetime(2026, 9, 13, 9, tzinfo=TZ)


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_html_to_text_strips_boilerplate_and_keeps_links():
    html = (FIX / "hudson_events.html").read_text(encoding="utf-8")
    text = fetch.html_to_text(html, "https://www.hudson.org/events")
    assert "Somaliland" in text and "September 2026" in text
    assert "<script" not in text and "cookie" not in text.lower()[:500]
    assert "<https://www.hudson.org/events/" in text  # link targets inlined for Claude


def test_chunking_respects_limit():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(500))
    chunks = fetch.chunk_text(text, 4000)
    assert len(chunks) > 1 and all(len(c) <= 4100 for c in chunks)
    assert "\n".join(chunks) == text


def test_ics_parsing_and_upsert_is_idempotent(con):
    src = Source(name="GW Elliott School", url="https://calendar.gwu.edu/x.ics", type="ics")
    events = fetch.parse_ics((FIX / "gw_elliott.ics").read_text(encoding="utf-8"), src)
    assert len(events) > 10 and all(e["start_dt"] and e["title"] for e in events)
    cfg = {"dedupe_window_days": 1, "dedupe_threshold": 85}
    new1, _ = fetch.upsert_events(con, events, src, cfg, TODAY)
    new2, seen2 = fetch.upsert_events(con, events, src, cfg, TODAY)
    assert new1 > 0 and new2 == 0 and seen2 == new1
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == new1


def test_rss_to_text_includes_when_where():
    text = fetch.rss_to_text((FIX / "hub_555penn.rss").read_text(encoding="utf-8"))
    assert "Kevin Roose" in text and "When: October 6th" in text and "Link: https://hub.jhu.edu" in text


def test_html_extraction_with_fake_claude_and_cache(con, monkeypatch):
    calls = {"n": 0}

    def fake_extract(page_text, page_url, source_name, today, model=None):
        calls["n"] += 1
        assert "Somaliland" in page_text
        ev = ExtractedEvent(
            title="Somaliland as a Strategic Partner in the Horn of Africa",
            start_datetime="2026-09-14T15:30:00-04:00", end_datetime="2026-09-14T17:00:00-04:00",
            location="Hudson Institute, 1201 Pennsylvania Ave NW", virtual=False,
            url="/events/somaliland", host_org="Hudson Institute",
            description_short="Keynote by the Somaliland president.", speakers=["Joshua Meservey"],
        )
        past = ev.model_copy(update={"title": "Old thing", "start_datetime": "2026-01-01T10:00:00-05:00"})
        return ExtractionResult(events=[ev, past]), type("U", (), {"input_tokens": 1000, "output_tokens": 100})()

    monkeypatch.setattr(llm, "extract_events", fake_extract)
    src = Source(name="Hudson Institute", url="https://www.hudson.org/events", type="html")
    cfg = {"max_chunk_chars": 100000, "model": "fake", "dedupe_window_days": 1, "dedupe_threshold": 85}
    text = fetch.html_to_text((FIX / "hudson_events.html").read_text(encoding="utf-8"), src.url)

    events = fetch.extract_with_cache(con, text, src, cfg, TODAY)
    assert calls["n"] == 1 and len(events) == 2
    assert events[0]["url"] == "https://www.hudson.org/events/somaliland"  # relative URL resolved

    # second run: identical content -> served from cache, no model call
    events2 = fetch.extract_with_cache(con, text, src, cfg, TODAY)
    assert calls["n"] == 1 and events2 == events

    new, _ = fetch.upsert_events(con, events, src, cfg, TODAY)
    assert new == 1  # the past event was skipped
    row = con.execute("SELECT title, speakers FROM events").fetchone()
    assert "Somaliland" in row[0] and json.loads(row[1]) == ["Joshua Meservey"]


def test_sources_status_and_consecutive_failures(con):
    for s in ("ok", "failed", "failed", "failed"):
        db.log_source_status(con, "X", s, 0, "boom")
    assert db.consecutive_failures(con, "X") == 3
    db.log_source_status(con, "X", "ok", 3, "")
    assert db.consecutive_failures(con, "X") == 0
