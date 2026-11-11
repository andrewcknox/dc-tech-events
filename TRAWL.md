# The trawl — which pages we hit, and how we keep it ahead of the backups

**Goal: we find every event before Caleb Knapp's substack or the SAIS mailing lists do.** Those two are
*backups*. Every event a backup reports that we did not already have is a **miss**, and every miss
must end with a change to this trawl, so the same kind of event is caught next time.

## Run order (every run)

1. **Primary trawl first**: tiers 1–3 below, then `dte import inbox/YYYY-MM-DD.json`.
2. **Backups last, in their own file**: read Knapp's newest post and the SAIS mail and write
   `inbox/backup_YYYY-MM-DD.json` with `"backup": true` at the top level. Never mix backup events into
   the primary file; otherwise misses are counted as our own finds.
   `dte import` then prints `backup check: N already ours, M MISSED`.
3. **Close the loop**: run `uv run dte gaps`. For every open miss:
   - work out why we missed it (the report suggests a cause);
   - change the trawl: add the host to `sources.yaml`, add a page to tier 2/3 below, fix a URL, or
     tighten the extraction guidance in DAILY.md;
   - record the change: `uv run dte gaps resolve <ids> --cause <cause> --fix "what changed"`.
     A fix note is required except for `posted-late`, `not-public` and `out-of-scope`.
   If a miss can't be fixed in this run, leave it open; it stays in every `dte gaps` report until it is.
4. Report the catch rate line from `dte gaps` in the run summary.

