from datetime import datetime

from dte import db, digest, review
from dte.models import TZ


def _seed(con):
    for i, (title, fit, rel) in enumerate([("AI Export Controls Briefing", 5, 1), ("Campus Bake Sale", 1, 0), ("Quantum Policy Panel", 3, 1)]):
        db.insert_event(con, {
            "fingerprint": f"fp{i}", "title": title, "start_dt": f"2026-09-{15 + i}T14:00:00-04:00",
            "url": f"https://x/{i}", "host_org": "CSIS", "location": "CSIS, 1616 Rhode Island Ave NW", "source_name": "CSIS",
        })
        db.update_event(con, i + 1, relevant=rel, fit_score=fit, topics=["AI"], one_line_why="why", lat=38.9, lon=-77.03, geocode_status="venue")
    con.commit()


def test_review_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DTE_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(review, "REVIEW_DIR", tmp_path / "review")
    con = db.connect()
    _seed(con)
    con.close()

    today = datetime(2026, 9, 13, tzinfo=TZ)
    path = review.write_pending(today)
    text = path.read_text(encoding="utf-8")
    assert "AI Export Controls" in text and "Quantum Policy" in text and "Bake Sale" not in text

    # human edits: approve row 1, reject row 3 with a note
    lines = []
    for line in text.splitlines():
        if line.startswith("| 1 |"):
            line = line.replace("| 1 |  |", "| 1 | y |", 1)
        if line.startswith("| 3 |"):
            line = line.replace("| 3 |  |", "| 3 | n |", 1).rsplit("|", 2)[0] + "| too niche |"
        lines.append(line)
    path.write_text("\n".join(lines), encoding="utf-8")

    assert review.apply_reviews() == 2
    con = db.connect()
    rows = {r[0]: (r[1], r[2]) for r in con.execute("SELECT id, approved, review_note FROM events")}
    assert rows[1] == ("y", "") and rows[3] == ("n", "too niche") and rows[2][0] == ""
    con.close()
    assert review.write_pending(today) is None  # nothing left to review


def test_auto_approve_score(tmp_path, monkeypatch):
    monkeypatch.setenv("DTE_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(review, "REVIEW_DIR", tmp_path / "review")
    con = db.connect(); _seed(con); con.close()
    path = review.write_pending(datetime(2026, 9, 13, tzinfo=TZ), auto_approve_score=5)
    con = db.connect()
    assert con.execute("SELECT approved FROM events WHERE id=1").fetchone()[0] == "y"
    assert "Quantum" in path.read_text(encoding="utf-8")


def test_digest_markdown_and_site(tmp_path, monkeypatch):
    monkeypatch.setenv("DTE_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(digest, "DIGEST_DIR", tmp_path / "digest")
    monkeypatch.setattr(digest, "DOCS_DIR", tmp_path / "docs")
    con = db.connect(); _seed(con)
    db.update_event(con, 1, approved="y")
    for _ in range(3):
        db.log_source_status(con, "Wilson Center", "failed", 0, "Timeout")
    con.commit(); con.close()

    path = digest.run_digest(datetime(2026, 9, 13, tzinfo=TZ))
    md = path.read_text(encoding="utf-8")
    assert path.name == "2026-W37.md"
    assert "AI Export Controls Briefing" in md and "Quantum" not in md  # only approved
    assert "`AI`" in md and "Wilson Center: 3 failures" in md
    html = (tmp_path / "docs" / "index.html").read_text(encoding="utf-8")
    assert "AI Export Controls Briefing" in html and "leaflet" in html
    assert (tmp_path / "docs" / "events.json").exists()
