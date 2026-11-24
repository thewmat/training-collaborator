---
name: training-history
description: Build a rich, contextual history of the athlete's training and performance - volume by year, builds into each race, breaks, peaks, PB progression and what worked. Use at onboarding, when the athlete asks about their history, or before planning a new block.
---

# Training and performance history

## Gather
1. `python3 -m runlab sync` (full activity history; `--all-fits` once for deep bests).
2. `python3 -m runlab history` -> `me/out/history.md` (years, builds before races, breaks, peaks,
   last 12 weeks with time in zones).
3. `python3 -m runlab bests` and `python3 -m runlab pbs list`.
4. `python3 -m runlab curve` for the current fitness and best-on-record window.
5. Read `me/athlete.md` and `me/log/` for injuries and context the data can't show.

## Write the history (to `me/out/history-narrative.md`, then summarise in chat)
Sections:
1. **Arc**: when they started, total km, the big years, the shape (steady climber, boom and bust,
   comeback).
2. **Best performances**: official PBs with VDOT and date; the strongest distance by VDOT; when the
   peak was.
3. **Builds that worked and builds that didn't**: for each race with a build, mean/peak km, longest
   run, sessions per week, result vs VDOT at the time. Pull out what the best results had in common
   (volume, consistency, long runs, sessions). Be specific: "PB builds averaged 95 km/week with
   no break over 7 days; the DNF build had two 10-day gaps."
4. **Breaks**: every gap of 10+ days, with the cause if known (ask). Injury pattern if any.
5. **Now vs then**: current fitness against the best-on-record window and the PB VDOTs; weeks of
   consistency since the last break.
6. **Three lessons** that should shape the next block. Evidence for each.

Keep facts and inferences apart. Where Garmin data starts later than the athlete's running career, say
the history before that comes from public results only.
