"""Load config.yaml, sources.yaml and venues.yaml from the project root."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def project_root() -> Path:
    """Project root = directory containing sources.yaml (env DTE_ROOT overrides)."""
    env = os.environ.get("DTE_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for p in [Path.cwd(), *here.parents]:
        if (p / "sources.yaml").exists():
            return p
    return Path.cwd()


ROOT = project_root()

DEFAULTS: dict[str, Any] = {
    "model": "claude-haiku-4-5",
    "timezone": "America/New_York",
    "max_chunk_chars": 24000,
    "dedupe_threshold": 85,
    "dedupe_window_days": 1,
    "digest_days_ahead": 14,
    "min_fit_for_review": 1,
    "failure_flag_threshold": 3,
    "map_center": [38.905, -77.036],
    "map_zoom": 13,
    "user_agent": "dc-tech-events/0.1",
    "extraction": "session",
    "site_days_back": 90,
    "site_days_ahead": 90,
}


def load_config() -> dict[str, Any]:
    cfg = dict(DEFAULTS)
    p = ROOT / "config.yaml"
    if p.exists():
        cfg.update(yaml.safe_load(p.read_text(encoding="utf-8")) or {})
    if os.environ.get("DTE_MODEL"):
        cfg["model"] = os.environ["DTE_MODEL"]
    return cfg


@dataclass
class Source:
    name: str
    url: str
    type: str = "html"
    js: bool = False
    tags: list[str] = field(default_factory=list)
    enabled: bool = True

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Source":
        return cls(
            name=str(d["name"]),
            url=str(d["url"]),
            type=str(d.get("type", "html")).lower(),
            js=bool(d.get("js", False)),
            tags=list(d.get("tags") or []),
            enabled=bool(d.get("enabled", True)),
        )


def load_sources(path: Path | None = None, only_enabled: bool = True) -> list[Source]:
    p = path or ROOT / "sources.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    srcs = [Source.from_dict(d) for d in data.get("sources", [])]
    return [s for s in srcs if s.enabled] if only_enabled else srcs


def load_venues() -> list[dict[str, Any]]:
    p = ROOT / "venues.yaml"
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return list(data.get("venues", []))


def db_path() -> Path:
    return Path(os.environ.get("DTE_DB", ROOT / "data" / "events.db"))
