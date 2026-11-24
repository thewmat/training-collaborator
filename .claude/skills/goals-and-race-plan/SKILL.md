---
name: goals-and-race-plan
description: Capture what the athlete wants to achieve, turn it into measurable targets with the gap from today, and build race plans (pacing, fuelling, taper, checkpoints) with them. Use when the athlete states a goal, picks a race, asks if a time is realistic, or asks for a race-day plan.
---

# Goals and race plans

## Goal intake (their words first)
Ask, in one batch:
1. What do you want to achieve, and by when? (A time, a race, a ranking, beating someone, finishing,
   staying injury-free.)
2. Why this one? (It tells you what to protect when trade-offs come.)
3. Races entered vs considered. (Only "entered" races are commitments.)
4. Constraints: days available, work, travel, injuries, max sessions per week, coach.
Write it to `me/goals.md` verbatim under "What I want to achieve".

## Turn it into numbers
- Target time -> VDOT needed (`runlab estimate --race "<event> <target>"`) vs current VDOT
  (`runlab curve`): gap in VDOT and in s/km at threshold.
- Rate: current trend (`curve` rate s/km/week) and realistic gain (~1 VDOT per 4-6 weeks for a
  developing runner; slower near lifetime bests). Weeks available until the race.
- Verdict, plainly: on track / needs X s/km more threshold by <date> / not realistic by this date
  (give the date it would be).
- Relative goals ("beat my club's 10th fastest", "beat a rival"): look the bar up in public results
  (**find-pbs**), then treat it as a target time.
- Checkpoints: fitness reads on the curve (threshold pace at dates), not scheduled test sessions the
  athlete may not run. Record them in `me/goals.md`.

## Race plan (when a race is entered or asked for)
1. **Target and range**: A (good day), B (realistic), C (bad conditions), each with even-split pace.
2. **Pacing**: even or slight negative; first km no faster than target + 2 s/km. Marathon: cap HR at
   about LT2 - 8 bpm to halfway; half: settle at LT2 HR after 5 km; 10K: LT2 + 3-5 by halfway;
   5K: ignore HR.
3. **Course**: hills, turns, wind exposure, measured or not; adjust splits to the course.
4. **Fuel**: marathon 60-90 g carbs/h from 20-30 min; half 30-60 g/h optional; rehearsed in 2+ long runs
   with the race product and the race shoes. Generic targets only unless the athlete asks for products.
5. **Taper**: 10K/half 7-10 days, marathon 2-3 weeks; volume down 30-50 %, keep intensity, keep the
   sessions short and sharp.
6. **Shoes and kit**: race shoes worn in at least one session; nothing new on race day.
7. **Warm-up**: 10-15 min easy + 4 strides; for 5K/10K add 2-3 min at race pace.
Write the plan to `me/goals.md` under the race. After the race, run **review-session** with
`--official <metres>` and update PBs.
