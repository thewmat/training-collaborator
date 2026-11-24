---
name: race-estimate
description: Estimate race times with VDOT (Daniels/Gilbert), from a recent race, the fitness curve or both, and convert between distances. Use for "what could I run for 10K", predicted times, equivalent performances, or pacing a target time.
---

# Race estimate

1. Pick the source, best first:
   - a race in the last ~8 weeks on a measured course: `python3 -m runlab estimate --race "10K 41:30"`
   - the fitness curve (threshold pace -> VDOT): `python3 -m runlab estimate` (after `runlab curve`)
   - an older PB, flagged as old: `--race "<event> <time>"`
2. Give the estimate for the distance asked, with its VDOT and source, and a range: +/- 1 % for a 5K-10K
   from a recent race, +/- 2 % from the curve, wider for the marathon.
3. **Super shoes.** If `profile.racing.super_shoes` is true and the source is training (the curve),
   `estimate` applies `plate_gain` (default 2.5 % speed). A race result already includes the shoes:
   no adjustment. Say which applied.
4. **Distance-specific limits.** VDOT assumes training for the distance. Half and marathon estimates
   need the long runs to match: if the longest run in the last 8 weeks is under ~75 % of the half or
   ~32 km for the marathon, say the estimate is optimistic and by roughly how much is unknowable.
5. **Target times.** For a goal time: `--race "<event> <goal>"` gives the VDOT it needs. Gap in VDOT
   points and in s/km at threshold. Typical gains: ~1 VDOT per 4-6 weeks of consistent training for a
   returning or developing runner, less near a lifetime best. Say whether the gap is realistic by the
   date, plainly.
6. **Pacing a race:** even splits at goal pace; for the marathon cap HR in the first half at about
   LT2 - 8 bpm and don't open at threshold HR. Fuel 60-90 g carbs/h from 20-30 min, rehearsed in training.
