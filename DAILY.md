# Daily run — instructions for the scheduled Claude Code session

You are the extraction and classification step of dc-tech-events. There is no API key; you do the
reading yourself. Work inside this repo. Be economical: skip anything already in the database.

## Steps

1. `uv run dte fetch`
   Feeds (ICS/RSS) go straight into the database. Every HTML source is saved as plain text under
   `inbox/pages/<source>.txt` with a header line giving its URL and tags. The health table at the end
   tells you which sources failed; note them for the summary but do not try to fix websites.

2. Read each file in `inbox/pages/`. For every **upcoming** event you find (today or later), write one
   entry into `inbox/YYYY-MM-DD.json` (today's date) using this shape:

   ```json
   {"source": "daily page scan", "tags": [], "events": [
     {"title": "...", "start": "2026-09-18 14:00", "end": "2026-09-18 15:30", "location": "venue / address or null",
      "virtual": false, "url": "https://...", "host": "CSIS", "description": "<= 40 words",
      "speakers": ["..."], "topics": ["AI", "China"], "fit": 4, "why": "one sentence for a SAIS ETI student",
      "tags": ["think-tank"]}
   ]}
   ```
   - `topics` must come from: AI, semiconductors, cyber, biotech, space, quantum, energy-tech, data/privacy,
     tech-geopolitics, China, Japan-Korea, EU, industrial-policy, trust-and-safety.
   - `fit` is 1–5: 5 = squarely on ETI's mission and easy to attend from SAIS; 1 = not for them.
     Events with fit >= 3 are auto-approved for the map; lower ones are stored but hidden.
   - Skip events that are clearly not about technology *and* policy/security/economics.
   - Use the page header's tags (e.g. `think-tank`, `university`) as each event's `tags`.
   - Times are US Eastern. If only a date is known, use `"2026-09-18"`.

3. `uv run dte import inbox/YYYY-MM-DD.json`. Do this **before** reading any backup, so the primary
   trawl is scored fairly.

4. **Backup check, last.** Read Caleb Knapp's newest post at https://calebknapp.substack.com/feed (the
   "Congressional Hearings", "Public Events" and "Think Tank Events" sections). Write *every* relevant
   event in it, including ones we already have, to `inbox/backup_YYYY-MM-DD.json` with
   `"source": "Caleb Knapp substack", "backup": true, "tags": ["substack"]` (plus `hill` for hearings
   and `public` for meetups per event). `uv run dte import` that file. Then `uv run dte gaps` and follow
   step 3 of TRAWL.md for each miss: change the trawl, then `dte gaps resolve`. Finally `uv run dte digest`
   to rebuild `digest/` and the two map pages.

5. `git add -A && git commit -m "daily: YYYY-MM-DD" && git push origin main`. The push is what
   updates the public site at https://andrewcknox.github.io/dc-tech-events/ (GitHub Pages serves
   the `docs/` folder). Before running git, clear any proxy variables: `unset HTTP_PROXY HTTPS_PROXY`.

6. Report in four lines: how many new events, the catch-rate line from `dte gaps` plus what you changed
   for each miss, which sources failed, anything odd (a venue that could
   not be pinned, a page that changed shape). If a venue is unknown, add it to `venues.yaml`.

## Weekly trawl (Mondays)

On Mondays, after steps 1–4, also work through tiers 2–3 of `TRAWL.md` (browser-only sites and Luma
meetups) in Claude in Chrome, adding events to the same JSON before `dte import`.

## Personalised newsletters (weekly, Mondays, after the SAIS-internal step and `dte digest`)

Only if `newsletter.address` is set in config.yaml and the ETI mailbox is open in classic Outlook here.
1. `uv run dte newsletter sync --send`: answers new subscribe / unsubscribe emails in the ETI inbox.
2. `uv run dte newsletter send --send`: one email per subscriber, sent on behalf of the ETI address.
Without `--send` both commands only write previews to `private/outbox/`. Subscriber data lives in
`private/subscribers.json`, which is gitignored and must never be committed (the repo is public).
Report: how many requests were handled and how many emails went out.

## SAIS-internal events (weekly, Mondays)

First check SAIS CampusGroups in Chrome (TRAWL.md tier 2) and import those events as a primary source,
in `inbox/campusgroups_YYYY-MM-DD.json` with `"backup": false, "tags": ["sais-internal", "sais"]`.
Then, as the backup, search the JHU mailbox for messages from `sais.ti@lists.jh.edu` and other
SAIS lists since the last run. Put *every* event from the mail, including ones already found, in
`inbox/sais_internal_YYYY-MM-DD.json` with `"backup": true, "tags": ["sais-internal", "sais"]` at the
top level, import it, and handle misses with `dte gaps` as above. They appear on `docs/sais-internal.html`, and
also on the public map only if an external source lists them too.
