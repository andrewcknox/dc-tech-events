"""Import events from a JSON file written by a Claude Code session (or by hand).

File shape:  {"source": "Substack backlog", "tags": ["substack"], "events": [ {...}, ... ]}
Each event:  title, start (ISO or natural language), end (opt), location (opt), virtual (bool),
             url, host, description (opt), speakers (opt list), topics (opt list), fit (1-5, opt),
             why (opt), tags (opt list), approved ("y" | "n" | "", opt; default "y" if fit >= 3)
Idempotent: re-importing the same file changes nothing. Existing events get any new tags appended.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from . import db
from .config import Source, load_config
from .dedupe import find_duplicate, window_bounds
from .models import TOPICS, TZ, fingerprint, parse_datetime, to_iso


def _norm(raw: dict[str, Any], default_tags: list[str], source: str) -> dict[str, Any] | None:
    start = parse_datetime(raw.get("start") or raw.get("start_dt") or raw.get("start_datetime"))
    if not start or not (raw.get("title") or "").strip():
        return None
    topics = [t for t in (raw.get("topics") or []) if t in TOPICS]
    fit = raw.get("fit") or raw.get("fit_score")
    fit = int(fit) if fit is not None else None
    approved = raw.get("approved")
    if approved is None:
        approved = "y" if (fit or 0) >= 3 else ""
    return {
        "title": raw["title"].strip(),
        "start_dt": to_iso(start),
        "end_dt": to_iso(parse_datetime(raw.get("end") or raw.get("end_dt") or raw.get("end_datetime"))),
        "location": (raw.get("location") or "").strip() or None,
        "virtual": bool(raw.get("virtual", False)),
        "url": (raw.get("url") or "").strip() or None,
        "host_org": (raw.get("host") or raw.get("host_org") or source).strip(),
        "description_short": " ".join(str(raw.get("description") or raw.get("description_short") or "").split()[:40]),
        "speakers": list(raw.get("speakers") or []),
        "tags": sorted(set(default_tags) | set(raw.get("tags") or [])),
        "topics": topics,
        "fit_score": fit,
        "one_line_why": raw.get("why") or raw.get("one_line_why") or "",
        "relevant": raw.get("relevant"),
        "approved": approved if approved in ("y", "n", "") else "",
        "review_note": raw.get("note") or "",
    }


def import_file(path: Path, today: datetime | None = None, keep_past: bool = True) -> dict[str, int]:
    cfg = load_config()
    today = today or datetime.now(TZ)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    source = data.get("source") or Path(path).stem
    default_tags = list(data.get("tags") or [])
    con = db.connect()
    stats = {"new": 0, "updated": 0, "skipped": 0}
    for raw in data.get("events", []):
        ev = _norm(raw, default_tags, source)
        if ev is None:
            stats["skipped"] += 1
            continue
        start = datetime.fromisoformat(ev["start_dt"])
        if not keep_past and start < today:
            stats["skipped"] += 1
            continue
        ev["fingerprint"] = fingerprint(ev["title"], start)
        ev["source_name"] = source
        lo, hi = window_bounds(start, int(cfg["dedupe_window_days"]))
        dup = find_duplicate(ev, db.events_between(con, lo, hi), int(cfg["dedupe_threshold"]), int(cfg["dedupe_window_days"]))
        if dup:
            db.touch_event(con, dup["id"], ev.get("url"), ev["tags"])
            fill = {}
            for k in ("topics", "fit_score", "one_line_why", "location", "end_dt", "description_short"):
                if not dup.get(k) and ev.get(k):
                    fill[k] = ev[k]
            if ev.get("relevant") is not None and dup.get("relevant") is None:
                fill["relevant"] = 1 if ev["relevant"] else 0
            if not dup.get("approved") and ev.get("approved"):
                fill["approved"] = ev["approved"]
            if fill:
                db.update_event(con, dup["id"], **fill)
            stats["updated"] += 1
        else:
            eid = db.insert_event(con, ev)
            rel = ev["relevant"]
            if rel is None:
                rel = 1 if (ev["fit_score"] or 0) >= 2 or ev["topics"] else 0
            db.update_event(
                con, eid, relevant=1 if rel else 0, topics=ev["topics"], fit_score=ev["fit_score"],
                one_line_why=ev["one_line_why"], classify_raw="claude-session", approved=ev["approved"],
                review_note=ev["review_note"],
            )
            stats["new"] += 1
    con.commit()
    con.close()
    return stats


def dump_pages_dir():
    from .config import ROOT
    d = ROOT / "inbox" / "pages"
    d.mkdir(parents=True, exist_ok=True)
    return d


def source_stub(src: Source) -> str:
    return "".join(c if c.isalnum() else "_" for c in src.name).strip("_").lower()
