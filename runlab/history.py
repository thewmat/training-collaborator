"""Training and performance history: the facts Claude needs to write an athlete's story.

Built from the Garmin activity list (full history, no FIT needed) plus FIT files where present:
  years       km, runs, hours, longest run per calendar year
  weeks       Monday-start weeks: km, runs, hours, long run, quality sessions (Garmin training effect:
              anaerobic >= 2.0 or aerobic >= 3.8; FIT-only imports have no training effect, so 0)
  breaks      gaps of 10+ days without a run (illness, holidays, time off): the shape of the history
  builds      the 12 weeks before each race / PB: mean and peak km, longest run, sessions per week
  peaks       the highest 8-week rolling volume blocks
  intensity   time below LT1 / LT1-LT2 / above LT2 per week from strap-HR FIT files
"""
import datetime as dt
import glob
import json
import os
import statistics as st

from . import config, pbs
from .analyse import load
from .garmin import is_run, load as load_store
from .units import DISTANCES, hms

D = lambda s: dt.date.fromisoformat(s[:10])
monday = lambda d: d - dt.timedelta(d.weekday())


def _zones(prof):
    """Weekly seconds per zone from strap-HR FIT files (cached per file)."""
    lt1, lt2, _, _ = config.thresholds(prof)
    p = config.data("zones.json")
    cache = json.load(open(p)) if os.path.exists(p) else {}
    key = f"{lt1}-{lt2}"
    if cache.get("_key") != key:
        cache = {"_key": key}
    if not (lt1 and lt2):
        return {}, cache
    for f in glob.glob(config.data("fit", "*.fit")):
        b = os.path.basename(f)
        if b in cache:
            continue
        try:
            d, recs = load(f, tuple(prof["hr"].get("strap_products") or ()))
        except Exception:                               # noqa: BLE001
            cache[b] = None
            continue
        if d["hr_source"] != "strap":
            cache[b] = None
            continue
        z = [0, 0, 0]
        for a, c in zip(recs, recs[1:]):
            if a[3]:
                z[0 if a[3] < lt1 else 1 if a[3] <= lt2 else 2] += min(c[0] - a[0], 10)
        cache[b] = z
    json.dump(cache, open(p, "w"))
    return {k: v for k, v in cache.items() if k != "_key"}, cache


def build(prof=None):
    prof = prof or config.profile()
    runs = sorted([a for a in load_store("activities.json") if is_run(a)], key=lambda a: a["startTimeLocal"])
    if not runs:
        raise SystemExit("no runs stored: python3 -m runlab sync (or import)")
    km = lambda a: (a.get("distance") or 0) / 1000
    hrs = lambda a: (a.get("movingDuration") or a.get("duration") or 0) / 3600

    years = {}
    for a in runs:
        y = years.setdefault(a["startTimeLocal"][:4], {"year": a["startTimeLocal"][:4], "km": 0, "runs": 0, "hours": 0, "longest_km": 0})
        y["km"] += km(a); y["runs"] += 1; y["hours"] += hrs(a); y["longest_km"] = max(y["longest_km"], km(a))

    first, last = monday(D(runs[0]["startTimeLocal"])), monday(D(runs[-1]["startTimeLocal"]))
    weeks, w = {}, first
    while w <= last:
        weeks[w.isoformat()] = {"week": w.isoformat(), "km": 0.0, "runs": 0, "hours": 0.0, "long_km": 0.0, "quality": 0}
        w += dt.timedelta(7)
    for a in runs:
        W = weeks[monday(D(a["startTimeLocal"])).isoformat()]
        W["km"] += km(a); W["runs"] += 1; W["hours"] += hrs(a); W["long_km"] = max(W["long_km"], km(a))
        if (a.get("anaerobicTrainingEffect") or 0) >= 2.0 or (a.get("aerobicTrainingEffect") or 0) >= 3.8:
            W["quality"] += 1

    zones, _ = _zones(prof)
    for b, z in zones.items():
        if not z:
            continue
        aid = b.split("_")[0].split(".")[0]
        a = next((r for r in runs if str(r["activityId"]) == aid), None)
        if a:
            W = weeks[monday(D(a["startTimeLocal"])).isoformat()]
            W.setdefault("zones_min", [0, 0, 0])
            for i in range(3):
                W["zones_min"][i] += round(z[i] / 60, 1)

    breaks = []
    for a, b in zip(runs, runs[1:]):
        gap = (D(b["startTimeLocal"]) - D(a["startTimeLocal"])).days
        if gap >= 10:
            breaks.append({"from": a["startTimeLocal"][:10], "to": b["startTimeLocal"][:10], "days": gap})

    wl = list(weeks.values())
    roll = []
    for i in range(7, len(wl)):
        roll.append((sum(x["km"] for x in wl[i - 7:i + 1]) / 8, wl[i]["week"]))
    peaks = []
    for v, wk in sorted(roll, reverse=True):
        if v >= 0.6 * max(roll)[0] and all(abs((D(wk) - D(p["week_end"])).days) > 70 for p in peaks):
            peaks.append({"week_end": wk, "avg_km_8wk": round(v, 1)})
        if len(peaks) == 5:
            break

    # builds before races: official PBs with dates, plus Garmin race-flagged runs
    from .bests import classify_race
    races = [{"date": r["date"], "event": r["event"], "time": r.get("time") or hms(r["time_s"]), "source": "pbs"}
             for r in pbs.load() if r.get("date")]
    races += [{"date": a["startTimeLocal"][:10], "event": classify_race(a), "time": hms(a.get("movingDuration") or a["duration"]),
               "source": "garmin", "name": a.get("activityName")} for a in runs if classify_race(a)]
    seen, builds = set(), []
    for r in sorted(races, key=lambda r: r["date"]):
        if (r["date"], r["event"]) in seen:
            continue
        seen.add((r["date"], r["event"]))
        rd = D(r["date"])
        ws = [weeks[(monday(rd) - dt.timedelta(7 * k)).isoformat()] for k in range(1, 13)
              if (monday(rd) - dt.timedelta(7 * k)).isoformat() in weeks]
        if len(ws) < 6:
            continue
        builds.append({**r, "weeks": len(ws), "mean_km": round(st.mean(x["km"] for x in ws), 1),
                       "peak_km": round(max(x["km"] for x in ws), 1), "longest_km": round(max(x["long_km"] for x in ws), 1),
                       "runs_per_week": round(st.mean(x["runs"] for x in ws), 1),
                       "quality_per_week": round(st.mean(x["quality"] for x in ws), 1)})

    recent = wl[-12:]
    streak = 0
    for x in reversed(wl):
        if x["runs"] >= 3:
            streak += 1
        else:
            break
    out = {
        "built": dt.date.today().isoformat(), "first_run": runs[0]["startTimeLocal"][:10], "runs": len(runs),
        "total_km": round(sum(km(a) for a in runs)), "longest_run_km": round(max(km(a) for a in runs), 2),
        "years": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in y.items()} for y in years.values()],
        "weeks": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in x.items()} for x in wl],
        "recent_weeks": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in x.items()} for x in recent],
        "breaks": breaks, "peaks": peaks, "builds": builds, "consistency_streak_weeks": streak,
        "pbs": pbs.load(),
    }
    json.dump(out, open(config.out("history.json"), "w"), indent=1)
    open(config.out("history.md"), "w").write(markdown(out))
    return out


