import json
from datetime import datetime

from dte import db, digest
from dte.importer import import_file
from dte.models import TZ


def _write(tmp_path, name, payload):
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_import_is_idempotent_and_merges_tags(tmp_path, monkeypatch):
    monkeypatch.setenv("DTE_DB", str(tmp_path / "t.db"))
    p = _write(tmp_path, "a.json", {"source": "Substack", "tags": ["substack"], "events": [
        {"title": "AI and National Security", "start": "2026-10-01 14:00", "url": "https://a/1", "host": "CSIS",
         "topics": ["AI", "bogus-topic"], "fit": 5, "why": "core", "tags": ["think-tank"]},
        {"title": "Bake sale", "start": "2026-10-02", "host": "Club", "fit": 1, "topics": []},
        {"title": "no date"},
    ]})
    s1 = import_file(p, today=datetime(2026, 9, 14, tzinfo=TZ))
    assert s1 == {"new": 2, "updated": 0, "skipped": 1}
    s2 = import_file(p)
    assert s2 == {"new": 0, "updated": 2, "skipped": 1}

    # same event from the SAIS list: merged, tags unioned, still one row
    q = _write(tmp_path, "b.json", {"source": "T&I list", "tags": ["sais-internal"], "events": [
        {"title": "AI & National Security (panel)", "start": "2026-10-01 14:00", "location": "Room 422, Hopkins Bloomberg Center", "fit": 4}
    ]})
    assert import_file(q)["updated"] == 1
    con = db.connect()
    rows = [db.row_to_dict(r) for r in con.execute("SELECT * FROM events ORDER BY id")]
    assert len(rows) == 2
    ev = rows[0]
    assert sorted(ev["tags"]) == ["sais-internal", "substack", "think-tank"]
    assert ev["topics"] == ["AI"] and ev["approved"] == "y" and ev["location"].startswith("Room 422")
    assert rows[1]["approved"] == "" and rows[1]["relevant"] == 0
    con.close()


def test_public_and_internal_split():
    assert digest._is_public(["substack", "think-tank"])
    assert digest._is_public(["sais-internal", "substack"])  # cross-listed -> public too
    assert not digest._is_public(["sais-internal", "sais"])
