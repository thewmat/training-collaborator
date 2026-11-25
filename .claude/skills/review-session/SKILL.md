---
name: review-session
description: Review a run or workout the athlete has completed - execution against the plan, rep pacing, rep-end HR, drift, HR validity, fitness read and what changes next. Use whenever the athlete mentions a run they did, asks "how did that go", or a new activity appears after sync.
---

# Review a session

## Gather
1. `python3 -m runlab sync` (skip if synced in the last hour).
2. `python3 -m runlab review` (latest) or `review <garmin id>`. For a race on a measured course add
   `--official <metres>`; for a race inside a longer recording add `--lap N`.
3. Find what was planned: `me/plan.md`, the coach's session, or what the athlete told you. If nothing
   was planned, judge it as what it looks like (easy, long, reps, race) and say so.
4. Look up the targets: pace bands from `runlab paces` / the curve, HR caps from `profile.json`.
5. For a threshold or tempo session with a comparable earlier one:
   `python3 -m runlab compare <earlier id> <this id>` (matched on cumulative work time).

## Judge (in this order)
1. **HR validity.** `strap` = trust it. `wrist` / `cadence lock` = say once that HR is indicative and
   judge on pace only. No fitness read from wrist HR.
2. **Execution vs intent.** Reps: pace band, evenness, last rep no more than 3 s/km faster, rep-end HR
   flat from rep 2 and under the cap. Easy: every minute below LT1 HR. Long: decoupling under 5 %.
   Tempo: started on the slow edge, eased at the cap, no kick. Race: halves, fade, where it was lost.
3. **The automatic checks** (`!` lines in the review). Confirm or dismiss each one with the evidence;
   don't repeat ones that don't matter for this session type.
4. **Fitness read.** Only from strap HR on steady running or reps of 4 min+. Pace at LT2 HR from
   steady-state minutes, compared on matched work time. If there is no valid read, say "no fitness
   read" and why. Never adjust for shoes.
5. **Patterns.** Check `me/log/` for the same breach in earlier sessions. If it repeats, name it.
6. **Load.** Week-to-date km vs last week.

## Write
Reply (terse):
```
Verdict: <one line: executed well / too fast / cap broken in reps 5-8 / ...>
Ran: <reps or splits that matter, with rep-end HR>
vs plan: <the gaps, in s/km and bpm>
Fitness: <pace at LT2 HR or "no valid read: wrist HR / reps too short">
Next: <the one change for the next session, or "none">
```
Then append the entry to `me/log/YYYY-MM.md` (format in `me/log/README.md`) and any new athlete fact to
`me/athlete.md`.

## Don't
- Don't rewrite the coach's next session. Give pace bands and caps for it if asked.
- Don't soften a broken cap because the athlete "felt good". Effort feelings go next to the data.
- Don't call a short-rep session a fitness gain or loss.
