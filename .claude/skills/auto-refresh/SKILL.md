---
name: auto-refresh
description: Set up, check or stop automatic refresh - new Garmin runs reviewed and the curve, profile snapshot and dashboard rebuilt without being asked. Use when the athlete wants updates to happen on their own, asks why a run wasn't picked up, or wants it stopped.
---

# Auto-refresh

Garmin's Personal API is pull-only: new runs are found by checking. `python3 -m runlab auto` is one pass
(sync, review new runs, rebuild curve, bests, history, readiness, dashboard, write `profile.json`
`current`). Three ways to run it:

1. **Background job (recommended):** `python3 -m runlab schedule install [--every 30]`.
   macOS LaunchAgent, Linux cron, Windows Task Scheduler. Runs while the computer is on and the athlete
   is logged in. Desktop notification per new run. Log: `me/out/auto.log`.
   - macOS: if the repo is inside Desktop, Documents or Downloads, the job may be blocked by privacy
     settings. Fix: move the repo (e.g. `~/training-collaborator`) and reinstall, or give the Python
     binary Full Disk Access.
   - `--claude` also has Claude Code write the verdicts headless after each new run (uses the
     athlete's Claude plan; needs the `claude` CLI). Offer it; don't turn it on unasked.
2. **Session-start hook:** already in `.claude/settings.json`. Every new Claude Code conversation runs a
   pass first; its output arrives as context.
3. **`python3 -m runlab watch`** in an open terminal.

## Check
`python3 -m runlab schedule status`: job installed or not, last pass, runs on record, runs waiting for
their FIT, last log lines. A run is missing when: the watch hasn't synced to Garmin Connect yet; the
FIT is still processing (it is retried for 3 days); the activity type is not running; or sync failed
(the log says why: usually the key, see **connect-garmin**).

## Stop
`python3 -m runlab schedule remove`. The hook can be removed from `.claude/settings.json`.

## Rules
- A pass never changes thresholds, goals, the plan or the coach's sessions. It flags; the athlete
  decides.
- Verdicts are still Claude's job: runs in `me/out/inbox.md` get a review-session verdict, then their
  line is deleted.
- Cloud sessions (claude.ai/code) start from a fresh copy without `me/`, so scheduling there cannot
  keep history: the background job belongs on the athlete's own computer.
