"""Readiness: is today a day to run the planned session at its targets?

Signals (Garmin daily summaries, sleep, HRV, training load) against the athlete's own baseline
(median of days 8-35 before today), not population norms:
  resting HR   7-day mean +3 bpm = amber, +5 = red; today's +5 = amber
  sleep        7-day mean score < 70 = amber; last night < 60 = amber
  HRV          last night below Garmin's balanced range low = amber
  Body Battery morning peak < 50 = amber, < 30 = red
  load ratio   7-day load / (28-day load / 4) > 1.3 = amber, > 1.5 = red
Verdict: green = run the session at the targets; amber = run it on the slow edge of every target;
red = replace it with easy running or rest. Data never overrides how the athlete feels in the other
direction: a green day with heavy legs is still a day to back off.
"""
import datetime as dt
import statistics as st

from .garmin import load as load_store


def build(asof=None):
    today = dt.date.fromisoformat(asof) if asof else dt.date.today()
    daily = {r["calendarDate"]: r for r in load_store("daily.json")}
    sleep = {r["calendarDate"]: r for r in load_store("sleep.json")}
    hrv = {r["calendarDate"]: r for r in load_store("hrv.json")}
    acts = load_store("activities.json")
    days = [(today - dt.timedelta(i)).isoformat() for i in range(34, -1, -1)]

    def rhr(d):
        return ((daily.get(d) or {}).get("heartRate") or {}).get("restingValue")

    def sscore(d):
        return (((sleep.get(d) or {}).get("sleepScores") or {}).get("overall") or {}).get("value")

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    load = {}
    for a in acts:
        load[a["startTimeLocal"][:10]] = load.get(a["startTimeLocal"][:10], 0) + (a.get("activityTrainingLoad") or 0)
    base_vals = [rhr(d) for d in days[:-7] if rhr(d) is not None]
    base = st.median(base_vals) if base_vals else None
    r7 = mean(rhr(d) for d in days[-7:])
    r_today = rhr(days[-1]) if rhr(days[-1]) is not None else rhr(days[-2])
    s7, s_last = mean(sscore(d) for d in days[-7:]), next((sscore(d) for d in reversed(days) if sscore(d) is not None), None)
    bb = ((daily.get(days[-1]) or {}).get("bodyBattery") or {}).get("maxValue")
    h = hrv.get(days[-1]) or {}
    h_last, h_low = h.get("lastNightAvg"), ((h.get("baseline") or {}) or {}).get("balancedLow")
    acute = sum(load.get(d, 0) for d in days[-7:])
    chronic = sum(load.get(d, 0) for d in days[-28:]) / 4
    earliest = min((a["startTimeLocal"][:10] for a in acts), default=days[-1])
    acwr = acute / chronic if chronic and earliest <= days[-28] else None   # needs 4 full weeks of history

    flags = []
    if base is not None and r7 is not None:
        if r7 - base >= 5: flags.append((2, f"7-day resting HR {r7:.0f}, {r7 - base:+.0f} on baseline {base:.0f}"))
        elif r7 - base >= 3: flags.append((1, f"7-day resting HR {r7:.0f}, {r7 - base:+.0f} on baseline {base:.0f}"))
    if base is not None and r_today is not None and r_today - base >= 5:
        flags.append((1, f"resting HR today {r_today}, {r_today - base:+.0f} on baseline"))
    if s7 is not None and s7 < 70: flags.append((1, f"7-day sleep score {s7:.0f}"))
    if s_last is not None and s_last < 60: flags.append((1, f"last sleep score {s_last}"))
    if h_last and h_low and h_last < h_low: flags.append((1, f"HRV {h_last} below balanced range ({h_low})"))
    if bb is not None:
        if bb < 30: flags.append((2, f"Body Battery peak {bb}"))
        elif bb < 50: flags.append((1, f"Body Battery peak {bb}"))
    if acwr is not None:
        if acwr > 1.5: flags.append((2, f"load ratio {acwr:.2f}: this week well above the last four"))
        elif acwr > 1.3: flags.append((1, f"load ratio {acwr:.2f}"))
    level = max((l for l, _ in flags), default=0)
    verdict = ["Green", "Amber", "Red"][level]
    action = ["Run the planned session at its targets.",
              "Run the planned session on the slow edge of every target; drop optional reps.",
              "Replace the session with easy running or rest today."][level]
    return {"date": today.isoformat(), "verdict": verdict, "action": action, "reasons": [t for _, t in flags],
            "rhr_today": r_today, "rhr_7d": r7 and round(r7, 1), "rhr_baseline": base, "sleep_last": s_last,
            "sleep_7d": s7 and round(s7), "hrv_last": h_last, "body_battery": bb,
            "load_7d": round(acute), "load_28d_weekly": round(chronic), "load_ratio": acwr and round(acwr, 2),
            "has_data": bool(daily)}


def text(r):
    if not r["has_data"]:
        return "No daily wellness data (needs the Garmin API sync). Readiness = how you feel."
    s = [f"{r['verdict']}: {r['action']}"]
    s += [f"  - {x}" for x in r["reasons"]] or ["  - no flag raised"]
    s.append(f"  RHR {r['rhr_today']} (7d {r['rhr_7d']}, base {r['rhr_baseline']})  sleep {r['sleep_last']} (7d {r['sleep_7d']})  "
             f"HRV {r['hrv_last']}  BB {r['body_battery']}  load 7d {r['load_7d']} vs {r['load_28d_weekly']}/wk")
    return "\n".join(s)
