"""Turn an event's location / host into map coordinates.

Order: venues.yaml keyword match -> geocode_cache -> Nominatim (OpenStreetMap, 1 req/s, polite UA).
Virtual-only events get geocode_status='virtual' and no pin.
"""
from __future__ import annotations

import re
import time
from typing import Any

import requests

from . import db
from .config import load_config, load_venues

NOMINATIM = "https://nominatim.openstreetmap.org/search"
_last_call = 0.0

# Rough bounding box: DC metro. Anything outside is kept but flagged so the map can grey it out.
DC_BOX = (38.70, -77.35, 39.10, -76.80)  # min_lat, min_lon, max_lat, max_lon


def _match_venue(text: str, venues: list[dict[str, Any]]) -> dict[str, Any] | None:
    t = f" {text.lower()} "
    for v in venues:
        for kw in v.get("match", []):
            kw = str(kw).lower()
            if kw in t:
                return v
    return None


def _nominatim(query: str, ua: str) -> tuple[float, float, str] | None:
    global _last_call
    wait = 1.1 - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()
    try:
        resp = requests.get(
            NOMINATIM,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": ua},
            timeout=15,
        )
        resp.raise_for_status()
        hits = resp.json()
    except Exception:  # noqa: BLE001
        return None
    if not hits:
        return None
    h = hits[0]
    return float(h["lat"]), float(h["lon"]), h.get("display_name", "")


def _clean_location(loc: str) -> str:
    loc = re.sub(r"\b(room|suite|floor|fl\.?|ste\.?)\s*[\w-]+", " ", loc, flags=re.I)
    loc = re.sub(r"\s+", " ", loc).strip(" ,")
    return loc


def geocode_event(con, ev: dict[str, Any], venues: list[dict[str, Any]], cfg: dict[str, Any]) -> tuple[float | None, float | None, str]:
    """Return (lat, lon, status). status in: venue | cache | nominatim | virtual | none."""
    loc = (ev.get("location") or "").strip()
    host = (ev.get("host_org") or "").strip()
    src = (ev.get("source_name") or "").strip()

    if not loc and ev.get("virtual"):
        return None, None, "virtual"

    v = _match_venue(loc, venues) or (_match_venue(host, venues) if not _looks_like_address(loc) else None) or _match_venue(src, venues)
    if v and (loc or host):
        return float(v["lat"]), float(v["lon"]), "venue"

    if not loc:
        # no address, no venue match; a source-level fallback is better than nothing for the map
        v = _match_venue(host, venues) or _match_venue(src, venues)
        if v:
            return float(v["lat"]), float(v["lon"]), "venue"
        return None, None, "virtual" if ev.get("virtual") else "none"

    q = _clean_location(loc)
    if re.fullmatch(r"(washington|washington,? d\.?c\.?|dc|in[- ]person|tbd|tba)[\s,.]*", q, re.I) or "(" in q and "venue" in q.lower():
        v = _match_venue(host, venues) or _match_venue(src, venues)
        return (float(v["lat"]), float(v["lon"]), "venue") if v else (None, None, "none")
    if "washington" not in q.lower() and "dc" not in q.lower() and not re.search(r"\b(va|md|virginia|maryland)\b", q, re.I):
        q = f"{q}, Washington, DC"
    cached = db.geocache_get(con, q)
    if cached:
        return cached["lat"], cached["lon"], "cache" if cached["lat"] is not None else "none"
    hit = _nominatim(q, cfg["user_agent"])
    if hit:
        db.geocache_put(con, q, hit[0], hit[1], hit[2])
        return hit[0], hit[1], "nominatim"
    db.geocache_put(con, q, None, None, "")
    # last resort: host org venue
    v = _match_venue(host, venues) or _match_venue(src, venues)
    if v:
        return float(v["lat"]), float(v["lon"]), "venue"
    return None, None, "none"


def _looks_like_address(loc: str) -> bool:
    return bool(re.search(r"\d{2,5}\s+\w+.*\b(st|street|ave|avenue|blvd|rd|road|nw|ne|sw|se)\b", loc, re.I))


def in_dc_area(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    return DC_BOX[0] <= lat <= DC_BOX[2] and DC_BOX[1] <= lon <= DC_BOX[3]


def geocode_pending(con, after_iso: str) -> int:
    cfg = load_config()
    venues = load_venues()
    n = 0
    for ev in db.ungeocoded_events(con, after_iso):
        lat, lon, status = geocode_event(con, ev, venues, cfg)
        db.update_event(con, ev["id"], lat=lat, lon=lon, geocode_status=status)
        n += 1
    con.commit()
    return n
