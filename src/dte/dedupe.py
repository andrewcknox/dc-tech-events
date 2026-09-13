"""Deduplication: exact fingerprint first, then fuzzy title match within ±N days."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from rapidfuzz import fuzz

from .models import fingerprint, normalize_title, parse_datetime


def find_duplicate(
    candidate: dict[str, Any],
    existing: list[dict[str, Any]],
    threshold: int = 85,
    window_days: int = 1,
) -> dict[str, Any] | None:
    """Return the existing record that `candidate` duplicates, or None.

    candidate/existing dicts need `title` and `start_dt` (ISO string or datetime).
    Exact match = same fingerprint (normalized title + date).
    Fuzzy match = token_set_ratio >= threshold and start dates within ±window_days.
    """
    c_start = parse_datetime(candidate["start_dt"])
    if c_start is None:
        return None
    c_fp = candidate.get("fingerprint") or fingerprint(candidate["title"], c_start)
    c_norm = normalize_title(candidate["title"])

    best, best_score = None, 0
    for ex in existing:
        if ex.get("fingerprint") == c_fp:
            return ex
        e_start = parse_datetime(ex["start_dt"])
        if e_start is None:
            continue
        if abs((e_start.date() - c_start.date()).days) > window_days:
            continue
        score = fuzz.token_set_ratio(c_norm, normalize_title(ex["title"]))
        if score >= threshold and score > best_score:
            best, best_score = ex, score
    return best


def dedupe_batch(events: list[dict[str, Any]], threshold: int = 85, window_days: int = 1) -> list[dict[str, Any]]:
    """Collapse duplicates inside one batch (earliest in list wins; alt URLs appended)."""
    kept: list[dict[str, Any]] = []
    for ev in events:
        dup = find_duplicate(ev, kept, threshold, window_days)
        if dup is None:
            ev.setdefault("alt_urls", [])
            kept.append(ev)
        else:
            u = ev.get("url")
            if u and u != dup.get("url") and u not in dup.setdefault("alt_urls", []):
                dup["alt_urls"].append(u)
            # fill in blanks from the duplicate
            for k in ("location", "end_dt", "description_short", "host_org"):
                if not dup.get(k) and ev.get(k):
                    dup[k] = ev[k]
            if ev.get("speakers") and not dup.get("speakers"):
                dup["speakers"] = ev["speakers"]
    return kept


def window_bounds(start: datetime, window_days: int) -> tuple[str, str]:
    lo = (start - timedelta(days=window_days)).replace(hour=0, minute=0, second=0)
    hi = (start + timedelta(days=window_days + 1)).replace(hour=0, minute=0, second=0)
    return lo.isoformat(), hi.isoformat()