def markdown(h):
    L = [f"# Training history", "", f"{h['runs']} runs, {h['total_km']:,} km since {h['first_run']}. "
         f"Longest run {h['longest_run_km']} km. Current streak: {h['consistency_streak_weeks']} weeks with 3+ runs.", ""]
    L += ["## By year", "", "| Year | km | Runs | Hours | Longest km |", "|---|---|---|---|---|"]
    L += [f"| {y['year']} | {y['km']:.0f} | {y['runs']} | {y['hours']:.0f} | {y['longest_km']:.1f} |" for y in h["years"]]
    if h["pbs"]:
        L += ["", "## Official PBs", "", "| Event | Time | Date |", "|---|---|---|"]
        L += [f"| {r['event']} | {r['time']} | {r.get('date') or '-'} |" for r in sorted(h["pbs"], key=lambda r: DISTANCES.get(r["event"], 0))]
    if h["builds"]:
        L += ["", "## Builds into races (12 weeks before)", "",
              "| Race | Date | Result | Mean km/wk | Peak km | Longest | Runs/wk | Sessions/wk |", "|---|---|---|---|---|---|---|---|"]
        L += [f"| {b['event']} | {b['date']} | {b['time']} | {b['mean_km']} | {b['peak_km']} | {b['longest_km']} | "
              f"{b['runs_per_week']} | {b['quality_per_week']} |" for b in h["builds"]]
    if h["peaks"]:
        L += ["", "## Biggest training blocks (8-week average)", ""]
        L += [f"- {p['avg_km_8wk']} km/week, 8 weeks to {p['week_end']}" for p in h["peaks"]]
    if h["breaks"]:
        L += ["", "## Breaks (10+ days without running)", ""]
        L += [f"- {b['from']} to {b['to']}: {b['days']} days" for b in h["breaks"][-12:]]
    L += ["", "## Last 12 weeks", "", "| Week | km | Runs | Long | Sessions | Easy/Mod/Hard min |", "|---|---|---|---|---|---|"]
    for w in h["recent_weeks"]:
        z = w.get("zones_min")
        L.append(f"| {w['week']} | {w['km']:.1f} | {w['runs']} | {w['long_km']:.1f} | {w['quality']} | "
                 f"{'/'.join(f'{x:.0f}' for x in z) if z else '-'} |")
    return "\n".join(L) + "\n"
