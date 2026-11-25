---
name: weekly-review
description: Review the past training week - volume, sessions executed, fitness trend, readiness, patterns - and set targets for the coming week's sessions. Use on the athlete's planning day, or when they ask "how was my week" or "what's next week".
---

# Weekly review

1. `python3 -m runlab sync`, `python3 -m runlab dashboard`, `python3 -m runlab readiness`.
2. From `me/out/history.md` (last 12 weeks): km, runs, long run, sessions, zone minutes vs last
   week and the 4-week average. Flag jumps > 10-15 %, three quality days, long-run jumps > 15 %.
3. Sessions: list each quality session's verdict from `me/log/` (review any that weren't reviewed).
   Name repeated patterns.
4. Fitness: threshold pace now vs last week and 4 weeks ago (`runlab curve`). Say if it's a valid
   read (enough strap points near LT2).
5. Load in Daniels points: `python3 -m runlab points --weeks 6` (HR basis on strap runs, pace basis
   otherwise). A jump of more than ~15 % week on week is a load flag like a km jump.
6. Readiness trend: resting HR vs baseline, sleep, HRV, load ratio.
7. Coming week:
   - Coach's week: add pace bands and HR caps to each session (`workouts` skill, targets only), flag
     risks.
   - No coach: write the week only if they asked for it.
8. Reply (under ~150 words):
```
Week: <km> (<+/- %> vs last), <n> sessions, long <km>
Executed: <best and worst session in one line each>
Pattern: <one, if any>
Fitness: threshold <pace> (<+/- s/km> 4 wk), easy <band>
Readiness: <green/amber/red + why>
Next week: <the one thing to get right>
```
Log the summary at the end of the month file in `me/log/`.
