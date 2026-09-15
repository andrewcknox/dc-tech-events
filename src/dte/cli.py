"""`dte` command line: fetch / review / apply-review / digest / probe / stats."""
from __future__ import annotations

from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table

from .models import TZ

app = typer.Typer(help="dc-tech-events: track and map emerging-tech policy events in DC.", no_args_is_help=True)
console = Console()


@app.command()
def fetch(
    source: list[str] = typer.Option(None, "--source", "-s", help="Only these source names (repeatable)."),
    no_classify: bool = typer.Option(False, help="Skip the Claude classification step."),
):
    """Pull all enabled sources, dedupe, classify new events, geocode, print health + cost."""
    from . import db, llm
    from .classify import run_classify
    from .fetch import run_fetch
    from .geocode import geocode_pending

    from .config import load_config

    today = datetime.now(TZ)
    report = run_fetch(only=source or None, today=today)
    n_cls = 0 if (no_classify or load_config().get("extraction") != "api") else run_classify(today)
    con = db.connect()
    n_geo = geocode_pending(con, today.isoformat())
    con.close()

    t = Table(title="Source health", show_lines=False)
    for col in ("Source", "Status", "New", "Detail", "Fails in a row"):
        t.add_column(col)
    for r in report:
        colour = {"ok": "green", "empty": "yellow", "failed": "red"}[r["status"]]
        t.add_row(r["source"], f"[{colour}]{r['status']}[/]", str(r["new"]), r["message"][:90], str(r["consecutive_failures"]))
    console.print(t)
    console.print(f"classified: {n_cls}   geocoded: {n_geo}")
    console.print(llm.SPEND.summary())


@app.command()
def review(auto_approve_score: int = typer.Option(None, help="Auto-approve events with fit >= this (lazy mode). Off by default.")):
    """Write review/pending_YYYY-MM-DD.md for a human to mark approve = y/n."""
    from .review import apply_reviews, write_pending

    applied = apply_reviews()
    path = write_pending(auto_approve_score=auto_approve_score)
    console.print(f"applied {applied} earlier decisions")
    console.print(f"wrote {path}" if path else "nothing new to review")


@app.command("apply-review")
def apply_review():
    """Read edited review/pending_*.md files and store the y/n decisions."""
    from .review import apply_reviews

    console.print(f"applied {apply_reviews()} decisions")


@app.command()
def digest():
    """Build digest/YYYY-WW.md and the docs/ map site; post to DIGEST_WEBHOOK_URL if set."""
    from .digest import run_digest
    from .review import apply_reviews

    apply_reviews()
    path = run_digest()
    console.print(f"wrote {path} and docs/index.html")


@app.command("import")
def import_cmd(path: list[str] = typer.Argument(..., help="JSON file(s) of events, e.g. inbox/2026-09-14.json")):
    """Import events from JSON written by a Claude Code session (or by hand). Idempotent."""
    from pathlib import Path

    from . import db
    from .geocode import geocode_pending
    from .importer import import_file

    for p in path:
        stats = import_file(Path(p))
        console.print(f"{p}: {stats['new']} new, {stats['updated']} updated, {stats['skipped']} skipped")
    con = db.connect()
    n = geocode_pending(con, "1970-01-01")
    con.close()
    console.print(f"geocoded {n}")


@app.command()
def probe():
    """Check every source URL: reachable? feed available? JavaScript needed?"""
    from .probe import probe_all, render_markdown

    md = render_markdown(probe_all())
    console.print(md, markup=False)


@app.command()
def stats():
    """Quick counts from the database."""
    from . import db

    con = db.connect()
    def q(sql: str) -> int:
        return int(con.execute(sql).fetchone()[0])

    n_ev, n_rel = q("SELECT COUNT(*) FROM events"), q("SELECT COUNT(*) FROM events WHERE relevant=1")
    n_ok, n_cache = q("SELECT COUNT(*) FROM events WHERE approved='y'"), q("SELECT COUNT(*) FROM extraction_cache")
    console.print(f"events: {n_ev}  relevant: {n_rel}  approved: {n_ok}  cache entries: {n_cache}")
    con.close()


if __name__ == "__main__":
    app()
