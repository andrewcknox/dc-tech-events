# dc-tech-events

A small robot that watches the events pages of DC think tanks, SAIS and nearby universities,
picks out the ones about **emerging technology and policy**, asks a human to approve them, and
then publishes a **weekly digest** and a **map of Washington with the events pinned on it**.

Built for student fellows at the SAIS Emerging Technologies Initiative. You do not need to be an
engineer to keep it running: the two files you will ever touch are `sources.yaml` (where to look)
and `review/pending_*.md` (what to approve).

## How it works (5 lines)

```
sources.yaml ──▶ fetch (feeds, or web page → Claude) ──▶ events.db (SQLite)
                                                         │
                       dedupe ──▶ classify (Claude) ──▶ pin on map (venues.yaml / OpenStreetMap)
                                                         │
     review/pending_*.md ◀── you type y / n ──▶ digest/YYYY-WW.md  +  docs/index.html (the map)
```

Every morning GitHub Actions runs the top row. Every Monday (and whenever you commit an approval)
it runs the bottom row and republishes the map to GitHub Pages.

## The map

`docs/index.html` is a single static page: a Leaflet map of DC on the right, the upcoming 14 days
on the left. Numbered pins match the numbered list. Click a topic chip (AI, China, semiconductors…)
to filter. Virtual-only events appear in the list with a `~` and no pin. Grey pins are outside the
DC area (e.g. a JHU event in Baltimore).

## Adding or fixing a source

Open `sources.yaml` and copy one of the blocks:

```yaml
  - name: Brookings
    url: https://www.brookings.edu/events/
    type: html        # ics | rss | html | eventbrite_org
    js: false         # true only if the page is blank without JavaScript
    tags: [think-tank]
    enabled: true
```

Then check it:

```bash
uv run dte probe
```

That prints a table saying whether the URL loads, whether a machine-readable feed (RSS/ICS) exists,
and whether the page needs JavaScript. Prefer a feed if one exists (cheaper and more reliable);
otherwise `html` is fine, Claude reads the page. If the probe says "needs JS", set `js: true`.

If a pin lands in the wrong place, add the venue to `venues.yaml` with its coordinates
(right-click in Google Maps to copy them). Venues in that file are checked before the online geocoder.

## The review step

`uv run dte review` (also run daily by the bot) writes a file like `review/pending_2026-09-14.md`:

| id | approve | date | title | host | fit | why | note |
|---|---|---|---|---|---|---|---|
| 41 |  | 2026-09-18 14:00 | [AI Export Controls…](https://…) | CSIS | 5 | Directly on ETI's China/semiconductor agenda. (AI, China) |  |

Type `y` or `n` in the **approve** column (anything in **note** is kept with the event), save, commit,
push. Nothing reaches the digest or map until it has a `y`. Events you leave blank show up again next time.

Lazy mode, off by default: `uv run dte review --auto-approve-score 5` approves anything Claude rated 5/5.

## Running it on your laptop

```bash
# once
pip install uv                       # or brew install uv
uv sync
export ANTHROPIC_API_KEY=sk-ant-...  # PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."

# the loop
uv run dte fetch          # pull sources, classify, geocode; prints a health table + cost
uv run dte review         # writes review/pending_YYYY-MM-DD.md — edit it
uv run dte digest         # writes digest/YYYY-WW.md and docs/index.html (open it in a browser)
```

Extras: `uv run dte fetch -s CSIS -s CNAS` (only some sources), `uv run dte stats`,
`uv run pytest` (tests never touch the network). For `js: true` sources install Playwright once:
`uv sync --extra js && uv run playwright install chromium`.

## Running it on GitHub

1. Push this repo. In **Settings → Secrets** add `ANTHROPIC_API_KEY`. Optionally add
   `DIGEST_WEBHOOK_URL` (a Slack or Discord incoming-webhook URL) to get the digest posted.
2. In **Settings → Pages** set the source to **GitHub Actions**.
3. Workflows: `fetch.yml` runs daily at 07:00 Eastern; `digest.yml` runs Monday 08:00 Eastern and
   whenever a file under `review/` is pushed. The SQLite database is committed to the repo so nothing
   is lost between runs.

## Cost and safety valves

- Claude (Haiku, set in `config.yaml` → `model`) is only called for HTML pages and once per new event
  for classification. Pages that have not changed are cached by content hash and cost nothing.
  `dte fetch` prints the token count and an estimated dollar figure each run; a normal day is a few cents.
- Re-running `fetch` never creates duplicates. Cross-listed events (same talk on two sites) are merged;
  the extra links are kept.
- Every source's outcome is logged. A source that fails three runs in a row is called out in the
  digest footer and at the top of the map so someone fixes the URL.

## Layout

```
sources.yaml   venues.yaml   config.yaml      ← the files humans edit
src/dte/       the pipeline (fetch, dedupe, classify, geocode, review, digest, map_template.html)
scripts/probe_sources.py                      ← same as `dte probe`
data/events.db                                ← the database
review/  digest/  docs/                       ← outputs
tests/                                        ← offline tests with saved sample pages
```
