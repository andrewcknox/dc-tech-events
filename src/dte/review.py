"""Human review step.

`dte review`        -> writes review/pending_YYYY-MM-DD.md (a Markdown table with approve/note columns)
`dte apply-review`  -> reads every review/pending_*.md back and stores approve=y/n + note in the DB
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import db
from .config import ROOT, load_config
from .models import TZ

REVIEW_DIR = ROOT / "review"
HEADER = "| id | approve | date | title | host | fit | why | note |"
SEP = "|---|---|---|---|---|---|---|---|"


def _cell(s: str | None) -> str:
    return (s or "").replace("|", "/").replace("\n", " ").strip()


def write_pending(today: datetime | None = None, auto_approve_score: int | None = None) -> Path | None:
    cfg = load_config()
    today = today or datetime.now(TZ)
    con = db.connect()
    rows = con.execute(
        """SELECT * FROM events WHERE relevant=1 AND fit_score >= ? AND approved='' AND start_dt >= ?
           ORDER BY start_dt""",
        (int(cfg["min_fit_for_review"]), today.isoformat()),
    ).fetchall()
    events = [db.row_to_dict(r) for r in rows]

    if auto_approve_score is not None:
        auto = [e for e in events if (e["fit_score"] or 0) >= auto_approve_score]
        for e in auto:
            db.update_event(con, e["id"], approved="y", review_note=f"auto-approved (fit>={auto_approve_score})")
        con.commit()
        events = [e for e in events if e not in auto]

    if not events:
        con.close()
        return None

    REVIEW_DIR.mkdir(exist_ok=True)
    path = REVIEW_DIR / f"pending_{today.date().isoformat()}.md"
    lines = [
        f"# Pending review — {today.date().isoformat()}",
        "",
        "Put `y` in the **approve** column to include an event in the digest, `n` to reject it. Leave blank to decide later.",
        "Anything you type in **note** is saved with the event. Then run `uv run dte apply-review` (or just commit; the digest job does it).",
        "",
        HEADER, SEP,
    ]
    for e in events:
        d = e["start_dt"][:16].replace("T", " ")
        topics = ", ".join(e.get("topics") or [])
        lines.append(
            f"| {e['id']} |  | {d} | [{_cell(e['title'])}]({e['url']}) | {_cell(e['host_org'])} | "
            f"{e['fit_score']} | {_cell(e['one_line_why'])} ({topics}) |  |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    con.close()
    return path


ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]*)\|(?:[^|]*\|){5}\s*([^|]*)\|\s*$")


def apply_reviews() -> int:
    """Read every pending file; apply y/n decisions. Returns number of rows applied."""
    if not REVIEW_DIR.exists():
        return 0
    con = db.connect()
    n = 0
    for path in sorted(REVIEW_DIR.glob("pending_*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = ROW_RE.match(line)
            if not m:
                continue
            event_id, approve, note = int(m.group(1)), m.group(2).strip().lower(), m.group(3).strip()
            if approve in ("y", "yes", "n", "no"):
                db.update_event(con, event_id, approved=approve[0], review_note=note)
                n += 1
    con.commit()
    con.close()
    return n
