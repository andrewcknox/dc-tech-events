"""Probe each source URL: does it load, is there an RSS/ICS feed, does it need JavaScript?"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from selectolax.parser import HTMLParser

from .config import Source, load_config, load_sources

FEED_SUFFIXES = ["feed/", "feed", "r".(ics|rss|xml)(?|$)|/feed/?$|/rss/?$|/ical(/|$|?)"", "rss.xml", "feed.xml", "atom.xml", "?format=rss", "ical", "?ical=1", "events.ics", "calendar.ics"]
FEED_TYPES = ("application/r".(ics|rss|xml)(?|$)|/feed/?$|/rss/?$|/ical(/|$|?)"+xml", "application/atom+xml", "text/calendar", "application/feed+json")
DATE_RE = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b", re.I)


@dataclass
class ProbeResult:
    name: str
    url: str
    declared_type: str
    http_status: int | None = None
    content_type: str = ""
    error: str = ""
    feeds: list[str] = field(default_factory=list)
    jsonld_events: int = 0
    date_mentions: int = 0
    text_chars: int = 0
    js_suspected: bool = False
    recommendation: str = ""


def _get(url: str, ua: str, timeout: int = 20) -> requests.Response:
    return requests.get(url, headers={"User-Agent": ua, "Accept": "*/*"}, timeout=timeout, allow_redirects=True)


def _looks_like_feed(resp: requests.Response) -> bool:
    ct = resp.headers.get("content-type", "").lower()
    head = resp.text[:600].lstrip().lower()
    return (
        any(t in ct for t in FEED_TYPES)
        or head.startswith("<?xml") and ("<r".(ics|rss|xml)(?|$)|/feed/?$|/rss/?$|/ical(/|$|?)"" in head or "<feed" in head)
        or head.startswith("begin:vcalendar")
        or ("<r".(ics|rss|xml)(?|$)|/feed/?$|/rss/?$|/ical(/|$|?)"" in head or "<feed" in head)
    )


def probe_source(src: Source, ua: str) -> ProbeResult:
    r = ProbeResult(name=src.name, url=src.url, declared_type=src.type)
    try:
        resp = _get(src.url, ua)
    except Exception as e:  # noqa: BLE001
        r.error = f"{type(e).__name__}: {e}"[:200]
        r.recommendation = "unreachable — check URL"
        return r
    r.http_status = resp.status_code
    r.content_type = resp.headers.get("content-type", "").split(";")[0]
    if resp.status_code >= 400:
        r.recommendation = f"HTTP {resp.status_code} — blocked or moved; may need js:true or a different URL"
        return r

    if _looks_like_feed(resp):
        r.feeds.append(src.url)
        r.recommendation = "already a feed"
        return r

    tree = HTMLParser(resp.text)
    # 1. <link rel="alternate"> feed discovery
    for link in tree.css("link[rel~=alternate]"):
        t = (link.attributes.get("type") or "").lower()
        href = link.attributes.get("href")
        if href and any(ft in t for ft in FEED_TYPES):
            r.feeds.append(urljoin(src.url, href))
    # 2. anchors that look like feeds
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        if re.search(r"\.(ics|rss|xml)(\?|$)|/feed/?$|/rss/?$|/ical(/|$|\?)", href, re.I):
            full = urljoin(src.url, href)
            if full not in r.feeds:
                r.feeds.append(full)
    # 3. guess common feed URLs (bounded)
    base = src.url.rstrip("/") + "/"
    origin = f"{urlparse(src.url).scheme}://{urlparse(src.url).netloc}/"
    for suffix in FEED_SUFFIXES[:6]:
        for root in (base, origin):
            cand = root + suffix
            if cand in r.feeds:
                continue
            try:
                fr = _get(cand, ua, timeout=12)
                if fr.status_code == 200 and _looks_like_feed(fr):
                    r.feeds.append(cand)
            except Exception:  # noqa: BLE001
                pass
        if len(r.feeds) >= 3:
            break

    # signals for JS-rendering
    r.jsonld_events = len(re.findall(r'"@type"\s*:\s*"Event"', resp.text))
    for n in tree.css("script, style, noscript, nav, footer, header"):
        n.decompose()
    text = tree.body.text(separator=" ") if tree.body else ""
    text = re.sub(r"\s+", " ", text)
    r.text_chars = len(text)
    r.date_mentions = len(DATE_RE.findall(text))
    r.js_suspected = (r.date_mentions < 3 and r.jsonld_events == 0) or r.text_chars < 1500

    if r.feeds:
        r.recommendation = f"use feed: {r.feeds[0]}"
    elif r.js_suspected:
        r.recommendation = "few dates in raw HTML — likely needs js:true (Playwright) or an API endpoint"
    else:
        r.recommendation = f"html ok ({r.date_mentions} dates, {r.jsonld_events} JSON-LD events)"
    return r


def probe_all(sources: list[Source] | None = None) -> list[ProbeResult]:
    cfg = load_config()
    srcs = sources or load_sources(only_enabled=False)
    return [probe_source(s, cfg["user_agent"]) for s in srcs]


def render_markdown(results: list[ProbeResult]) -> str:
    lines = [
        "| Source | Type | HTTP | Feeds found | Dates | JSON-LD | JS? | Recommendation |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        feeds = "<br>".join(r.feeds[:2]) if r.feeds else "-"
        lines.append(
            f"| {r.name} | {r.declared_type} | {r.http_status or r.error[:40]} | {feeds} | "
            f"{r.date_mentions} | {r.jsonld_events} | {'yes' if r.js_suspected else 'no'} | {r.recommendation} |"
        )
    return "\n".join(lines)
