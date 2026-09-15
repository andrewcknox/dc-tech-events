"""SQLite storage. One file, a handful of tables, no ORM."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  fingerprint TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  start_dt TEXT NOT NULL,
  end_dt TEXT,
  location TEXT,
  virtual INTEGER DEFAULT 0,
  url TEXT,
  alt_urls TEXT DEFAULT '[]',
  host_org TEXT,
  description_short TEXT,
  speakers TEXT DEFAULT '[]',
  source_name TEXT,
  first_seen TEXT,
  last_seen TEXT,
  lat REAL,
  lon REAL,
  geocode_status TEXT,
  relevant INTEGER,
  topics TEXT,
  fit_score INTEGER,
  one_line_why TEXT,
  classify_raw TEXT,
  approved TEXT DEFAULT '',
  review_note TEXT DEFAULT '',
  tags TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_dt);

CREATE TABLE IF NOT EXISTS sources_status (
  id INTEGER PRIMARY KEY,
  source_name TEXT NOT NULL,
  run_at TEXT NOT NULL,
  status TEXT NOT NULL,
  n_events INTEGER DEFAULT 0,
  message TEXT
);

CREATE TABLE IF NOT EXISTS extraction_cache (
  content_hash TEXT PRIMARY KEY,
  source_name TEXT,
  extracted_json TEXT,
  input_tokens INTEGER DEFAULT 0,
  output_tokens INTEGER DEFAULT 0,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS geocode_cache (
  query TEXT PRIMARY KEY,
  lat REAL,
  lon REAL,
  display_name TEXT,
  created_at TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(events)")}
    if "tags" not in cols:
        con.execute("ALTER TABLE events ADD COLUMN tags TEXT DEFAULT '[]'")
    return con


def row_to_dict(r: sqlite3.Row | None) -> dict[str, Any] | None:
    if r is None:
        return None
    d = dict(r)
    for k in ("alt_urls", "speakers", "topics", "tags"):
        if isinstance(d.get(k), str):
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                d[k] = []
    return d


# ---------- events ----------

def get_event_by_fingerprint(con: sqlite3.Connection, fp: str) -> dict | None:
    return row_to_dict(con.execute("SELECT * FROM events WHERE fingerprint=?", (fp,)).fetchone())


def events_between(con: sqlite3.Connection, start_iso: str, end_iso: str) -> list[dict]:
    rows = con.execute(
        "SELECT * FROM events WHERE start_dt >= ? AND start_dt < ? ORDER BY start_dt",
        (start_iso, end_iso),
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def insert_event(con: sqlite3.Connection, ev: dict[str, Any]) -> int:
    ts = now_iso()
    cur = con.execute(
        """INSERT INTO events (fingerprint,title,start_dt,end_dt,location,virtual,url,alt_urls,
             host_org,description_short,speakers,source_name,first_seen,last_seen,tags)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ev["fingerprint"], ev["title"], ev["start_dt"], ev.get("end_dt"), ev.get("location"),
            1 if ev.get("virtual") else 0, ev.get("url"), json.dumps(ev.get("alt_urls") or []),
            ev.get("host_org"), ev.get("description_short"), json.dumps(ev.get("speakers") or []),
            ev.get("source_name"), ts, ts, json.dumps(ev.get("tags") or []),
        ),
    )
    return int(cur.lastrowid)


def touch_event(con: sqlite3.Connection, event_id: int, alt_url: str | None = None, tags: list[str] | None = None) -> None:
    row = con.execute("SELECT alt_urls, url, tags FROM events WHERE id=?", (event_id,)).fetchone()
    alts = json.loads(row["alt_urls"] or "[]")
    if alt_url and alt_url != row["url"] and alt_url not in alts:
        alts.append(alt_url)
    cur_tags = json.loads(row["tags"] or "[]")
    for t in tags or []:
        if t not in cur_tags:
            cur_tags.append(t)
    con.execute(
        "UPDATE events SET last_seen=?, alt_urls=?, tags=? WHERE id=?",
        (now_iso(), json.dumps(alts), json.dumps(cur_tags), event_id),
    )


def update_event(con: sqlite3.Connection, event_id: int, **fields: Any) -> None:
    if not fields:
        return
    for k, v in list(fields.items()):
        if isinstance(v, (list, dict)):
            fields[k] = json.dumps(v)
    sets = ", ".join(f"{k}=?" for k in fields)
    con.execute(f"UPDATE events SET {sets} WHERE id=?", (*fields.values(), event_id))


def unclassified_events(con: sqlite3.Connection, after_iso: str) -> list[dict]:
    rows = con.execute(
        "SELECT * FROM events WHERE relevant IS NULL AND start_dt >= ? ORDER BY start_dt",
        (after_iso,),
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def ungeocoded_events(con: sqlite3.Connection, after_iso: str) -> list[dict]:
    rows = con.execute(
        "SELECT * FROM events WHERE geocode_status IS NULL AND start_dt >= ? ORDER BY start_dt",
        (after_iso,),
    ).fetchall()
    return [row_to_dict(r) for r in rows]


# ---------- sources_status ----------

def log_source_status(con: sqlite3.Connection, name: str, status: str, n: int, msg: str = "") -> None:
    con.execute(
        "INSERT INTO sources_status (source_name, run_at, status, n_events, message) VALUES (?,?,?,?,?)",
        (name, now_iso(), status, n, msg[:500]),
    )


def consecutive_failures(con: sqlite3.Connection, name: str, limit: int = 10) -> int:
    rows = con.execute(
        "SELECT status FROM sources_status WHERE source_name=? ORDER BY id DESC LIMIT ?",
        (name, limit),
    ).fetchall()
    n = 0
    for r in rows:
        if r["status"] == "failed":
            n += 1
        else:
            break
    return n


def latest_status(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute(
        """SELECT s.* FROM sources_status s
           JOIN (SELECT source_name, MAX(id) AS mid FROM sources_status GROUP BY source_name) m
             ON s.id = m.mid ORDER BY s.source_name"""
    ).fetchall()
    return [dict(r) for r in rows]


# ---------- caches ----------

def cache_get(con: sqlite3.Connection, h: str) -> dict | None:
    r = con.execute("SELECT * FROM extraction_cache WHERE content_hash=?", (h,)).fetchone()
    return dict(r) if r else None


def cache_put(con: sqlite3.Connection, h: str, source: str, payload: Any, in_tok: int, out_tok: int) -> None:
    con.execute(
        "INSERT OR REPLACE INTO extraction_cache VALUES (?,?,?,?,?,?)",
        (h, source, json.dumps(payload), in_tok, out_tok, now_iso()),
    )


def geocache_get(con: sqlite3.Connection, q: str) -> dict | None:
    r = con.execute("SELECT * FROM geocode_cache WHERE query=?", (q,)).fetchone()
    return dict(r) if r else None


def geocache_put(con: sqlite3.Connection, q: str, lat: float | None, lon: float | None, name: str = "") -> None:
    con.execute(
        "INSERT OR REPLACE INTO geocode_cache VALUES (?,?,?,?,?)",
        (q, lat, lon, name, now_iso()),
    )


def executemany(con: sqlite3.Connection, sql: str, rows: Iterable[tuple]) -> None:
    con.executemany(sql, rows)