Causes: `no-source` (host not trawled) · `page-missed` (trawled, but the event wasn't on the page we
read) · `extraction-missed` (it was in `inbox/pages/` but we skipped it) · `blocked` · `no-run` (our
trawl didn't run in time) · `posted-late` · `not-public` · `out-of-scope`.
If the same host shows up as `posted-late` twice, it isn't late. Check it more often or find a better page.

Tiers 1–3 run on every daily run where possible. Tiers 2–3 need Claude in Chrome, so at minimum they run
on Mondays, covering the next 14 days.

## Tier 1 — scripted (`uv run dte fetch`)

Everything enabled in `sources.yaml` (99 enabled sources: about 75 for DC/Baltimore and 24 for the Bay Area,
which are listed below. The 2026-11-07 additions include SpacePolicyOnline's ICS, Global Taiwan Institute,
AAAS, JHU APL, UMD GPI/CISSM, Scoop News Group, MeriTalk, Punchbowl, INSA, US Chamber, CTA, and in
Baltimore SNF Agora, JHU IAA, GBC and Baltimore Tech Meetup. Also included are Luma iCal feeds for Fathom, IFP, Center for Technology & Statecraft, Squadra Ventures and ACE Health/Millennium Project). Covers: JHU/SAIS, the core think tanks (CSIS, CNAS,
Brookings, CSET, ITIF, Hudson, Carnegie, Atlantic Council, Wilson, Stimson, R Street, SCSP, IST, CDI, FAS,
AEI, FAI, New America, CAP, Hoover, Niskanen, GMF, CFR, Aspen Digital, Third Way, BPC, ASP, KEI,
SPF USA), EPIC, FPF, Alliance for Secure AI, National Academies, House Science, USCC, NIST, JHU DSAI,
GW Elliott and Georgetown SFS. Then read `inbox/pages/` as DAILY.md step 2 describes.

Note the health table: a source that fails three runs in a row is flagged in the digest footer.

## Tier 2 — browser-only (Claude in Chrome, ~10 min)

These sites answer scripts with 403/404, so they are not in `sources.yaml`. Open each in the user's
Chrome, read the upcoming list, and add events to the same `inbox/YYYY-MM-DD.json`. Don't try to make
scripts get past their blocking.

| Org | Page | Why it matters |
|---|---|---|
| **SAIS CampusGroups** (signed in) | https://jhu.campusgroups.com/saisfocusareaevents/events plus the JHU CampusGroups event calendar filtered to SAIS | the source the SAIS mailing lists link to (`cglink.me`); focus-area and club events. Put them in their own file with `"backup": false, "tags": ["sais-internal", "sais"]` (the explicit false matters: that tag otherwise marks a backup). If Chrome is signed out (JHU SSO now asks for a Windows Hello/security-key MFA prompt that an unattended run can't pass), the signed-out list still works: on the events page run `fetch('/mobile_ws/v17/mobile_events_list?range=0&limit=600&filter4_contains=OR&filter4_notcontains=OR&order=undefined&search_word=&&1')` (then range=600) and filter `clubName` for SAIS. This omits **private** events (e.g. Merrill Center Defense Industry Speaker Series), which only the mailing lists then catch. Event detail pages render signed out at `rsvp_boot?id=N` |
| Heritage Foundation | https://www.heritage.org/events | China/tech, conservative AI policy |
| Cato Institute | https://www.cato.org/events (403 in the in-app browser on 2026-11-09; loads in the user's Chrome, checked 2026-11-10) | tech regulation, surveillance, trade |
| FDD | https://www.fdd.org/events/ | cyber, China tech, sanctions |
| Mercatus Center | https://www.mercatus.org/events | AI governance, innovation policy |
| Aspen Institute (DC) | https://www.aspeninstitute.org/events/ | security forum spin-offs |
| RAND (DC office) | https://www.rand.org/events.html | AI, national security |
| Lawfare | https://www.lawfaremedia.org/events (404 on 2026-11-09; find the new events page) | cyber/national-security law |
| CDT | https://cdt.org/events/ | AI rights, privacy |
| US-China Business Council | https://www.uschina.org/events | export controls, China market |
| BSA / The Software Alliance | https://www.bsa.org/events | AI and data policy, industry view |
| CEPA | https://cepa.org/events/ | transatlantic tech/cyber; page needs a human check |
| House committees | https://docs.house.gov/Committee/Calendar/ByWeek.aspx (all House hearings this week) | E&C, Science, Homeland, Foreign Affairs, Armed Services |
| Senate committees | https://www.congress.gov/committee-schedule (week view; filter Commerce, Judiciary, HSGAC, Banking, Foreign Relations, Armed Services) | hearings on AI, chips, export controls |
| House China Select Committee | https://chinaselectcommittee.house.gov/committee-activity/hearings/all (old `/hearings` 404 on 2026-11-10; titles appear here and on congress.gov a few days ahead) | China tech hearings |
| FTC / FCC open meetings | https://www.ftc.gov/news-events/events · https://www.fcc.gov/news-events/events | AI enforcement, spectrum, broadband |
| Annual DC tech/cyber conferences | https://www.cyberwarcon.com · https://events.govexec.com (GovExec / Google Public Sector Summit and similar vendor-government summits) · https://www.stateofthenet.org (Feb 9, 2027) · https://billingtoncybersecurity.com (Mar 17–19, 2027, National Harbor) · ITI's The Intersect (February) | one-off yearly events that never appear on a think-tank page; check monthly |
| Media live events | https://www.axios.com/events · https://www.politico.com/live-events · https://www.washingtonpost.com/washington-post-live/ · https://www.semafor.com/events · https://thehillevents.splashthat.com/ · https://events.defenseone.com/ | on-record officials, often in-person in DC |
| Jamestown Foundation | https://jamestown.org/events/ | China/Eurasia; China Brief conferences |
| NBR (DC) | https://www.nbr.org/events/ | Asia tech, supply chains, Indo-Pacific |
| CSBA | https://csbaonline.org/about/events | defense strategy and technology |
| East-West Center in Washington | https://www.eastwestcenter.org/events | Asia-Pacific, US-China |
| NTI | https://www.nti.org/events/ | biosecurity, AI-bio, nuclear |
| Aerospace Corp. Center for Space Policy & Strategy | https://csps.aerospace.org/events | space policy, DC events |
| American University SIS | https://www.american.edu/sis/events/ | tech and security events |
| Library of Congress (Kluge Center) | https://www.loc.gov/events/ | AI/tech talks |
| GMU National Security Institute | https://nationalsecurity.gmu.edu/upcoming-events/ | AI Edge series, FISA, cyber, space (Arlington); listing has no dates, so open each item |

Orgs without a working events page yet (find it once, then move it into tier 1 or 2):
IAPS, Americans for Responsible Innovation, Public Knowledge, NTIA, House Energy & Commerce. (Checked
2026-11-07: IAPS, ARI and Public Knowledge `/events` all 404; catch them via Luma search and the backups.)
(IFP and Fathom are now tier 1 via their Luma iCal feeds.)

## Tier 3 — meetups and community (Luma / Eventbrite)

DC's AI/defense-tech community runs almost entirely on Luma. In Chrome, check:
- Luma discover, Washington DC (https://luma.com/dc; the list is virtualised and event cards have no plain links, so read it with get_page_text after scrolling, then search Luma for any title worth adding) and search "AI", "policy",
  "defense tech", "chips".
- Calendars seen in our data so far: The AI Collective DC, Deep Tech Week, All Tech Is Human (ATIHx DC).
  (BlueDot Impact, cal-4g8MKXGW8nmoHby, a global calendar, and Human Friendly Tech, cal-JhOxDIdiNDtJH2g,
  moved to tier 1 via iCal on 2026-11-11; score BlueDot's non-DC events fit 1.) (STATION DC, Defense Tech DC, DC Industrial Policy Salon and DC Data & AI Events moved to
  tier 1 via iCal on 2026-11-07. The AI Collective and All Tech Is Human share one *global* calendar each,
  so they stay here: look for the DC chapter's events by hand.)
  When you find a calendar's own Luma URL, record it here; if Luma offers an "Add iCal subscription"
  link for it, add that to `sources.yaml` as `type: ics` and move it to tier 1.
- Luma iCal feeds already in tier 1: Fathom (cal-WpSrRMVxhflSAm6), Institute for Progress
  (cal-WzpdUQqj4iM0Yl6), Center for Technology & Statecraft (cal-cvLhoiSidIrXJIi), Squadra Ventures
  (cal-faJsEcJ06uVdslO; co-hosts ETI's Boundary Breakers), ACE Health Foundation & Millennium Project
  (cal-oFEiXyJHfoilbmL). Feed URL pattern: `https://api.lu.ma/ics/get?entity=calendar&id=<cal-id>`; the
  cal id is in the event page HTML (`"calendar":{"api_id":...`).
- Hosts that post from a *personal* Luma calendar (no org feed to subscribe to), so check them by
  searching Luma for the host name: IAPS, DCMC (AI Governance Happy Hour), Inclusive Abundance,
  VALS AI, IST happy hours, and Alperovitch Institute / SAIS ETI talks (e.g. "The Bitter Struggle").
- Hosts that announce events only as Zoom webinars, with no events page: **Americans for Responsible
  Innovation (ARI)**. Checked 2026-11-08: `ari.us/events` is a 404 and `ari.us/feed/` only carries
  press statements. Each tier-3 run, search the web and Luma for "Americans for Responsible Innovation"
  plus webinar/event, and check ari.us news posts for "register" links (they use zoom.us/webinar).
- Tag these events `public`.

## Bay Area (docs/bay-area.html)

A separate list for SF / East Bay / Peninsula / South Bay, plus Sacramento for state tech-policy bodies.
Its events carry the `bay-area` tag, which keeps them off the DC map, digest and newsletters. Times are
shown in Pacific.

- **Tier 1 (scripted):** 24 enabled sources in the BAY AREA block of `sources.yaml`:
  - Stanford: HAI, the FSI umbrella listing plus CISAC, APARC and SCCEI, the Digital Economy Lab and SIEPR.
    (Stanford Law blocks scripts, so it is in tier 2.)
  - Berkeley: BCLT and the Law AI category ICS, IEAS, the Center for Chinese Studies, IIS, IGS, the I School,
    Risk & Security Lab, the campus "artificial intelligence" search ICS, and Simons.
  - Others: Asia Society NorCal, Computer History Museum, SVLG, Internet Archive, the Mox and Frontier Tower
    Luma calendars, and the CPPA board.
  - Two Sacramento committees (Assembly Privacy, Senate Judiciary) are disabled until the January 2027
    session.
- **Tier 2 (Claude in Chrome):**

| Org | Page | Why it matters |
|---|---|---|
| Commonwealth Club World Affairs | https://www.commonwealthclub.org/events | SF's biggest public forum for tech/AI and geopolitics (403 to scripts) |
| Stanford Tech Impact & Policy Center (ex-Cyber Policy Center) | https://cyber.fsi.stanford.edu/events | trust & safety, AI governance (403); usually also on the FSI listing |
| Stanford Law tech centers (CodeX, CIS, LST, privacy) | https://law.stanford.edu/events/ | tech-law talks, e.g. CPPA officials (blocks scripts) |
| EFF | https://www.eff.org/events | digital rights; its ICS is per month (`/calendar/ics/export.ics/YYYY-MM`) |
| Hoover Institution (Stanford) | https://www.hoover.org/events | the DC source already lists these; tag any event at Stanford `bay-area` |

- **Tier 3 (Luma):** luma.com/discover → San Francisco, searching "AI policy", "AI safety" and
  "tech policy". One-off host calendars dominate there: AI Governance After Hours, AI Salon, Bay Area AI
  Safety Meetup. Constellation, Transluce and Foresight have Luma calendars with no public future events,
  so check them in a browser now and then.
- Researched but left out (dead or off-topic on 2026-11-07): CLTC and AI Policy Hub (nothing since
  Dec 2025), Berkeley Center for Security in Politics, Markkula Center (empty), Partnership on AI, CAIS,
  CHAI, TechNet, TechEquity, SPUR, Bay Area Council, Long Now.

## Backups (read last, scored, never the primary source)

- Caleb Knapp's newest post: https://calebknapp.substack.com/feed (Hearings, Public Events, Think Tank
  Events).
- SAIS mailing lists (Monday task `dc-tech-events-sais-mail`).
Both go in `inbox/backup_YYYY-MM-DD.json` with `"backup": true`. Use tag `sais-internal` for SAIS-only
events so they land on the SAIS-internal map.

## Monthly check (5 minutes)

`uv run dte gaps --days 28` for the catch rate; it should rise toward 100%. `uv run dte probe` to see
whether any page now offers a feed (a feed is cheaper and more reliable than a page).

Deliberately left out: Belfer (Cambridge), FPRI (Philadelphia), AFCEA/NDIA/SIA (national trade
conferences, mostly paid and outside DC). Add them back if an ETI fellow wants them.
