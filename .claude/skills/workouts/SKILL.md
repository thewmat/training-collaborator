---
name: workouts
description: Suggest sessions, pace bands and HR caps using Daniels' tables and the athlete's thresholds, or set targets for a coach's session. Use only when the athlete asks for a session, a week, paces for a workout, or targets for their coach's workout.
---

# Workouts and paces

## Before writing anything
- Did the athlete ask for a session? If not, don't write one.
- Coach? If `coach.has_coach`, you set **targets for the coach's sessions** (pace bands, HR caps, stop
  rules). You never replace or reshape them.
- Current numbers: `python3 -m runlab curve` (threshold pace, VDOT) and `python3 -m runlab readiness`.
- Week so far and last week's km: `python3 -m runlab history` (last 12 weeks table).

## Library
`python3 -m runlab workouts --system threshold|daniels|marathon [--km WEEKLY_KM]` prints every session
type with its pace band, HR cap and rule at the current VDOT. Daniels volume limits per session: T
<= 10 % of the week, I <= 8 % (max 10 km), R <= 5 % (max 8 km), M <= 20 % (max 29 km), long run <= 25 %
or 150 min.

## Detailed Daniels tables
`python3 -m runlab tables [--only zones,tempo,splits,races,points,heat]` at the current VDOT:
- **zones**: recovery, easy, moderate and high aerobic, then marathon to mile intensity, with % VO2max,
  Daniels' % max HR, % HR reserve, pace per km and mile. Measured LT1/LT2 caps win over the % max HR
  column.
- **tempo**: continuous T pace for 20-60 min (a 60-min tempo is ~5.5 % slower than a 20-min one).
- **splits**: 100 m to 2000 m rep times at R, I, T and mile, 5K, 10K, half and marathon race pace. Use
  these for track and rep targets instead of converting by hand.
- **points**: Daniels intensity points per minute; `python3 -m runlab points` totals them per week.

## Setting targets for any session
1. Identify the intensity: easy, long, sub-threshold, threshold (continuous or reps), 10K, 5K/I, R,
   hills, strides.
2. Pace band from the library; adjust for rest:
   - threshold reps off 60 s: ~1.5 % faster than continuous T (1 km reps); 6-min reps ~1-2 % slower.
   - longer rest (2 min+) on 1 km reps: rep pace drifts toward 10K; keep the HR cap to stop it.
3. HR cap as rep-end HR (last 30 s): sub-threshold LT2 - 3; threshold reps LT2 + 2; continuous tempo
   <= LT2; easy < LT1. Ignore HR for the first ~2 min of a rep.
4. Stop / adjust rules, always:
   - rep-end HR up > 3 bpm on the previous rep, or over the cap -> next rep 3 s/km slower;
   - two reps over the cap -> stop 2 reps early;
   - last rep no more than 3 s/km faster than the others;
   - readiness amber -> slow edge of every band; red -> easy instead.
5. Write the band fast-slow, e.g. "3:52-3:55/km, rep-end <= 172".

## Writing a week (only when asked)
- Respect the athlete's system and max quality sessions per week (`profile.preferences`).
- Threshold (Norwegian-style): Tue double threshold (AM sub-threshold long reps, PM shorter reps),
  Thu threshold, Sat X-element hills (15-20 x 200 m uphill, ~5K effort, jog down), Sun easy long.
  Everything else easy. Progress by adding reps or shortening rest, one change per week.
- Daniels: phase I base (E + strides), II (R + T), III (I + T), IV (T + race-specific).
- Volume: +10 % per week max over the last 3-week average; a down week every 3-4 weeks.
- Group or club sessions: note that groups pull reps over the cap; set the cap before the session.
- Write it to `me/plan.md` with the bands and caps. Make Garmin workouts with reps and recoveries only
  (no warm-up/cool-down steps) if the athlete asks; the personal API cannot write workouts, so give the
  steps for Garmin Connect.
