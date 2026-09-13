"""Classify every not-yet-classified upcoming event with one Claude call each."""
from __future__ import annotations

from datetime import datetime

from . import db, llm
from .config import load_config
from .models import TZ


def run_classify(today: datetime | None = None, limit: int | None = None) -> int:
    cfg = load_config()
    today = today or datetime.now(TZ)
    con = db.connect()
    pending = db.unclassified_events(con, today.isoformat())
    if limit:
        pending = pending[:limit]
    for ev in pending:
        c, raw = llm.classify_event(ev, cfg["model"])
        db.update_event(
            con, ev["id"],
            relevant=1 if c.relevant else 0, topics=c.topics,
            fit_score=int(c.audience_fit_for_sais_students), one_line_why=c.one_line_why, classify_raw=raw,
        )
        con.commit()
    con.close()
    return len(pending)
