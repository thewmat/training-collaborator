"""Synthetic athlete for the demo and the tests. Nothing here is real data.

"Alex" (fictional): LT1 150 / LT2 170 / max 190 bpm, threshold pace improving from about 4:10 to
3:52/km over 30 weeks, a two-week break mid-way, a threshold-style week (Tue 1 km reps, Thu cruise
reps, Sun long run), a parkrun every fourth Saturday and a 10K race near the end. Chest strap from
week 9; wrist HR (noisier, under-reads on reps) before that.
"""
import datetime as dt
import json
import math
import os
import random

from . import vdot
from .fitwrite import Writer, ts

LT1, LT2, HRMAX, REST = 150, 170, 190, 48
SLOPE = 0.12                 # km/h per bpm


def v2_at(week, weeks):
    """Threshold speed (km/h) by week: steady gains, a dip after the break."""
    base = 14.4 + 1.2 * min(1.0, week / max(1, weeks - 2))
    if 12 <= week < 16:
        base -= 0.35 * (1 - (week - 12) / 4)
    return base


def simulate(segs, start_unix, a, strap, rng, rate=2):
    """segs: [(seconds, kmh, kind)] -> (records, laps, summary). HR follows speed with a 40 s lag and drift."""
    recs, laps = [], []
    t, dist, hr = 0, 0.0, 95.0
    for dur, kmh, kind in segs:
        lap0, d0, hrs = t, dist, []
        for _ in range(0, int(dur), rate):
            v = max(5.0, kmh * (1 + rng.gauss(0, 0.012)))
            target = (v - a) / SLOPE + 0.05 * max(0, t / 60 - 20)
            hr += (target - hr) * (1 - math.exp(-rate / 40))
            shown = hr + rng.gauss(0, 1.2)
            if not strap:
                shown = shown * (0.93 if kind == "rep" else 1.0) + rng.gauss(0, 4)
            dist += v / 3.6 * rate
            t += rate
            cad = 150 + 2.4 * v + rng.gauss(0, 1.5)
            alt = 30 + 8 * math.sin(dist / 900)
            recs.append((start_unix + t, dist, v, int(min(HRMAX, max(70, shown))), int(cad), alt))
            hrs.append(int(shown))
        laps.append({"start": start_unix + lap0, "secs": t - lap0, "dist": dist - d0, "hr": sum(hrs) / len(hrs),
                     "max_hr": max(hrs), "cad": int(150 + 2.4 * (dist - d0) / max(1, t - lap0) * 3.6)})
    return recs, laps, {"secs": t, "dist": dist, "hr": sum(r[3] for r in recs) / len(recs), "max_hr": max(r[3] for r in recs)}


def write_fit(path, start_unix, recs, laps, summ, strap):
    w = Writer()
    w.write("file_id", f0=4, f1=1, f2=9999, f4=ts(start_unix))
    w.write("device_info", f253=ts(start_unix), f0=0, f1=4, f2=1, f4=9999, f25=5)
    if strap:
        w.write("device_info", f253=ts(start_unix), f0=1, f1=120, f2=1, f4=9998, f25=1)
    w.write("event", f253=ts(start_unix), f0=0, f1=0)
    li = 0
    for r in recs:
        w.write("record", f253=ts(r[0]), f5=r[1] * 100, f73=r[2] / 3.6 * 1000, f3=r[3], f4=r[4] / 2, f78=(r[5] + 500) * 5)
        L = laps[li]
        if r[0] >= L["start"] + L["secs"]:
            w.write("lap", f253=ts(r[0]), f2=ts(L["start"]), f7=L["secs"] * 1000, f8=L["secs"] * 1000, f9=L["dist"] * 100,
                    f110=L["dist"] / L["secs"] * 1000, f15=L["hr"], f16=L["max_hr"], f17=L["cad"] / 2, f24=0)
            li = min(li + 1, len(laps) - 1)
    end = start_unix + summ["secs"]
    w.write("event", f253=ts(end), f0=0, f1=4)
    w.write("session", f253=ts(end), f2=ts(start_unix), f7=summ["secs"] * 1000, f8=summ["secs"] * 1000,
            f9=summ["dist"] * 100, f5=1, f6=0, f16=summ["hr"], f17=summ["max_hr"])
    open(path, "wb").write(w.bytes())


