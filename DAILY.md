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

3. Also check Caleb Knapp's newest post at https://calebknapp.substack.com/feed (the "Congressional
   Hearings", "Public Events" and "Think Tank Events" sections). Add anything new to the same JSON with
   tag `substack`, plus `hill` for hearings and `public` for meetups.

4. `uv run dte import inbox/YYYY-MM-DD.json` — this dedupes against everything already stored, so
   over-including is harmless. Then `uv run dte digest` to rebuild `digest/` and the two map pages.

5. `git add -A && git commit -m "daily: YYYY-MM-DD" && git push origin main`. The push is what
   updates the public site at https://andrewcknox.github.io/dc-tech-events/ (GitHub Pages serves
   the `docs/` folder). Before running git, clear any proxy variables: `unset HTTP_PROXY HTTPS_PROXY`.

6. Report in three lines: how many new events, which sources failed, anything odd (a venue that could
   not be pinned, a page that changed shape). If a venue is unknown, add it to `venues.yaml`.

## SAIS-internal events (weekly, Mondays)

If mail access is available, search the JHU mailbox for messages from `sais.ti@lists.jh.edu` and other
SAIS lists since the last run. Put those events in `inbox/sais_internal_YYYY-MM-DD.json` with
`"tags": ["sais-internal", "sais"]` at the top level. They appear on `docs/sais-internal.html`, and
also on the public map only if an external source lists them too.
