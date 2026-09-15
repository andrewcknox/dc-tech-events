# PLAN — dc-tech-events

**Goal.** Track emerging-tech policy events in Washington DC (think tanks, SAIS, Hopkins),
dedupe and classify them, let a human approve, then publish a weekly digest **and a map of DC
with the upcoming events pinned on it**. Built for SAIS ETI student fellows; the source list and
venue list are plain YAML files a non-engineer can edit.

## Architecture (5 lines)

```
sources.yaml ──▶ fetch (ICS / RSS / HTML→Claude) ──▶ SQLite events.db
                                                      │
                     dedupe ──▶ classify (Claude) ──▶ geocode (venues.yaml + Nominatim)
                                                      │
        review/pending_*.md  ◀── human approves ──▶ digest/YYYY-WW.md + docs/ (map + list)
```

## CLI (`uv run dte ...`)

| Command | What it does |
|---|---|
| `dte fetch` | Pull every enabled source, extract events, dedupe, classify new ones, geocode. Prints health + token spend. |
| `dte review` | Write `review/pending_YYYY-MM-DD.md` with new relevant events and an `approve` column. `--auto-approve-score N` optional. |
| `dte apply-review` | Read back edited pending files and mark approvals in the DB (run automatically by `digest`). |
| `dte digest` | Build `digest/YYYY-WW.md`, `docs/events.json`, `docs/index.html` (Leaflet map + list). Posts to `DIGEST_WEBHOOK_URL` if set. |
| `dte probe` | Same as `scripts/probe_sources.py`: check each source URL for feeds / JS. |

## SQLite schema (`data/events.db`)

```sql
events(
  id INTEGER PK, fingerprint TEXT UNIQUE,      -- normalized title + date
  title, start_dt, end_dt, location, virtual INT, url, alt_urls TEXT(JSON),
  host_org, description_short, speakers TEXT(JSON),
  source_name, first_seen, last_seen,
  lat REAL, lon REAL, geocode_status TEXT,
  relevant INT, topics TEXT(JSON), fit_score INT, one_line_why, classify_raw TEXT,
  approved TEXT ('', 'y', 'n'), review_note TEXT
)
sources_status(id, source_name, run_at, status ('ok'|'failed'|'empty'), n_events, message)
extraction_cache(content_hash TEXT PK, source_name, extracted_json, input_tokens, output_tokens, created_at)
geocode_cache(query TEXT PK, lat, lon, display_name, created_at)
```

## Config

- `config.yaml`: model name (default `claude-haiku-4-5`), time zone, thresholds, map centre.
- `sources.yaml`: name, url, type (`ics|rss|html|eventbrite_org`), js, tags, enabled.
- `venues.yaml`: host org / venue name → address + lat/lon. First geocoding stop; Nominatim is the fallback.

## Build order

sources.yaml + probe → fetch (feeds, then HTML extraction) → dedupe → classify → geocode →
review → digest + map → GH Actions → tests → README.

## Revision 2026-09-14: no API key

Extraction and classification are done by a scheduled Claude Code session on the user's machine
(see `DAILY.md`), not by the Anthropic API. `dte fetch` dumps HTML pages to `inbox/pages/`; the
session writes `inbox/*.json`; `dte import` loads it. Events carry `tags`; `sais-internal` events
get their own map page. The map has date-range and time-of-day filters and a 90-day backlog.
