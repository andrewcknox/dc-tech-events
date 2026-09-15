"""Fetch every enabled source and turn it into event dicts.

ics  -> icalendar (no Claude needed)
rss  -> feedparser; items become text and go through Claude (event feeds rarely carry structured dates)
html -> requests (or Playwright when js: true) -> boilerplate stripped -> Claude structured extraction
eventbrite_org -> the organiser page's embedded JSON-LD (no Claude needed)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import feedparser
import requests
from icalendar import Calendar
from selectolax.parser import HTMLParser

from . import db, llm
from .config import Source, load_config, load_sources
from .dedupe import find_duplicate, window_bounds
from .models import TZ, ExtractedEvent, content_hash, fingerprint, is_past, parse_datetime, to_iso

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
STRIP_TAGS = "script, style, noscript, svg, iframe, nav, footer, header, form, button, [aria-hidden=true], .cookie, #cookie-banner"


# ---------- transport ----------

def get_text(url: str, js: bool, cfg: dict[str, Any]) -> str:
    if js:
        return _get_with_playwright(url)
    r = requests.get(url, headers={"User-Agent": BROWSER_UA, "Accept": "*/*"}, timeout=40)
    r.raise_for_status()
    if "just a moment" in r.text[:2000].lower() and "cloudflare" in r.text.lower():
        raise RuntimeError("Cloudflare challenge page; set js: true for this source")
    return r.text


def _get_with_playwright(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("js: true source but Playwright is not installed (uv sync --extra js; uv run playwright install chromium)") from e
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=BROWSER_UA)
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1500)
        html = page.content()
        browser.close()
    return html


# ---------- HTML -> text ----------

def html_to_text(html: str, base_url: str = "") -> str:
    """Strip boilerplate; keep link targets inline so Claude can return event URLs."""
    tree = HTMLParser(html)
    for n in tree.css(STRIP_TAGS):
        n.decompose()
    root = tree.css_first("main") or tree.css_first("article") or tree.body or tree.root
    if root is None:
        return ""
    for a in root.css("a[href]"):
        href = a.attributes.get("href") or ""
        if href.startswith(("#", "javascript:", "mailto:")):
            continue
        full = urljoin(base_url, href)
        txt = (a.text() or "").strip()
        if txt and len(txt) > 2:
            a.replace_with(f"{txt} <{full}>")
    text = root.text(separator="\n")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def chunk_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks, cur = [], []
    size = 0
    for line in text.split("\n"):
        if size + len(line) > max_chars and cur:
            chunks.append("\n".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks


# ---------- per-type parsers ----------

def parse_ics(raw: str, src: Source) -> list[dict[str, Any]]:
    cal = Calendar.from_ical(raw)
    out = []
    for comp in cal.walk("VEVENT"):
        start = parse_datetime(comp.decoded("DTSTART")) if comp.get("DTSTART") else None
        if not start:
            continue
        end = parse_datetime(comp.decoded("DTEND")) if comp.get("DTEND") else None
        loc = str(comp.get("LOCATION") or "").strip() or None
        desc = re.sub(r"\s+", " ", str(comp.get("DESCRIPTION") or "")).strip()
        url = str(comp.get("URL") or "").strip() or src.url
        out.append({
            "title": str(comp.get("SUMMARY") or "").strip(),
            "start_dt": to_iso(start), "end_dt": to_iso(end),
            "location": loc, "virtual": bool(re.search(r"\b(virtual|online|zoom|webinar)\b", f"{loc or ''} {desc[:300]}", re.I)),
            "url": url, "host_org": src.name,
            "description_short": " ".join(desc.split()[:40]),
            "speakers": [],
        })
    return out


def parse_eventbrite(html: str, src: Source) -> list[dict[str, Any]]:
    tree = HTMLParser(html)
    out = []
    for s in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(s.text())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if not isinstance(it, dict) or it.get("@type") not in ("Event", "SocialEvent", "BusinessEvent"):
                continue
            start = parse_datetime(it.get("startDate"))
            if not start:
                continue
            loc = it.get("location") or {}
            if isinstance(loc, dict):
                addr = loc.get("address")
                if isinstance(addr, dict):
                    addr = ", ".join(str(v) for k, v in addr.items() if k != "@type" and v)
                loc_s = ", ".join(x for x in [loc.get("name"), addr if isinstance(addr, str) else None] if x)
                virtual = "Virtual" in str(loc.get("@type", ""))
            else:
                loc_s, virtual = str(loc), False
            out.append({
                "title": it.get("name", "").strip(), "start_dt": to_iso(start),
                "end_dt": to_iso(parse_datetime(it.get("endDate"))), "location": loc_s or None,
                "virtual": virtual, "url": it.get("url") or src.url,
                "host_org": (it.get("organizer") or {}).get("name", src.name) if isinstance(it.get("organizer"), dict) else src.name,
                "description_short": " ".join(str(it.get("description", "")).split()[:40]), "speakers": [],
            })
    return out


def rss_to_text(raw: str) -> str:
    feed = feedparser.parse(raw)
    parts = []
    for e in feed.entries:
        body = e.get("summary") or (e.get("content") or [{}])[0].get("value", "") or ""
        body = html_to_text(body) if "<" in body else body
        when = e.get("published") or e.get("updated") or ""
        parts.append(f"### {e.get('title','').strip()}\nLink: {e.get('link','')}\nPublished: {when}\n{body}\n")
    return "\n".join(parts)


# ---------- Claude extraction with cache ----------

def extract_with_cache(con, text: str, src: Source, cfg: dict[str, Any], today: datetime) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for chunk in chunk_text(text, int(cfg["max_chunk_chars"])):
        h = content_hash(f"{src.url}\n{chunk}")
        cached = db.cache_get(con, h)
        if cached:
            llm.SPEND.cache_hits += 1
            raw = json.loads(cached["extracted_json"])
        else:
            result, usage = llm.extract_events(chunk, src.url, src.name, today, cfg["model"])
            raw = [e.model_dump() for e in result.events]
            db.cache_put(con, h, src.name, raw, getattr(usage, "input_tokens", 0), getattr(usage, "output_tokens", 0))
            con.commit()
        events.extend(normalize_extracted(raw, src))
    return events


def normalize_extracted(raw: list[dict[str, Any]], src: Source) -> list[dict[str, Any]]:
    out = []
    for d in raw:
        try:
            e = ExtractedEvent.model_validate(d)
        except Exception:  # noqa: BLE001
            continue
        start = parse_datetime(e.start_datetime)
        if not start or not e.title.strip():
            continue
        out.append({
            "title": e.title.strip(), "start_dt": to_iso(start), "end_dt": to_iso(parse_datetime(e.end_datetime)),
            "location": (e.location or "").strip() or None, "virtual": bool(e.virtual),
            "url": urljoin(src.url, e.url) if e.url else src.url, "host_org": e.host_org or src.name,
            "description_short": " ".join(e.description_short.split()[:40]), "speakers": list(e.speakers or []),
        })
    return out


# ---------- orchestration ----------

def fetch_source(con, src: Source, cfg: dict[str, Any], today: datetime) -> list[dict[str, Any]]:
    if src.type == "ics":
        return parse_ics(get_text(src.url, src.js, cfg), src)
    if src.type == "eventbrite_org":
        return parse_eventbrite(get_text(src.url, src.js, cfg), src)
    if src.type == "rss":
        text = rss_to_text(get_text(src.url, src.js, cfg))
    elif src.type == "html":
        text = html_to_text(get_text(src.url, src.js, cfg), src.url)
    else:
        raise ValueError(f"unknown source type {src.type!r}")
    if len(text) < 200:
        return []
    if cfg.get("extraction", "session") == "api":
        return extract_with_cache(con, text, src, cfg, today)
    # session mode: save the page text for a Claude Code session to read; no events extracted here
    from .importer import dump_pages_dir, source_stub
    out = dump_pages_dir() / f"{source_stub(src)}.txt"
    header = f"# {src.name}\n# {src.url}\n# fetched {today.isoformat()}\n# tags: {', '.join(src.tags)}\n\n"
    out.write_text(header + text, encoding="utf-8")
    raise PageDumped(out.name, len(text))


class PageDumped(Exception):
    """Not an error: the page text was written to inbox/pages for a session to read."""

    def __init__(self, path: str, n_chars: int):
        super().__init__(path)
        self.path, self.n_chars = path, n_chars


def upsert_events(con, events: list[dict[str, Any]], src: Source, cfg: dict[str, Any], today: datetime) -> tuple[int, int]:
    """Insert new events, touch duplicates. Returns (new, seen_again)."""
    new = seen = 0
    for ev in events:
        start = parse_datetime(ev["start_dt"])
        if start is None or is_past(start, today, grace_hours=6):
            continue
        ev["fingerprint"] = fingerprint(ev["title"], start)
        ev["source_name"] = src.name
        lo, hi = window_bounds(start, int(cfg["dedupe_window_days"]))
        dup = find_duplicate(ev, db.events_between(con, lo, hi), int(cfg["dedupe_threshold"]), int(cfg["dedupe_window_days"]))
        if dup:
            db.touch_event(con, dup["id"], ev.get("url"), ev.get("tags"))
            seen += 1
        else:
            db.insert_event(con, ev)
            new += 1
    con.commit()
    return new, seen


def run_fetch(only: list[str] | None = None, today: datetime | None = None) -> list[dict[str, Any]]:
    cfg = load_config()
    today = today or datetime.now(TZ)
    con = db.connect()
    report = []
    for src in load_sources():
        if only and src.name not in only:
            continue
        try:
            events = fetch_source(con, src, cfg, today)
            for ev in events:
                ev["tags"] = list(src.tags)
            new, seen = upsert_events(con, events, src, cfg, today)
            status = "ok" if events else "empty"
            msg = f"{len(events)} parsed, {new} new, {seen} seen again"
            db.log_source_status(con, src.name, status, len(events), msg)
        except PageDumped as d:
            status, msg, new = "ok", f"saved inbox/pages/{d.path} ({d.n_chars:,} chars) for session extraction", 0
            db.log_source_status(con, src.name, status, 0, msg)
        except Exception as e:  # noqa: BLE001
            status, msg, new = "failed", f"{type(e).__name__}: {e}", 0
            db.log_source_status(con, src.name, status, 0, msg)
        con.commit()
        report.append({"source": src.name, "status": status, "new": new, "message": msg,
                       "consecutive_failures": db.consecutive_failures(con, src.name)})
    con.close()
    return report
