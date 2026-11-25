# Methods

Why each number is computed the way it is. Code references are to `runlab/`.

## Heart-rate validity (`fit.py`, `analyse.py`)

The FIT file lists every sensor used (device_info). HR counts as **strap** when an external heart-rate
sensor (ANT+ device type 120 or Bluetooth LE heart-rate) is recorded; otherwise **wrist**. Wrist HR
reads low in intervals (it lags and under-reads on surges) and can lock onto running cadence (HR within
3 bpm of steps/min for most of the run: **cadence lock**). Fitness reads use strap HR only; wrist HR is
reported as indicative.

## Thresholds (`config.py`)

LT1 (aerobic threshold, first lactate rise) caps easy running. LT2 (lactate turn point / threshold)
anchors threshold work. Priority: lab test > field test > estimate from max HR (LT1 79 %, LT2 90 %).
The source is always shown next to the number.

## Session review (`analyse.py`)

- **Timer time**: pauses removed. **GPS spikes**: any step faster than 8 m/s between records is capped.
- **Reps**: device laps split into fast and slow groups at the largest speed gap (at least 12 %).
- **Rep-end HR**: mean of the last 30 s. HR lags about two minutes, so a rep's average HR understates
  the effort; the end of the rep is what the cap applies to.
- **Checks**: pace creep (last rep > 3 s/km faster than the rest), uneven reps (> 6 s/km spread), fade
  inside a rep, rep-end HR rising > 3 bpm from rep 2 on, rep-end HR over LT2 + 2, easy runs over LT1.
- **Drift / decoupling**: speed per heartbeat in the second half vs the first, from minute 5.
  Under 5 % on a long run is good aerobic durability.
- **Matched comparison** (`compare_matched`): HR climbs through a session, so two sessions are compared
  minute-for-minute of cumulative work time, with the first 150 s of each rep dropped.

## Fitness curve (`curve.py`)

Every steady run and long rep is a point (pace, HR). Over a 30-day window a weighted reduced-major-axis
line `speed = a + b x HR` is fitted (weights = minutes, capped at 15; three 2.5 x MAD outlier passes).
RMA rather than least squares because both axes are noisy. The line is read at LT1 and LT2: **pace at
LT2 HR is the threshold pace**, the single best week-to-week fitness number, available without races or
tests. Points need >= 800 m and >= 4 min (shorter reps never reach steady-state HR), no long stops, and
strap HR whenever the window holds enough strap points.

Threshold pace -> VDOT uses Daniels' rule that T pace is 88 % of VDOT.

## VDOT (`vdot.py`)

Daniels and Gilbert's oxygen-cost and time-to-exhaustion curves:

```
VO2(v)    = -4.6 + 0.182258 v + 0.000104 v^2          v in m/min
%max(t)   = 0.8 + 0.1894393 e^(-0.012778 t) + 0.2989558 e^(-0.1932605 t)   t in min
VDOT      = VO2(race speed) / %max(race time)
```

Training paces: E 59-74 % of VDOT, T 88 %, I 97.5 %, M = marathon race pace, R = mile race pace less
2.3 % (matches the published tables). Checked: VDOT 50 -> 5K 19:57, 10K 41:21, T 4:15/km, I 3:55/km,
R 89 s/400 m.

**Super shoes**: estimates converted from training fitness add `plate_gain` (default 2.5 % speed) when
the athlete races in plated shoes. Race results already include the shoes and are not adjusted.

## Best performances (`bests.py`)

Three sources: activities that are races (Garmin event type or a race word in the name, at a standard
distance within 4 %), fastest rolling segments inside FIT files, and Garmin's own fastest-split fields
on the activity list (full history without FIT downloads). Everything gets a VDOT. Segments beating
the best race VDOT by > 3 % are flagged as probable GPS error; anything above VDOT 85 is dropped.

## Readiness (`readiness.py`)

Against the athlete's own baseline (median of days 8-35 back): 7-day resting HR +3 bpm amber / +5 red,
sleep score, HRV below Garmin's balanced range, Body Battery, acute:chronic load (> 1.3 amber,
> 1.5 red). Green = run the session at its targets,
amber = slow edge of every band, red = easy or rest.

## Training history (`history.py`)

Monday-start weeks from the activity list; builds = the 12 weeks before each race or PB date; breaks =
10+ days without a run; peaks = highest 8-week rolling volume blocks; zone minutes from strap-HR FIT
files.

## Workouts (`workouts.py`)

Daniels' session types and volume limits (T <= 10 % of the week, I <= 8 % / 10 km, R <= 5 % / 8 km,
M <= 20 % / 29 km, long <= 25 % / 150 min), with threshold-system variants: short-rest threshold reps are
LT2 effort (~1.5 % faster than continuous T on 1 km/60 s), guarded by rep-end HR.

## Detailed Daniels tables (`daniels.py`)

Every table is computed from the VDOT equations at the athlete's VDOT; none is copied.

- **Zone grid**: Daniels' mapping between % VO2max and % max HR, `%HRmax = 0.65 + 0.35 x (%VO2max - 0.59) / 0.41`
  (capped at 100 %). Recovery 65 %, easy 70-75 % of max HR, converted to % VO2max and pace. Moderate and
  high aerobic sit one and two thirds of the way from the top of easy to marathon pace (and HR). Race rows
  use the VDOT race time and Daniels' `%max(t)`. % HR reserve uses resting HR from the profile. Measured
  LT1/LT2 caps win over this generic HR column.
- **Continuous tempo**: T pace for 20 min, slowed by 1.2, 2.2, 2.7, 3.3, 3.8, 4.3, 4.9 and 5.5 % for 25-60 min.
- **Rep splits**: 100-2000 m at R, I, T and mile, 5K, 10K, half and marathon race pace.
- **Race table**: 1500 m to 50K by VDOT (not Riegel).
- **Intensity points**: Daniels' points per minute by % VO2max (0.1 at easy, 0.683 at T, 1.0 at VO2max,
  2.1 at 120 %), linearly interpolated. Per run: 60-second bins of the FIT file, scored on % max HR when the
  run has chest-strap HR and max HR is known, otherwise on pace (% VO2max of the bin's speed at the
  current VDOT). Weekly reference levels: 50 novice high-school, 100 advanced high-school, 150
  collegiate, 200 elite.
- **Heat**: no cost to 60 F (15.6 C), then 0.75 % of 5K time per 5 F. For race-day plans only.

Checked against a widely used Daniels workbook at VDOT 63.4: zone paces, aerobic interpolation, tempo
table and heat table agree to the second. Two deliberate differences: race projections use VDOT
throughout (the workbook can switch to Riegel), and R and I keep the published-table calibration (R =
mile pace + 2.3 %, I = 97.5 %), about 1 s per 400 m slower than the workbook's R formula.

## Auto-refresh (`auto.py`, `schedule.py`)

A pass: incremental sync (skipped without a key or in the demo workspace), then every run not seen
before is reviewed (`analyse`), written to `me/out/reviews/` and listed in `me/out/inbox.md`. The first
pass only records a baseline. A run whose FIT is not downloaded yet waits up to 3 days. When anything is
new the curve, bests, history, readiness and dashboard are rebuilt and `profile.json["current"]` is
rewritten (VDOT, pace at LT1/LT2, easy band, window, last run, highest strap HR seen). A lock file stops
overlapping passes. Flags (strap max HR above the profile max, a threshold-pace change of 1 s/km or more
since the last refresh) are reported, never applied.
