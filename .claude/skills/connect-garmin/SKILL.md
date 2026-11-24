---
name: connect-garmin
description: Connect the athlete's Garmin account - create a Personal API key, store it safely in .env or the cloud environment, verify the connection, and fix sync errors. Use for any Garmin key, sync or connection problem.
---

# Connect Garmin

Full steps for the athlete: `docs/garmin-setup.md`. Your job: walk them through it, verify, fix.

## Rules
- The key is a password to their health data. Never ask them to paste it into chat. Never write it
  anywhere except `.env` (gitignored) or the cloud environment's variables. If they paste it into
  chat anyway, tell them to revoke it and create a new one.
- Never commit `.env`. Check `git status` shows it untracked-and-ignored before any commit.

## Steps
1. Ask: are they running Claude Code locally (terminal/desktop/IDE) or on the web (claude.ai/code)?
2. Point them to the key page: https://connect.garmin.com/app/settings/personalApiToken
   (Garmin Connect web > profile > Settings > Personal API). Expiry: pick the longest (1 year). The key
   is shown once.
3. Local: they open `.env` (created by `runlab init`) and set `GARMIN_PERSONAL_API_KEY=...` themselves.
   Web: they add the variable `GARMIN_PERSONAL_API_KEY` in the cloud environment's settings and add
   `personal.connectapi.garmin.com` to the environment's allowed network domains, then start a new
   session.
4. Verify: `python3 -m runlab doctor`. `connection {"ok": true ...}` = done.
5. First pull: `python3 -m runlab sync`.

## Errors
| Message | Cause | Fix |
|---|---|---|
| `GARMIN_PERSONAL_API_KEY is not set` | not in .env / environment | step 3 |
| `token exchange failed: HTTP 401/403` | wrong, revoked or expired key | create a new key |
| `cannot reach personal.connectapi.garmin.com` | network allowlist (web) | add the domain, new session |
| `HTTP 404` on workouts/gear | the personal tier is read-only and has no gear | expected; use Garmin Connect for workouts, ask for shoes |
| `HTTP 429` | rate limit | the client backs off; rerun later |

No key and no wish to make one: `python3 -m runlab import <folder or export zip>`. Everything except
sleep, HRV and readiness works from FIT files.
