# dc-tech-events

A small robot that watches the events pages of DC think tanks, SAIS and nearby universities,
picks out the ones about **emerging technology and policy**, and publishes a **weekly digest** and
an **interactive map of Washington with the events pinned on it** (filter by date range, time of
day, topic). A second map shows **SAIS-internal** events from the T&I mailing list.

Built for student fellows at the SAIS Emerging Technologies Initiative. There is **no API key and no
per-token cost**: a scheduled Claude Code session on your own machine does the reading each morning.
You do not need to be an engineer to keep it running: the files you will touch are `sources.yaml`
(where to look), `venues.yaml` (where things are) and, optionally, `review/pending_*.md`.

## How it works (5 lines)

```
sources.yaml ──▶ dte fetch ──▶ feeds → events.db ;  web pages → inbox/pages/*.txt
                                                          │
   scheduled Claude session reads inbox/pages + Caleb Knapp's Substack ──▶ inbox/YYYY-MM-DD.json
                                                          │
   dte import (dedupe, tag, pin on map via venues.yaml) ──▶ dte digest ──▶ digest/YYYY-WW.md
                                                                          docs/index.html (public map)
                                                                          docs/sais-internal.html
```

Two scheduled tasks in the Claude desktop app drive this: **daily at 07:00** (fetch, read, import,
rebuild) and **Mondays 07:30** (scan the JHU Outlook mailbox for SAIS-internal events). The exact
instructions the session follows are in `DAILY.md`. Tasks run while the desktop app is open; if it
was closed, they run at next launch.

## The map

`docs/index.html` is a single static page: a Leaflet map of DC on the right, the event list on the
left. Controls: quick ranges (this week, next 14 / 30 days, past 90 days, everything) or any
from/to dates; morning / afternoon / evening / time-TBD; topic chips; a toggle for virtual-only
events and one for Hill hearings. Numbered pins match the list. Past events are greyed. Virtual-only
events show a `~` and no pin. Grey pins are outside the DC area (a Belfer Center event in Cambridge).

`docs/sais-internal.html` is the same page restricted to events tagged `sais-internal` (from the
SAIS T&I mailing list). An event listed both internally and publicly appears on both maps.

Open either file directly in a browser, or serve `docs/` with GitHub Pages.

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

## Tags

Every event carries tags: the source's tags from `sources.yaml`, plus `substack`, `hill`, `public`,
`think-tank`, `sais-internal`, `sais`, `eti`. Tags decide which map an event lands on.

## The review step (optional)

By default the Claude session's `fit` score decides: 3 or above is on the map, below is stored but
hidden. If you want a human gate instead, `uv run dte review` writes a file like
`review/pending_2026-09-14.md`:

| id | approve | date | title | host | fit | why | note |
|---|---|---|---|---|---|---|---|
| 41 |  | 2026-09-18 14:00 | [AI Export Controls…](https://…) | CSIS | 5 | Directly on ETI's China/semiconductor agenda. (AI, China) |  |

Type `y` or `n` in the **approve** column (anything in **note** is kept with the event), save, commit,
push. Nothing reaches the digest or map until it has a `y`. Events you leave blank show up again next time.

Lazy mode, off by default: `uv run dte review --auto-approve-score 5` approves anything Claude rated 5/5.

## Running it by hand

```bash
# once
pip install uv                       # then make sure uv is on PATH
uv sync

# the loop (the scheduled task does exactly this)
uv run dte fetch                     # feeds into the DB; web pages saved to inbox/pages/
#   ...a Claude Code session reads inbox/pages and writes inbox/YYYY-MM-DD.json (see DAILY.md)
uv run dte import inbox/2026-09-14.json
uv run dte digest                    # digest/YYYY-WW.md + docs/index.html + docs/sais-internal.html
```

Anyone can also hand-write an `inbox/*.json` file (the format is in `DAILY.md`) and import it.
`inbox/substack_backlog.json` is the three-month backlog from Caleb Knapp's Weekly AI Digest.

If you ever do want the Anthropic API to do the extraction unattended (for example on GitHub
Actions), set `extraction: api` in `config.yaml` and provide `ANTHROPIC_API_KEY`; the old path is
still there.

Extras: `uv run dte fetch -s CSIS -s CNAS` (only some sources), `uv run dte stats`,
`uv run pytest` (tests never touch the network). For `js: true` sources install Playwright once:
`uv sync --extra js && uv run playwright install chromium`.

## Publishing the map

Push the repo to GitHub and, in **Settings → Pages**, publish the `docs/` folder. The scheduled task
commits after each run; add a `git push` to `DAILY.md` step 5 once a remote exists. The workflows in
`.github/workflows/` are optional: `digest.yml` redeploys Pages, and `fetch.yml` is the API-mode
alternative that needs an `ANTHROPIC_API_KEY` secret. Set `DIGEST_WEBHOOK_URL` to have the weekly
digest posted to Slack or Discord.

## Cost and safety valves

- No API spend. The reading happens inside your Claude desktop session.
- Re-running `fetch` or `import` never creates duplicates. Cross-listed events (same talk on two sites) are merged;
  the extra links are kept.
- Every source's outcome is logged. A source that fails three runs in a row is called out in the
  digest footer and at the top of the map so someone fixes the URL.

## Layout

```
sources.yaml   venues.yaml   config.yaml      ← the files humans edit
DAILY.md                                      ← what the scheduled Claude session does
inbox/pages/   inbox/*.json                   ← saved page text; events written by the session
src/dte/       the pipeline (fetch, importer, dedupe, geocode, review, digest, map_template.html)
scripts/probe_sources.py                      ← same as `dte probe`
data/events.db                                ← the database
review/  digest/  docs/                       ← outputs (docs/ is the map site)
tests/                                        ← offline tests with saved sample pages
```