def generate(home, weeks=30, seed=7):
    rng = random.Random(seed)
    os.makedirs(os.path.join(home, "data", "fit"), exist_ok=True)
    os.makedirs(os.path.join(home, "log"), exist_ok=True)
    today = dt.date.today()
    first = today - dt.timedelta(today.weekday()) - dt.timedelta(7 * weeks)
    acts, aid = [], 900000000
    for wk in range(weeks):
        if wk in (12, 13):
            continue                                    # two-week break
        v2 = v2_at(wk, weeks)
        a = v2 - SLOPE * LT2
        easy = a + SLOPE * 140
        vd = vdot.vdot_from_threshold_kmh(v2)
        vol = 0.6 + 0.4 * min(1.0, wk / 20)
        strap = wk >= 8
        reps = 6 + min(4, wk // 5)
        plan = {
            0: ("Easy run", [(3000 * vol, easy, "easy")]),
            1: (f"{reps} x 1 km threshold", [(900, easy, "wu")] + sum(
                [[(1000 / (v2 * 1.015) * 3.6, v2 * 1.015, "rep"), (60, easy * 0.8, "rest")] for _ in range(reps)], [])[:-1]
                + [(600, easy, "cd")]),
            2: ("Easy run", [(2700 * vol, easy, "easy")]),
            3: ("4 x 2 km cruise", [(900, easy, "wu")] + sum(
                [[(2000 / v2 * 3.6, v2, "rep"), (90, easy * 0.8, "rest")] for _ in range(4)], [])[:-1] + [(600, easy, "cd")]),
            5: ("Easy run + strides", [(2400 * vol, easy, "easy")]),
            6: ("Long run", [((4200 + 2400 * min(1.0, wk / 22)) * vol, easy * 0.98, "easy")]),
        }
        if wk % 4 == 3:
            t5 = vdot.race_time(vd, 5000)
            plan[5] = ("Hilltown parkrun", [(600, easy, "wu"), (t5, 5000 / t5 * 3.6, "race")])
        if wk == weeks - 3:
            t10 = vdot.race_time(vd, 10000)
            plan[6] = ("Riverside 10K race", [(900, easy, "wu"), (t10, 10000 / t10 * 3.6, "race")])
        for dow, (name, segs) in plan.items():
            day = first + dt.timedelta(7 * wk + dow)
            if day >= today:
                continue
            start = dt.datetime.combine(day, dt.time(7, 0)).timestamp() + rng.randint(0, 1800)
            if name.endswith("parkrun") or "race" in name:
                # the race is its own activity; the warm-up is a separate run
                segs = [segs[-1]]
            aid += 1
            recs, laps, summ = simulate(segs, start, a, strap, rng)
            write_fit(os.path.join(home, "data", "fit", f"{aid}_ACTIVITY.fit"), start, recs, laps, summ, strap)
            hard = any(k == "rep" for _, _, k in segs) or any(k == "race" for _, _, k in segs)
            acts.append({"activityId": aid, "activityName": name,
                         "startTimeLocal": dt.datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M:%S"),
                         "activityType": {"typeKey": "running"},
                         "eventType": {"typeKey": "race" if "race" in name or "parkrun" in name else "uncategorized"},
                         "distance": round(summ["dist"], 1), "duration": summ["secs"], "movingDuration": summ["secs"],
                         "averageHR": round(summ["hr"]), "maxHR": summ["max_hr"], "lapCount": len(laps),
                         "activityTrainingLoad": round(summ["secs"] / 60 * (2.2 if hard else 1.1)),
                         "aerobicTrainingEffect": 3.9 if hard else 2.8, "anaerobicTrainingEffect": 2.3 if hard else 0.4})
    daily, sleep, hrv = [], [], []
    for i in range((today - first).days + 1):
        d = first + dt.timedelta(i)
        load7 = sum(x["activityTrainingLoad"] for x in acts
                    if 0 <= (d - dt.date.fromisoformat(x["startTimeLocal"][:10])).days < 7)
        k = d.isoformat()
        daily.append({"calendarDate": k, "heartRate": {"restingValue": REST + round(load7 / 400) + rng.randint(-1, 1)},
                      "bodyBattery": {"maxValue": max(20, 95 - load7 // 40 + rng.randint(-5, 5))}, "stress": {"avgLevel": 25}})
        sleep.append({"calendarDate": k, "sleepTimeSeconds": int(3600 * rng.uniform(6.8, 8.6)),
                      "sleepScores": {"overall": {"value": rng.randint(68, 92)}}})
        hrv.append({"calendarDate": k, "lastNightAvg": rng.randint(58, 74), "baseline": {"balancedLow": 60, "balancedUpper": 78}})
    D = os.path.join(home, "data")
    json.dump(acts, open(os.path.join(D, "activities.json"), "w"))
    json.dump(daily, open(os.path.join(D, "daily.json"), "w"))
    json.dump(sleep, open(os.path.join(D, "sleep.json"), "w"))
    json.dump(hrv, open(os.path.join(D, "hrv.json"), "w"))
    json.dump({"name": "Alex (synthetic demo athlete)", "demo": True, "units": "km",
               "hr": {"max": HRMAX, "rest": REST, "lt1": LT1, "lt2": LT2, "source": "demo values"},
               "racing": {"super_shoes": False, "plate_gain": 0.025}, "coach": {"has_coach": False},
               "preferences": {"system": "threshold", "max_quality_per_week": 2}},
              open(os.path.join(home, "profile.json"), "w"), indent=2)
    json.dump([{"event": "5K", "time": "19:58", "time_s": 1198, "date": (first + dt.timedelta(40)).isoformat(),
                "source": "demo (public results would go here)"},
               {"event": "Half marathon", "time": "1:32:10", "time_s": 5530, "date": (first - dt.timedelta(200)).isoformat(),
                "source": "demo"}], open(os.path.join(home, "pbs.json"), "w"), indent=1)
    return len(acts)
