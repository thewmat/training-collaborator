"""Auto-refresh: pull new runs, review them, and rebuild the curve, profile snapshot and dashboard.

One pass (`python3 -m runlab auto`):
  1. sync from Garmin (incremental; skipped without a key, stored data is used)
  2. find runs not seen before (the first pass only records a baseline, so history is not re-reviewed)
  3. review each new run: report to me/out/reviews/, a line in me/out/inbox.md for Claude to give a verdict
  4. rebuild curve, bests, history, readiness and the dashboard
  5. write the fitness snapshot into me/profile.json ("current", machine-written) and flag anything the
     athlete should decide (a strap max HR above the profile's max, a fitness change since last pass)

Garmin's Personal API is pull-only, so "a new run is published" is detected by polling: run this from a
scheduler (`runlab schedule install`), keep `runlab watch` open, or let the Claude Code session-start hook
run it. Nothing here changes thresholds, plans or goals: the athlete decides.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time

from . import config

LOCK_MAX_S = 30 * 60


def _state_path():
    return config.data("auto.json")


def _load_state():
    p = _state_path()
    return json.load(open(p)) if os.path.exists(p) else {}


def _save_state(s):
    os.makedirs(os.path.dirname(_state_path()), exist_ok=True)
    json.dump(s, open(_state_path(), "w"), indent=1)


class Lock:
    """One pass at a time (scheduler, watch and the session hook can overlap)."""

    def __init__(self):
        self.p = config.data("auto.lock")
        self.ok = False

    def __enter__(self):
        os.makedirs(os.path.dirname(self.p), exist_ok=True)
        if os.path.exists(self.p) and time.time() - os.path.getmtime(self.p) < LOCK_MAX_S:
            return self
        open(self.p, "w").write(str(os.getpid()))
        self.ok = True
        return self

    def __exit__(self, *exc):
        if self.ok and os.path.exists(self.p):
            os.remove(self.p)


def _summary(a, r):
    km = r["dist_m"] / 1000
    from .units import hms
    head = (f"{a['startTimeLocal'][:16]}  {a.get('activityName') or 'Run'}  {km:.1f} km in {hms(r['time_s'])} "
            f"({hms(r['pace_s_km'])}/km)  HR {r['hr'] or '-'} [{r['hr_quality']}]")
    if r["reps"]:
        head += f"  {len(r['reps'])} reps"
    return head, r["checks"]


def _review(a):
    from . import analyse, garmin
    if not garmin.have_fit(a["activityId"]):
        return None
    path = analyse.find_fit(a["activityId"])
    r = analyse.analyse(path)
    title = f"{a['startTimeLocal'][:16]} {a.get('activityName') or 'Run'} ({a['activityId']})"
    out = config.out("reviews", f"{a['startTimeLocal'][:10]}_{a['activityId']}.txt")
    open(out, "w").write(analyse.report(r, title) + "\n")
    return r, out


def _inbox_add(lines):
    p = config.out("inbox.md")
    new = not os.path.exists(p) or not open(p).read().strip()
    with open(p, "a") as f:
        if new:
            f.write("# Runs waiting for a verdict\n\nWritten by `runlab auto`. Claude reviews each run (skill "
                    "review-session), logs the verdict in me/log/, then deletes its entry here.\n\n")
        for ln in lines:
            f.write(ln + "\n")


def _refresh(log):
    from . import bests, curve, history, readiness, report
    c = None
    for name, fn in (("curve", lambda: curve.build()), ("bests", bests.assemble), ("history", history.build),
                     ("readiness", lambda: json.dump(readiness.build(), open(config.out("readiness.json"), "w")))):
        try:
            res = fn()
            if name == "curve":
                c = res
        except SystemExit as e:
            log(f"{name}: skipped ({e})")
        except Exception as e:                           # noqa: BLE001 - one broken report must not stop the rest
            log(f"{name}: failed ({type(e).__name__}: {e})")
    try:
        report.build()
    except Exception as e:                               # noqa: BLE001
        log(f"dashboard: failed ({type(e).__name__}: {e})")
    return c


def _snapshot(c, prof, new_runs, flags):
    """Machine-written fitness snapshot in profile.json["current"]. Returns the previous snapshot."""
    prev = prof.get("current") or {}
    cur = {"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "written_by": "runlab auto (do not edit)"}
    if c and c.get("current"):
        k = c["current"]
        cur.update({"vdot": k["vdot"], "pace_lt2": k["pace_lt2"], "pace_lt1": k["pace_lt1"],
                    "kmh_lt2": k["kmh_lt2"], "easy_band": k["easy_band"], "curve_window": k["window"],
                    "hr_confidence": k["hr_confidence"], "change_4wk_s_km": k["change_4wk_s_km"],
                    "thresholds": c["thresholds"]})
    from . import garmin
    runs = sorted((a for a in garmin.load("activities.json") if garmin.is_run(a)), key=lambda a: a["startTimeLocal"])
    if runs:
        cur["last_run"] = {"date": runs[-1]["startTimeLocal"][:16], "name": runs[-1].get("activityName") or "Run",
                           "id": str(runs[-1]["activityId"])}
    strap_max = max((r["max_hr"] for r in new_runs if r and r.get("hr_quality") == "strap" and r.get("max_hr")),
                    default=None)
    if strap_max:
        cur["max_hr_seen_strap"] = max(strap_max, prev.get("max_hr_seen_strap") or 0)
        if prof["hr"].get("max") and strap_max > prof["hr"]["max"]:
            flags.append(f"chest-strap max HR {strap_max} is above the profile's max {prof['hr']['max']}: "
                         "the athlete decides whether to update hr.max")
    raw = json.load(open(config.path("profile.json"))) if os.path.exists(config.path("profile.json")) else {}
    raw["current"] = cur
    config.save_profile(raw)
    return prev, cur


def notify(title, body):
    """Best-effort desktop notification (macOS, Linux with notify-send, Windows toast via PowerShell)."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["osascript", "-e", f"display notification {json.dumps(body)} with title {json.dumps(title)}"],
                           timeout=10, check=False, capture_output=True)
        elif sys.platform.startswith("linux") and shutil.which("notify-send"):
            subprocess.run(["notify-send", title, body], timeout=10, check=False, capture_output=True)
        elif sys.platform.startswith("win"):
            ps = ("[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null;"
                  "$n=New-Object System.Windows.Forms.NotifyIcon;$n.Icon=[System.Drawing.SystemIcons]::Information;"
                  f"$n.Visible=$true;$n.ShowBalloonTip(8000,{json.dumps(title)},{json.dumps(body)},'Info');Start-Sleep 9")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], timeout=20, check=False, capture_output=True)
    except Exception:                                    # noqa: BLE001 - notifications are optional
        pass


