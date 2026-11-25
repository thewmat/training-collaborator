# Training collaborator

Clone this, open it with Claude Code, connect your Garmin account, and you have a training
collaborator that:

- reviews every run and workout you do: rep pacing, rep-end heart rate, drift, whether you ran the
  session you meant to;
- tracks your fitness as an easy-to-read curve: the pace you run at your threshold heart rate, week by
  week;
- estimates race times with Jack Daniels' VDOT and gives Daniels' training paces;
- suggests sessions with pace bands and heart-rate caps when you ask (and leaves your coach's plan
  alone when you have one);
- finds your official PBs in public results and assembles your best performances from Garmin;
- writes a rich history of your training: builds, breaks, peaks, what worked;
- takes your goals in your own words and works with you on progress and race plans.

The Python toolkit (`runlab/`) does the maths; `CLAUDE.md` and the skills in `.claude/skills/` tell
Claude how to coach with it. Standard library only: no installs.

## Quick start

```bash
git clone https://github.com/<owner>/training-collaborator && cd training-collaborator
python3 -m runlab demo        # optional: a synthetic athlete, writes demo/out/dashboard.html
python3 -m runlab init        # your private workspace me/ and .env (both gitignored)
```

Then:

1. Create your Garmin key and put it in `.env`: [docs/garmin-setup.md](docs/garmin-setup.md)
   (5 minutes). No key? `python3 -m runlab import <Garmin export zip>` works too.
2. Open the folder in Claude Code and say **"set me up"**. Claude runs onboarding: pulls your data,
   asks about your thresholds, coach and goals, finds your PBs, and builds your dashboard.
3. After that, just talk to it: "how was this morning's session?", "am I getting fitter?", "what could
   I run for a half?", "I want to break 40 for 10K by May", "plan my race".

Requires Python 3.9+ and Claude Code (terminal, desktop app, IDE, or claude.ai/code).

## Privacy

- Everything personal lives in `me/`: profile, goals, PBs, training log, Garmin data, reports. It is
  in `.gitignore`. Don't force-add it, and don't fork this repo publicly with it.
- The Garmin key lives only in `.env` (gitignored) or your cloud environment's variables. Never paste it
  into a chat.
- Data goes from Garmin to your machine and nowhere else. Public-results lookups search for your name
  only when you ask for them.

## Commands

`python3 -m runlab <command>`; Claude runs these for you.

| Command | What it does |
|---|---|
| `init`, `doctor` | create the workspace; check key, thresholds, data |
| `sync` | pull Garmin data (first run: full history; then incremental) |
| `import PATH` | import FIT files / a Garmin export instead of using the API |
| `review [ID]` | analyse a run (default: the latest) |
| `compare A B` | compare two sessions matched on cumulative work time |
| `curve` | fitness curve, VDOT, race estimates |
| `estimate`, `paces` | VDOT race equivalents and training paces (`--race "10K 41:30"`) |
| `workouts` | session library at your VDOT with pace bands and HR caps |
| `bests` | best performances found in your Garmin data |
| `pbs list / add / import` | official PBs |
| `history` | training history report |
| `readiness` | green / amber / red for today |
| `dashboard` | everything above as one HTML page: `me/out/dashboard.html` |

## How it thinks

The rules Claude follows are in [CLAUDE.md](CLAUDE.md); the maths is in [docs/methods.md](docs/methods.md).
The short version:

- You decide. If you have a coach, their plan runs as written; Claude reviews and flags.
- Heart rate only counts from a chest strap. Wrist HR is indicative.
- Fitness is the pace you hold at a fixed heart rate, read from the running you actually did.
- Reps: lead with pace, cap with heart rate after two minutes, keep rep-end HR flat.
- Easy means under your aerobic-threshold heart rate, every minute.
- Verdicts are short, definitive and backed by the numbers.

## Layout

```
CLAUDE.md                 how Claude works with you
.claude/skills/           onboarding, connect-garmin, review-session, fitness-check, race-estimate,
                          workouts, find-pbs, training-history, goals-and-race-plan, weekly-review
runlab/                   toolkit: garmin, fit, analyse, curve, vdot, workouts, bests, pbs,
                          history, readiness, report, demo
docs/                     garmin-setup.md, methods.md
me.example/               template for your private workspace (copied to me/ by init)
tests/                    unit tests on synthetic data: python3 -m unittest
```
