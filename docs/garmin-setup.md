# Connect your Garmin account

The toolkit reads your Garmin data through Garmin Connect's **Personal API**: a free, read-only key you
create yourself. Nothing goes through a third-party server. The key stays on your machine (or in your
private cloud environment).

## 1. Create the key

1. Sign in at https://connect.garmin.com on a computer.
2. Open https://connect.garmin.com/app/settings/personalApiToken
   (profile picture > Settings > Personal API).
3. Create a key. Choose the longest expiry offered (1 year).
4. Copy it. **Garmin shows it once.** If you lose it, revoke it and make another.

Treat it like a password: it opens your activities, heart rate, sleep and health data.

## 2. Store it

### Claude Code on your computer (terminal, desktop app, IDE)

```bash
python3 -m runlab init        # creates me/ and .env (both gitignored)
```

Open `.env` in an editor and fill in the line:

```
GARMIN_PERSONAL_API_KEY=paste-your-key-here
```

Don't paste the key into the chat with Claude. `.env` is in `.gitignore`; `git status` should never
list it.

### Claude Code on the web (claude.ai/code)

The repository is cloned fresh into a cloud container each session, so the key goes in the
environment settings instead of a file:

1. Open the environment settings for this repository (environment picker > edit / settings).
2. Add an environment variable: `GARMIN_PERSONAL_API_KEY` = your key.
3. Network access: allow the domain `personal.connectapi.garmin.com` (custom allowlist), or the
   container cannot reach Garmin.
4. Start a new session so the variable and network rule apply.

Your `me/` workspace does not persist between cloud sessions. Either work locally, or keep `me/` in a
**separate private** repository and clone it into `me/` at the start of a session (never in this one).

## 3. Check it

```bash
python3 -m runlab doctor
```

`connection {"ok": true ...}` means it works. Then pull your data:

```bash
python3 -m runlab sync              # full activity list, FIT files for the last 120 days,
                                    # daily summaries and HRV (180 days), sleep (1 year)
python3 -m runlab sync --all-fits   # optional, slow: a FIT file for every run ever (deep PB search)
```

Later syncs only fetch what's new.

## What the Personal API gives you

| Data | Available |
|---|---|
| Activity list, full history | yes |
| Original FIT files (1 s records, laps, HR sensor used) | yes |
| Daily summaries (resting HR, Body Battery, stress) | yes, 180 days per request |
| Sleep | yes, 28 days per request |
| HRV | yes, on watches that record it |
| Workouts / calendar (write) | no: build workouts in Garmin Connect yourself |
| Gear (shoes) | no: tell Claude which shoes you wore |
| Training status, readiness score | no: the toolkit computes its own readiness |

## No key? Import files instead

- One run: Garmin Connect > activity > cog > Export Original -> a .zip with the FIT file.
- Everything: Garmin Connect > Account settings > Data management > Export your data (Garmin emails a
  link; the archive holds every FIT file).

```bash
python3 -m runlab import ~/Downloads/garmin-export.zip
```

Every report works from FIT files except sleep, HRV and readiness.

## Troubleshooting

| Message | Fix |
|---|---|
| `GARMIN_PERSONAL_API_KEY is not set` | add it to `.env` (local) or the environment variables (web) |
| `token exchange failed: HTTP 401` or `403` | key mistyped, revoked or expired: create a new one |
| `cannot reach personal.connectapi.garmin.com` | web: add the domain to the environment's network allowlist |
| `HTTP 429` | Garmin rate limit: wait and run sync again; it resumes where it stopped |
