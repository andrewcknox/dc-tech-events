"""Thin wrapper around the Anthropic SDK: structured extraction + classification, with token accounting."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from .config import load_config
from .models import TOPICS, Classification, ExtractionResult

T = TypeVar("T", bound=BaseModel)

# Haiku 4.5 list price, USD per 1M tokens. Only used for the printed estimate.
PRICE_IN, PRICE_OUT = 1.00, 5.00


@dataclass
class Spend:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    cache_hits: int = 0
    notes: list[str] = field(default_factory=list)

    def add(self, usage) -> None:  # noqa: ANN001
        self.calls += 1
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0

    @property
    def usd(self) -> float:
        return self.input_tokens / 1e6 * PRICE_IN + self.output_tokens / 1e6 * PRICE_OUT

    def summary(self) -> str:
        return (
            f"Claude calls: {self.calls} (cache hits skipped: {self.cache_hits}) | "
            f"tokens in/out: {self.input_tokens:,}/{self.output_tokens:,} | est. ${self.usd:.3f}"
        )


SPEND = Spend()

EXTRACT_SYSTEM = """You extract upcoming public events from the text of a web page.
Return every distinct event that has at least a title and a date. Rules:
- start_datetime must be ISO 8601 in the America/New_York time zone (e.g. 2026-09-18T14:00:00-04:00).
  If only a date is known, use 00:00:00. If the year is missing, assume the next occurrence on or after today.
- Ignore events whose date is clearly in the past relative to today.
- url must be absolute; resolve relative links against the page URL given.
- host_org is the organisation running the event (usually the site owner).
- virtual=true if the event is online-only or hybrid; location is the physical venue/address if any.
- description_short is at most 40 words. speakers lists names only, no titles.
- Do not invent events, dates or URLs. If the page has no events, return an empty list."""

CLASSIFY_SYSTEM = f"""You screen events for graduate students at the Johns Hopkins SAIS Emerging Technologies Initiative
(international relations students focused on how emerging technology shapes policy, security and geopolitics).
Mark relevant=true only if the event substantively concerns emerging technology AND policy/security/geopolitics/economics.
Pure product launches, purely technical tutorials, and unrelated policy topics (e.g. tax reform, migration) are not relevant.
topics must be a subset of exactly these labels: {", ".join(TOPICS)}.
audience_fit_for_sais_students: 5 = squarely on-mission and in DC / accessible; 3 = tangential or niche; 1 = not for them.
one_line_why: a single plain-English sentence a student could read in the digest."""


def client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _parse(model: str, system: str, user: str, schema: type[T], max_tokens: int) -> tuple[T, object]:
    resp = client().messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=schema,
    )
    SPEND.add(resp.usage)
    if resp.parsed_output is None:  # refusal or malformed — never crash the pipeline
        return schema.model_validate({} if schema is not ExtractionResult else {"events": []}), resp.usage
    return resp.parsed_output, resp.usage


def extract_events(page_text: str, page_url: str, source_name: str, today: datetime, model: str | None = None) -> tuple[ExtractionResult, object]:
    cfg = load_config()
    user = (
        f"Today is {today.strftime('%A %Y-%m-%d')}.\nPage URL: {page_url}\nSource: {source_name}\n\n"
        f"<page_text>\n{page_text}\n</page_text>"
    )
    return _parse(model or cfg["model"], EXTRACT_SYSTEM, user, ExtractionResult, max_tokens=8000)


def classify_event(ev: dict, model: str | None = None) -> tuple[Classification, str]:
    cfg = load_config()
    payload = {k: ev.get(k) for k in ("title", "host_org", "start_dt", "location", "virtual", "description_short", "speakers", "url")}
    user = "Classify this event:\n" + json.dumps(payload, ensure_ascii=False, indent=1)
    try:
        c, _ = _parse(model or cfg["model"], CLASSIFY_SYSTEM, user, Classification, max_tokens=600)
    except Exception:  # noqa: BLE001 — model_validate({}) would fail on required fields; build a safe default
        c = Classification(relevant=False, topics=[], audience_fit_for_sais_students=1, one_line_why="classification failed")
    c.topics = [t for t in c.topics if t in TOPICS]
    return c, c.model_dump_json()
