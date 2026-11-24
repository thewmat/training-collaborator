"""Best performances assembled from Garmin data.

Three sources, best first:
  races     runs that look like races: Garmin event type 'race', or a race word in the name (race, parkrun,
            10k, half, marathon, XC, relay, champs ...), at a standard distance (GPS within 4 %).
            The official time comes from public results (pbs.py); Garmin gives the splits.
  efforts   fastest rolling segment inside any run with a FIT file (1 km to marathon).
  summary   Garmin's own fastest-split fields on the activity list (1 km, mile, 5 km ...), which cover
            the full history even where no FIT file has been downloaded.
Every performance gets a VDOT so different distances can be ranked against each other.
Segments inside training runs are not races: they rank below races at the same VDOT and are flagged
when they beat the athlete's best race VDOT by more than 3 % (usually a GPS error).
"""
import datetime as dt
import glob
import json
import os
import re

from . import config, vdot
from .analyse import BESTS, load, rolling_best
from .garmin import is_run, load as load_store
from .units import DISTANCES, MILE, hms

RACE_WORDS = re.compile(r"\b(race|parkrun|park run|10k|5k|half|marathon|hm|xc|cross[- ]country|relay|champs?|"
                        r"championship|road race|pb|10 ?mile|5 ?mile|grand prix|gp)\b", re.I)
STANDARD = [("5K", 5000), ("5 miles", 5 * MILE), ("10K", 10000), ("10 miles", 10 * MILE),
            ("Half marathon", 21097.5), ("Marathon", 42195), ("3000m", 3000), ("Mile", MILE)]
SUMMARY_FIELDS = {"fastestSplit_1000": (1000, "1 km"), "fastestSplit_1609": (MILE, "Mile"),
                  "fastestSplit_5000": (5000, "5 km"), "fastestSplit_10000": (10000, "10 km"),
                  "fastestSplit_21098": (21097.5, "Half marathon"), "fastestSplit_42195": (42195, "Marathon")}
CACHE = "efforts.json"
MAX_VDOT = 85


def classify_race(a):
    name = a.get("activityName") or ""
    flagged = (a.get("eventType") or {}).get("typeKey") == "race" or bool(RACE_WORDS.search(name))
    d = a.get("distance") or 0
    for label, m in STANDARD:
        if abs(d - m) <= m * 0.04:
            return label if flagged else None
    return None


def efforts(refresh=False):
    """Rolling bests per FIT file, cached: {file: [{label, dist_m, time_s, from_km}]}."""
    p = config.data(CACHE)
    cache = {} if refresh or not os.path.exists(p) else json.load(open(p))
    for f in glob.glob(config.data("fit", "*.fit")):
        b = os.path.basename(f)
        if b in cache:
            continue
        try:
            _, recs = load(f)
        except Exception:                               # noqa: BLE001
            cache[b] = []
            continue
        row = []
        total = recs[-1][1] if recs else 0
        for dist, label in BESTS[1:]:
            if total >= dist * 1.01:
                r = rolling_best(recs, dist)
                if r:
                    row.append({"label": label, "dist_m": dist, "time_s": round(r[0], 1), "from_km": round(r[1] / 1000, 2)})
        cache[b] = row
    json.dump(cache, open(p, "w"))
    return cache


def assemble(refresh=False, top=3):
    acts = [a for a in load_store("activities.json") if is_run(a)]
    by_id = {str(a["activityId"]): a for a in acts}
    perf = []
    for a in acts:
        label = classify_race(a)
        if label and a.get("duration"):
            t = a.get("movingDuration") or a["duration"]
            perf.append({"kind": "race", "event": label, "dist_m": DISTANCES.get(label, 0) or a["distance"],
                         "time_s": round(t, 1), "date": a["startTimeLocal"][:10], "id": str(a["activityId"]),
                         "name": a.get("activityName") or "", "gps_m": round(a.get("distance") or 0)})
        for fld, (dist, lab) in SUMMARY_FIELDS.items():
            if a.get(fld):
                perf.append({"kind": "summary", "event": lab, "dist_m": dist, "time_s": round(a[fld], 1),
                             "date": a["startTimeLocal"][:10], "id": str(a["activityId"]), "name": a.get("activityName") or ""})
    for f, rows in efforts(refresh).items():
        aid = f.split("_")[0].split(".")[0]
        a = by_id.get(aid)
        if not a:
            continue
        for r in rows:
            perf.append({"kind": "effort", "event": r["label"], "dist_m": r["dist_m"], "time_s": r["time_s"],
                         "date": a["startTimeLocal"][:10], "id": aid, "name": a.get("activityName") or "",
                         "from_km": r["from_km"]})
    for p in perf:
        p["vdot"] = round(vdot.vdot(p["dist_m"], p["time_s"]), 1) if p["dist_m"] >= 1000 and p["time_s"] > 0 else None
    perf = [p for p in perf if p["vdot"] is None or p["vdot"] < MAX_VDOT]   # beyond world-record level: GPS garbage
    best_race = max((p["vdot"] for p in perf if p["kind"] == "race" and p["vdot"]), default=None)
    best_effort = max((p["vdot"] for p in perf if p["kind"] == "effort" and p["vdot"]), default=None)
    ref = best_race or best_effort
    for p in perf:
        # a training segment beating the best race (or Garmin's summary beating the spike-cleaned FIT
        # efforts) by > 3 % is almost always a GPS error
        p["suspect"] = bool(ref and p["kind"] != "race" and p["vdot"] and p["vdot"] > ref * 1.03)
    # best per event, races first; deduplicate the same activity appearing as summary and effort
    events = {}
    for p in sorted(perf, key=lambda p: (p["time_s"])):
        lst = events.setdefault(p["event"], [])
        if any(q["id"] == p["id"] for q in lst):
            continue
        if len(lst) < top:
            lst.append(p)
    ranked = sorted([p for p in perf if p["vdot"] and not p["suspect"]], key=lambda p: -p["vdot"])
    seen, best_overall = set(), []
    for p in ranked:
        if p["id"] in seen:
            continue
        seen.add(p["id"])
        best_overall.append(p)
        if len(best_overall) == 10:
            break
    out = {"built": dt.date.today().isoformat(), "best_race_vdot": best_race,
           "races": sorted([p for p in perf if p["kind"] == "race"], key=lambda p: p["date"]),
           "by_event": events, "top_by_vdot": best_overall}
    json.dump(out, open(config.out("bests.json"), "w"), indent=1)
    return out


def text(b):
    lines = ["Best performances from Garmin (time, VDOT, date). Races are whole activities flagged as races;",
             "efforts are the fastest segment inside a run. Confirm official times against public results.", ""]
    order = ["1 km", "Mile", "3 km", "5 km", "5K", "5 miles", "10 km", "10K", "10 miles", "Half marathon", "Marathon"]
    for ev in sorted(b["by_event"], key=lambda e: order.index(e) if e in order else 99):
        for i, p in enumerate(b["by_event"][ev]):
            lines.append(f"{ev if i == 0 else '':<14} {hms(p['time_s']):>8}  VDOT {p['vdot'] or '-':>5}  {p['date']}  "
                         f"{p['kind']:<7} {p['name'][:34]}" + ("  [suspect: GPS?]" if p["suspect"] else ""))
    lines += ["", "Top performances by VDOT:"]
    for p in b["top_by_vdot"]:
        lines.append(f"  {p['vdot']:>5}  {p['event']:<14} {hms(p['time_s']):>8}  {p['date']}  {p['kind']}")
    return "\n".join(lines)
