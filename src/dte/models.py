"""Event schema (used for Claude structured output) + normalization helpers."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil import parser as dtparser
from pydantic import BaseModel, Field

TZ_NAME = "America/New_York"
TZ = ZoneInfo(TZ_NAME)


class ExtractedEvent(BaseModel):
    """One event as returned by Claude from a web page."""

    title: str
    start_datetime: str = Field(description="ISO 8601 start, America/New_York. Use T00:00 if only the date is known.")
    end_datetime: str | None = None
    location: str | None = Field(default=None, description="Venue name and/or address; null if unknown or virtual-only.")
    virtual: bool = False
    url: str = Field(description="Absolute URL of the event page.")
    host_org: str
    description_short: str = Field(description="At most 40 words.")
    speakers: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    events: list[ExtractedEvent]


TOPICS = [
    "AI", "semiconductors", "cyber", "biotech", "space", "quantum", "energy-tech",
    "data/privacy", "tech-geopolitics", "China", "Japan-Korea", "EU", "industrial-policy",
    "trust-and-safety",
]


class Classification(BaseModel):
    relevant: bool = Field(description="True if the event is about emerging technology AND policy/geopolitics/security.")
    topics: list[str] = Field(default_factory=list, description=f"Subset of: {', '.join(TOPICS)}")
    audience_fit_for_sais_students: int = Field(ge=1, le=5, description="1=irrelevant, 5=must-attend for a SAIS tech-policy fellow")
    one_line_why: str = Field(description="One sentence: why (or why not) a SAIS ETI student should care.")


# ---------- normalization ----------

_PUNCT = re.compile(r"[^\w\s]", re.U)
_WS = re.compile(r"\s+")
_STOP = {"the", "a", "an", "and", "of", "for", "in", "on", "with", "to", "at", "&"}


def normalize_title(title: str) -> str:
    t = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode()
    t = _PUNCT.sub(" ", t.lower())
    words = [w for w in _WS.split(t) if w and w not in _STOP]
    return " ".join(words)


def parse_datetime(value: str | datetime | date | None, default_tz: ZoneInfo = TZ) -> datetime | None:
    """Parse many date shapes into an aware datetime in America/New_York. None if hopeless."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        s = str(value).strip()
        try:
            dt = dtparser.parse(s)
        except (ValueError, OverflowError, TypeError):
            try:
                dt = dtparser.parse(s, fuzzy=True)
            except (ValueError, OverflowError, TypeError):
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_tz)
    return dt.astimezone(default_tz)


def to_iso(dt: datetime | None) -> str | None:
    return dt.replace(microsecond=0).isoformat() if dt else None


def fingerprint(title: str, start: datetime) -> str:
    key = f"{normalize_title(title)}|{start.date().isoformat()}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:24]


def is_past(dt: datetime, now: datetime | None = None, grace_hours: int = 0) -> bool:
    now = now or datetime.now(TZ)
    return dt < now - timedelta(hours=grace_hours)
