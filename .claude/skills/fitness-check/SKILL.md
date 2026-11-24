---
name: fitness-check
description: Read the athlete's current fitness and its trend from the fitness curve (pace at LT1 and LT2 heart rate), explain it in plain language and show the chart. Use for "am I getting fitter", "what's my threshold pace", "when was I last this fit", or after a block of training.
---

# Fitness check

1. `python3 -m runlab sync`, then `python3 -m runlab curve` (add `--refresh` after changing
   thresholds). `python3 -m runlab dashboard` redraws the chart in `me/out/dashboard.html`.
2. Read in this order:
   - **Threshold pace** (pace at LT2 HR, current 30-day window) and the 4-week change in s/km.
   - **Easy pace band** (HR a few beats under LT1).
   - **Rate**: s/km per week. Typical returns: 1-3 s/km/week in a build, flat in a maintenance block.
   - **Confidence**: points, r2, strap vs wrist, and whether LT2 sits inside the HR range of the data
     ("extrapolated" windows are weak: say so).
   - **Best on record** and the gap to it.
3. Explain in plain words: "At the same heart rate you now run X s/km faster than a month ago."
   Lower pace at the same HR = fitter. One number up front, the rest below.
4. Cross-check with races: `runlab bests` / `runlab pbs list` VDOTs vs the curve VDOT. If they disagree
   by > 2 VDOT, say which you trust and why (a recent race beats a curve read; a curve read beats an
   old race).
5. "When was I last this fit?": convert past races (PBs and Garmin races) to 10K-equivalents with
   `runlab estimate --race "<event> <time>"` and compare with today's curve estimate. HR-based reads
   only exist where strap HR exists.

## Caveats to state only when they apply
- Heat, altitude and hills raise HR at a given pace; cold lowers it a little. Name the condition, keep
  the raw number.
- A big load week depresses the read (fatigue masks fitness). Say so if this week's load ratio > 1.3.
- Fewer than ~15 strap points in the window = provisional.