CLAUDE_PROMPT = ("New runs were synced by runlab auto and are listed in me/out/inbox.md. Follow CLAUDE.md: "
                 "review each listed run with the review-session skill, write the verdict to me/log/, then delete "
                 "that run's entry from me/out/inbox.md. Do not change the plan, goals or thresholds.")


def run_claude(log=print):
    """Optional: have Claude Code write the verdicts headless (uses the athlete's Claude plan)."""
    exe = shutil.which("claude")
    if not exe:
        log("claude: not installed, verdicts wait for the next conversation")
        return False
    r = subprocess.run([exe, "-p", CLAUDE_PROMPT, "--permission-mode", "acceptEdits",
                        "--allowedTools", "Read,Edit,Write,Glob,Grep,Bash(python3 -m runlab:*)"],
                       cwd=config.ROOT, capture_output=True, text=True, timeout=1800)
    log("claude: " + ("verdicts written" if r.returncode == 0 else f"failed ({r.stderr.strip()[:200]})"))
    return r.returncode == 0


def run(sync=True, quiet=False, notify_on_new=False, with_claude=False, log=None):
    """One pass. Returns {"status", "new": [...], "flags": [...], "messages": [...]}."""
    msgs = []
    log = log or (lambda *a: msgs.append(" ".join(str(x) for x in a)))
    res = {"status": "ok", "new": [], "flags": [], "messages": msgs}
    if not os.path.exists(config.path("profile.json")):
        res["status"] = "not set up"
        return res
    with Lock() as lk:
        if not lk.ok:
            res["status"] = "busy"
            return res
        from . import garmin
        if sync and config.profile().get("demo"):
            log("demo workspace: no Garmin sync")
        elif sync and os.environ.get("GARMIN_PERSONAL_API_KEY"):
            try:
                garmin.sync(log=lambda *a: None)
            except Exception as e:                       # noqa: BLE001 - keep going on stored data
                res["flags"].append(f"Garmin sync failed: {type(e).__name__}: {str(e)[:200]}. Using stored data.")
        elif sync:
            log("Garmin key not set: using stored data (python3 -m runlab import works without a key)")
        state = _load_state()
        runs = sorted((a for a in garmin.load("activities.json") if garmin.is_run(a)), key=lambda a: a["startTimeLocal"])
        seen = set(state.get("seen") or [])
        if "seen" not in state:                          # first pass: baseline only
            seen = {str(a["activityId"]) for a in runs}
            log(f"baseline: {len(seen)} runs already on record; new runs from now on are reviewed automatically")
        pending = [a for a in runs if str(a["activityId"]) not in seen]
        reviewed, waiting = [], []
        for a in pending:
            got, err = None, None
            try:
                got = _review(a)
            except SystemExit as e:
                err = str(e)
            age = (dt.date.today() - dt.date.fromisoformat(a["startTimeLocal"][:10])).days
            if got is None and err is None and age < 3:
                waiting.append(str(a["activityId"]))     # FIT not downloaded yet: try again next pass
                continue
            if err:
                log(f"{a['activityId']}: not reviewable ({err})")
            seen.add(str(a["activityId"]))
            if got:
                r, path = got
                head, checks = _summary(a, r)
                reviewed.append(r)
                res["new"].append({"id": str(a["activityId"]), "summary": head, "checks": checks,
                                   "report": os.path.relpath(path, config.home())})
        if res["new"]:
            _inbox_add([f"- [ ] {n['summary']}  (report: {n['report']})" + "".join(f"\n      ! {c}" for c in n["checks"])
                        for n in res["new"]])
        changed = bool(res["new"]) or "seen" not in state or not os.path.exists(config.out("dashboard.html"))
        c = _refresh(log) if changed else None
        if changed:
            prev, cur = _snapshot(c, config.profile(), reviewed, res["flags"])
            if prev.get("kmh_lt2") and cur.get("kmh_lt2"):
                d = 3600 / cur["kmh_lt2"] - 3600 / prev["kmh_lt2"]
                if abs(d) >= 1:
                    res["flags"].append(f"threshold pace {cur['pace_lt2']}/km, {abs(d):.0f} s/km "
                                        f"{'faster' if d < 0 else 'slower'} than the last refresh ({prev['pace_lt2']}/km)")
            res["current"] = cur
        state.update({"seen": sorted(seen), "last_pass": dt.datetime.now().isoformat(timespec="seconds"),
                      "waiting_for_fit": waiting})
        _save_state(state)
    if res["new"] and notify_on_new:
        notify("New run reviewed", "; ".join(n["summary"].split("  ")[1] for n in res["new"])[:200])
    if res["new"] and with_claude:
        run_claude(log)
    return res


