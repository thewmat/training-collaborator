---
name: find-pbs
description: Find the athlete's official personal bests in public race results (Power of 10, runbritain, parkrun, World Athletics, Athlinks and national/club databases), store them, and reconcile them with Garmin bests. Use when setting up, when the athlete asks for their PBs, or after a race.
---

# Find PBs in public records

Public results are the record of truth for times; Garmin is the record for splits and HR.

## 1. Identify the athlete
Ask for: full name as entered in races, club(s), country, rough age category, and any profile links
they already know. Store links in `profile.public_results.profiles`. Never guess between two people
with the same name: confirm with a race the athlete remembers.

## 2. Where to look (by country)
- **UK:** Power of 10 (powerof10.uk athlete profile: "Best known performances" + every result; the new
  site may require a free sign-in), runbritain rankings (road races, handicap), parkrun (athlete page:
  parkrun.org.uk/parkrunner/<id>/all/ - parkrun blocks automated fetches; use a browser or ask for the
  athlete's barcode number and have them paste the page).
- **Ireland:** athleticsireland results, parkrun.ie. **US:** Athlinks, RunSignup/UltraSignup,
  USATF. **Europe:** national federation databases (e.g. DLV/ladv.de, FFA bases.athle.fr), race timing
  sites (MikaTiming, Racetec). **Elite / national level:** worldathletics.org athlete profile.
- Race-specific results pages (the timing company) for one-off races.

## 3. How to read them
In order of preference:
1. A browser you can drive (Claude in Chrome or the app's built-in browser): open the profile, read
   the page text. If a site needs a sign-in, ask the athlete to sign in in that browser; never ask for
   their password.
2. Web search for "<name> <club> power of 10" etc. to find the profile URL, then read it.
3. Ask the athlete to copy the profile page text into a file (or paste it).
Then: `python3 -m runlab pbs import <file> --source "<site + URL>" --dry-run`, check the parse
against the page, and run again without `--dry-run`. Single results: `python3 -m runlab pbs add 10K 41:30 --date 2026-05-03 --venue "..." --source "..."`.

## 4. Reconcile with Garmin
`python3 -m runlab bests` (add `--refresh` after a new sync; `sync --all-fits` for full history).
- Official PB with a matching Garmin race: link them in `me/athlete.md` (date, Garmin id) for splits.
- Garmin race faster than any official time: either an unlisted race (ask) or GPS error (check
  `review <id>`; a GPS course reading > 2 % long is not a PB).
- Training efforts are never PBs; they show what fitness supported.
Report: a table of official PBs with VDOT, the best one by VDOT (their strongest distance), and any
gaps (distances never raced).
