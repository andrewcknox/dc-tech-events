from datetime import datetime

from dte.dedupe import dedupe_batch, find_duplicate
from dte.models import TZ, fingerprint, is_past, normalize_title, parse_datetime


def test_normalize_title_strips_punct_case_stopwords():
    assert normalize_title("The Future of AI: A Conversation!") == "future ai conversation"
    assert normalize_title("  Semiconductors & the CHIPS Act ") == "semiconductors chips act"


def test_parse_datetime_shapes():
    assert parse_datetime("2026-09-18T14:00:00-04:00").isoformat() == "2026-09-18T14:00:00-04:00"
    naive = parse_datetime("2026-09-18 14:00")
    assert naive.tzinfo is not None and naive.utcoffset().total_seconds() == -4 * 3600
    assert parse_datetime("September 18, 2026 2pm").hour == 14
    utc = parse_datetime("2026-12-01T19:00:00Z")
    assert utc.hour == 14 and utc.tzname() == "EST"  # converted to New York, winter
    assert parse_datetime("") is None and parse_datetime("no date here at all") is None


def test_fingerprint_same_for_cross_listed_titles():
    d = datetime(2026, 9, 18, 14, tzinfo=TZ)
    assert fingerprint("The Future of AI: A Conversation", d) == fingerprint("future of ai — a conversation", d)
    assert fingerprint("The Future of AI", d) != fingerprint("The Future of AI", datetime(2026, 9, 19, tzinfo=TZ))


def test_is_past():
    now = datetime(2026, 9, 13, 12, tzinfo=TZ)
    assert is_past(datetime(2026, 9, 12, 12, tzinfo=TZ), now)
    assert not is_past(datetime(2026, 9, 13, 13, tzinfo=TZ), now)
    assert not is_past(datetime(2026, 9, 13, 9, tzinfo=TZ), now, grace_hours=6)


def test_fuzzy_duplicate_within_window():
    existing = [{"id": 1, "title": "US-China Tech Competition: The Semiconductor Front", "start_dt": "2026-10-01T10:00:00-04:00", "url": "a"}]
    cand = {"title": "The Semiconductor Front in US–China Tech Competition (webcast)", "start_dt": "2026-10-02T09:00:00-04:00", "url": "b"}
    assert find_duplicate(cand, existing, threshold=85, window_days=1)["id"] == 1
    far = dict(cand, start_dt="2026-10-05T09:00:00-04:00")
    assert find_duplicate(far, existing) is None
    other = {"title": "Quantum Computing and Export Controls", "start_dt": "2026-10-01T10:00:00-04:00"}
    assert find_duplicate(other, existing) is None


def test_dedupe_batch_keeps_first_and_appends_alt_urls():
    batch = [
        {"title": "AI and National Security", "start_dt": "2026-10-01T10:00:00-04:00", "url": "https://a/1", "location": None},
        {"title": "AI & National Security", "start_dt": "2026-10-01T10:00:00-04:00", "url": "https://b/2", "location": "CSIS"},
        {"title": "Space Policy Forum", "start_dt": "2026-10-01T10:00:00-04:00", "url": "https://c/3"},
    ]
    out = dedupe_batch(batch)
    assert len(out) == 2
    assert out[0]["url"] == "https://a/1" and out[0]["alt_urls"] == ["https://b/2"]
    assert out[0]["location"] == "CSIS"  # blank filled from the duplicate