def text(res, quiet=False, hook=False):
    """Human/Claude-readable result. quiet: nothing unless there is news."""
    if res["status"] == "not set up":
        return "" if quiet else "Not set up yet: run python3 -m runlab init, then onboarding."
    if res["status"] == "busy":
        return "" if quiet else "Another refresh is running."
    if quiet and not (res["new"] or res["flags"]):
        return ""
    L = []
    if hook:
        L.append("runlab auto (session start): data refreshed.")
    if res["new"]:
        L.append(f"{len(res['new'])} new run{'s' if len(res['new']) > 1 else ''} reviewed (verdicts pending in me/out/inbox.md):")
        for n in res["new"]:
            L.append("  " + n["summary"])
            L += [f"    ! {c}" for c in n["checks"]]
    elif not quiet:
        L.append("No new runs.")
    cur = res.get("current") or {}
    if cur.get("pace_lt2"):
        L.append(f"Fitness: threshold pace {cur['pace_lt2']}/km, easy {cur['easy_band']}/km, VDOT {cur['vdot']} "
                 f"({cur['curve_window']}).")
    L += [f"Flag: {f}" for f in res["flags"]]
    if not quiet:
        L += res["messages"]
    return "\n".join(L)


def watch(every_min=30, notify_on_new=True, with_claude=False):
    print(f"watching for new runs every {every_min} min (Ctrl-C to stop)")
    while True:
        res = run(notify_on_new=notify_on_new, with_claude=with_claude)
        out = text(res, quiet=True)
        if out:
            print(dt.datetime.now().strftime("%H:%M"), out, sep="\n", flush=True)
        time.sleep(every_min * 60)
