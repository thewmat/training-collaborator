---
name: onboarding
description: First-run setup for a new athlete - create the private workspace, connect Garmin, set thresholds, find PBs, build the history and record goals. Use when me/profile.json does not exist or the athlete says they are new.
---

# Onboarding

Goal: in one conversation, go from a fresh clone to a dashboard, a history and written goals.
Ask questions in small batches (max 4 at a time). Do the work between batches.

## 1. Workspace
Run `python3 -m runlab init`. It creates `me/` (gitignored) and `.env`.

## 2. Garmin
Run the **connect-garmin** skill. If the athlete has no key yet and doesn't want one, use
`python3 -m runlab import <path>` on a Garmin export (Garmin Connect > Account > Export Your Data, or
"Export Original" on single activities). Without the key there is no sleep/HRV/readiness.

## 3. About the athlete (write answers to `me/profile.json` and `me/athlete.md`)
Batch 1:
- Name (as it appears in race results), club, country. Year of birth.
- Do you have a coach who writes your sessions? (sets `coach.has_coach`; if yes, ask how they share
  weeks: screenshots, TrainingPeaks, text.)
- Do you run with a chest strap? Which watch?
- Any lab or field test with HR thresholds? (LT1/aerobic threshold, LT2/lactate turn point, max HR.)
Batch 2:
- Current injuries or ones that recur? (sets `injury.watch`; pain threshold default 2/10.)
- Do you race in carbon-plated super shoes? (sets `racing.super_shoes`.)
- Training style you like (threshold/Norwegian, Daniels, high volume, run/walk ...), max quality
  sessions per week, days you can't run.
- How do you want me to talk to you? (Default: terse and definitive.)

If no measured thresholds: run `python3 -m runlab sync`, then use max HR from a recent race or hard
session on a strap (`runlab review`), and let `config.thresholds` estimate LT1/LT2. Record
`hr.source = "estimated from max HR"` and tell the athlete a lab or field test would sharpen it.

## 4. Data
- `python3 -m runlab sync` (full activity history, FIT files for 120 days). For a deep best-performance
  search add `--all-fits` (slow: one download per run).
- **find-pbs** skill: official PBs from public results.
- `python3 -m runlab dashboard`, then **training-history** skill for the narrative.

## 5. Goals
Run **goals-and-race-plan** to capture what they want, in their words.

## 6. Close
Reply with: current fitness (threshold pace, easy pace, VDOT, race estimates), the three facts from
their history that matter most, their goal restated with the gap to it, and where the dashboard is
(`me/out/dashboard.html`).
